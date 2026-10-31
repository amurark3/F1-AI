"""Tyre stints for a race: stored, from OpenF1, or from FastF1 lap data.

f1db records results and pit stops but not what a car was running, so the
compound behind a strategy has to come from timing data. Each stint carries the
compound fitted, its lap range, and how many laps that set had already done,
which together describe the strategy rather than just its timing.

**Where stints come from, in order:**

1. This process's cache, then the document store (:mod:`app.data.race_stints_store`):
   a finished race's stints never change.
2. OpenF1 (:mod:`app.data.openf1_stints`). Since mid-October 2026 F1's
   live-timing archive refuses requests without an F1 TV token, so FastF1 has
   no lap data on a cold cache, and Render's cache is always cold. OpenF1 needs
   no login and agrees with FastF1 stint for stint.
3. FastF1's lap frame, for when OpenF1 is closed (it refuses unauthenticated
   clients while any session is live) and a warm local cache can still answer.

``tyre_life_start`` at the start of a stint is the detail that usually explains
the decision: a set starting at zero is new, and one starting above zero is a
scrubbed set from qualifying or practice. A stint chart without it makes two
very different strategies look identical. FastF1's ``TyreLife`` counts the lap
being driven, so it reads 1 on a new set's first lap and is reduced by one here.

The lap a stint *ends* on matters just as much, because not every tyre change
is a pit stop. When a race is red-flagged the whole field files into the pit
lane and changes tyres for free, which shows up as a stint boundary for every
car. Monza 2026 was red-flagged on lap 3 and produced 21 such boundaries
against 9 real stops; counting them as pit stops trebled every driver's stop
count. ``ended_under_red_flag`` lets callers tell a strategic stop from a
suspended race.

Relationship to :mod:`app.data.strategy`: that module also reads stints, but
for a different job. ``analyze_pit_strategy`` answers a question about *one
driver* — degradation, average pace, undercut and overcut windows, circuit
history — and is what the AI tool layer calls. This module returns the shape of
every driver's race and computes no degradation at all.

Caching is not optional. ``session.load()`` re-parses the whole session on every
call, measured at ~28s warm and over two minutes cold for a single race. A
completed race is cached for the life of the process and kept in the store; only
an *empty* result is retried, on a short interval, in case the race simply has
not run yet.

Thread safety: FastF1 session loads are wrapped with ``_fastf1_lock``, the
process-wide lock every FastF1 caller shares.
"""

from __future__ import annotations

import math
import threading
import time
from typing import TYPE_CHECKING

import fastf1
import structlog

from app.data.openf1_stints import openf1_race_stints
from app.data.race_stints_store import stint_store
from app.data.stint_model import Stint, clean_compound
from app.utils.fastf1_lock import FASTF1_LOCK

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

# Aliased to the process-wide lock: a per-module lock does not serialise
# against the other modules sharing FastF1's SQLite cache.
_fastf1_lock = FASTF1_LOCK

# A resolved stint list describes a finished race and never changes, so it is
# held for the life of the process.
_cache: dict[tuple[int, int | str], tuple[Stint, ...]] = {}
# An empty result is a different state: the race may not have run yet, so it is
# retried rather than pinned.
_empty_until: dict[tuple[int, int | str], float] = {}
_cache_lock = threading.Lock()

#: How long an empty result is trusted before the sources are tried again.
EMPTY_RETRY_SECONDS = 300.0

#: FastF1 concatenates the single-digit track statuses seen during a lap, so a
#: red-flagged lap reads e.g. "1245". Code 5 is the red flag.
RED_FLAG_STATUS = "5"


def _is_missing(value: object) -> bool:
    """True for None and for the NaN pandas leaves in unset numeric cells."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def _bool_or_none(value: object) -> bool | None:
    # FastF1 leaves this as NaN where the tyre history is incomplete, and NaN
    # is truthy — coercing it straight to bool would claim every unknown set
    # was fresh.
    if _is_missing(value):
        return None
    return bool(value)


def _laps_before(tyre_life: object) -> int | None:
    """Laps on a set before this stint, from FastF1's ``TyreLife`` on its first lap.

    ``TyreLife`` includes the lap being driven, so a new set reads 1 there.
    """
    if _is_missing(tyre_life):
        return None
    return max(int(tyre_life) - 1, 0)


def _stints_from_laps(laps: pd.DataFrame, driver_codes: dict[str, str]) -> tuple[Stint, ...]:
    """Collapse a lap frame into one row per (driver, stint)."""
    frame = laps.dropna(subset=["Stint", "LapNumber"])
    if frame.empty:
        return ()

    stints: list[Stint] = []
    for (driver, stint), group in frame.groupby(["Driver", "Stint"], sort=True):
        ordered = group.sort_values("LapNumber")
        first = ordered.iloc[0]
        last = ordered.iloc[-1]
        stints.append(
            Stint(
                driver_code=driver_codes.get(str(driver), str(driver)),
                team=str(first.get("Team", "") or "").strip(),
                stint=int(stint),
                compound=clean_compound(first.get("Compound")),
                start_lap=int(ordered["LapNumber"].min()),
                end_lap=int(ordered["LapNumber"].max()),
                laps=len(ordered),
                tyre_life_start=_laps_before(first.get("TyreLife")),
                fresh=_bool_or_none(first.get("FreshTyre")),
                ended_under_red_flag=RED_FLAG_STATUS in str(last.get("TrackStatus") or ""),
            )
        )

    stints.sort(key=lambda item: (item.driver_code, item.stint))
    return tuple(stints)


def _cached(key: tuple[int, int | str]) -> tuple[Stint, ...] | None:
    """A hit, or ``None`` when the sources must actually be asked."""
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            return hit
        if time.monotonic() < _empty_until.get(key, 0.0):
            return ()
    return None


def _store(key: tuple[int, int | str], stints: tuple[Stint, ...]) -> None:
    with _cache_lock:
        if stints:
            _cache[key] = stints
            _empty_until.pop(key, None)
        else:
            _empty_until[key] = time.monotonic() + EMPTY_RETRY_SECONDS


def _driver_codes(results: pd.DataFrame | None) -> dict[str, str]:
    """FastF1's driver identifier mapped onto the three-letter code.

    FastF1 keys laps by the number for some seasons and the abbreviation for
    others; the results frame maps either onto the code every other surface
    here uses.
    """
    codes: dict[str, str] = {}
    if results is None or results.empty:
        return codes
    for _, row in results.iterrows():
        abbreviation = str(row.get("Abbreviation", "") or "").strip().upper()
        if not abbreviation:
            continue
        codes[str(row.get("DriverNumber", "") or "").strip()] = abbreviation
        codes[abbreviation] = abbreviation
    return codes


def _fastf1_stints(year: int, round_num: int) -> tuple[Stint, ...]:
    """Stints from FastF1's lap frame; empty when the session cannot be loaded."""
    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "R")
            session.load(telemetry=False, weather=False, messages=False)
        laps = session.laps
    # Deliberately broad, matching every other FastF1 loader in this package
    # (``session_entries``, ``predictions``, ``strategy``). The failure surface
    # is genuinely open: FastF1 raises ``SessionNotAvailableError`` from its
    # *private* ``_api`` module for an unpublished session, plus its own public
    # error family, plus requests/OSError from the network read. Catching the
    # narrow set would mean importing a private name and still missing cases,
    # and this function's contract is "no stints" for every one of them.
    except Exception as exc:
        logger.warning("race_stints.unavailable", year=year, round=round_num, error=str(exc))
        return ()

    if laps is None or laps.empty:
        logger.info("race_stints.no_laps", year=year, round=round_num)
        return ()
    return _stints_from_laps(laps, _driver_codes(session.results))


def race_stints(year: int, round_num: int) -> tuple[Stint, ...]:
    """Every tyre stint of a race, by driver then stint order.

    Returns an empty tuple when no source can say: a race that has not run, or
    every source unreachable. Callers report the gap rather than presenting an
    empty strategy as a real one.
    """
    key = (year, round_num)
    cached = _cached(key)
    if cached is not None:
        return cached

    stored = stint_store.get(year, round_num)
    if stored:
        _store(key, stored)
        return stored

    stints = openf1_race_stints(year, round_num) or _fastf1_stints(year, round_num)
    _store(key, stints)
    if stints:
        stint_store.put(year, round_num, stints)
    logger.info("race_stints.loaded", year=year, round=round_num, stints=len(stints))
    return stints
