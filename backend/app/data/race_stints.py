"""Tyre stints for a race, from FastF1 lap data.

f1db records results and pit stops but not what a car was running, so the
compound behind a strategy has to come from FastF1's lap frame. Each lap
carries the stint it belongs to, the compound fitted, and how many laps that
set had already done — which together describe the strategy rather than just
its timing.

``TyreLife`` at the start of a stint is the detail that usually explains the
decision: a set starting at zero is new, and one starting above zero is a
scrubbed set from qualifying or practice. A stint chart without it makes two
very different strategies look identical.

``TrackStatus`` on the lap a stint *ends* matters just as much, because not
every tyre change is a pit stop. When a race is red-flagged the whole field
files into the pit lane and changes tyres for free, which shows up as a stint
boundary — and as a ``PitInTime`` — for every car. Monza 2026 was red-flagged on
lap 3 and produced 21 such boundaries against 9 real stops; counting them as
pit stops trebled every driver's stop count. The end-lap status is therefore
recorded so callers can tell a strategic stop from a suspended race.

Relationship to :mod:`app.data.strategy`: that module also reads stints, but
for a different job. ``analyze_pit_strategy`` answers a question about *one
driver* — degradation, average pace, undercut and overcut windows, circuit
history — and is what the AI tool layer calls. Using it to draw a whole-field
stint chart would mean running that analysis twenty times over to recover a
lap range each time. This module makes one pass over the lap frame and returns
the shape of every driver's race, and computes no degradation at all.

Caching is not optional here. ``session.load()`` re-parses the whole session
from its cache on every call — measured at ~28s warm and over two minutes cold
for a single race — which is far too slow to sit in a request path. A stint is
also immutable once the chequered flag falls, so a completed race is cached for
the life of the process and only an *empty* result is retried, on a short
interval, in case the race simply has not run yet.

Thread safety: FastF1 session loads are wrapped with ``_fastf1_lock``, the same
per-module pattern used by :mod:`app.data.session_entries` and
:mod:`app.data.predictions`.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import fastf1
import structlog

from app.utils.fastf1_lock import FASTF1_LOCK

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

#: How long an empty result is trusted before the session is tried again.
EMPTY_RETRY_SECONDS = 300.0

#: FastF1 writes this when it has lap rows but no compound for them.
UNKNOWN_COMPOUND = "UNKNOWN"

#: FastF1 concatenates the single-digit track statuses seen during a lap, so a
#: red-flagged lap reads e.g. "1245". Code 5 is the red flag.
RED_FLAG_STATUS = "5"


@dataclass(frozen=True)
class Stint:
    """One run on one set of tyres."""

    driver_code: str
    #: Constructor the driver ran for, for livery-tinting a stint chart.
    team: str
    #: Which stint of the race, counting from 1.
    stint: int
    #: Tyre compound, or ``None`` when FastF1 has lap rows but no compound.
    compound: str | None
    start_lap: int
    end_lap: int
    laps: int
    #: Laps already on the set when the stint began: 0 for a new set.
    tyre_life_start: int | None
    #: Whether the set was new when fitted. ``None`` when not recorded.
    fresh: bool | None
    #: True when the lap this stint ended on was red-flagged, which makes the
    #: tyre change a consequence of the suspension rather than a pit stop.
    ended_under_red_flag: bool


def _clean_compound(value) -> str | None:
    text = str(value or "").strip().upper()
    if not text or text in {"NAN", "NONE", UNKNOWN_COMPOUND}:
        return None
    return text


def _is_missing(value) -> bool:
    """True for None and for the NaN pandas leaves in unset numeric cells."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def _bool_or_none(value) -> bool | None:
    # FastF1 leaves this as NaN where the tyre history is incomplete, and NaN
    # is truthy — coercing it straight to bool would claim every unknown set
    # was fresh.
    if _is_missing(value):
        return None
    return bool(value)


def _int_or_none(value) -> int | None:
    if _is_missing(value):
        return None
    return int(value)


def _stints_from_laps(laps, driver_codes: dict[str, str]) -> tuple[Stint, ...]:
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
                compound=_clean_compound(first.get("Compound")),
                start_lap=int(ordered["LapNumber"].min()),
                end_lap=int(ordered["LapNumber"].max()),
                laps=len(ordered),
                tyre_life_start=_int_or_none(first.get("TyreLife")),
                fresh=_bool_or_none(first.get("FreshTyre")),
                ended_under_red_flag=RED_FLAG_STATUS in str(last.get("TrackStatus") or ""),
            )
        )

    stints.sort(key=lambda item: (item.driver_code, item.stint))
    return tuple(stints)


def _cached(key: tuple[int, int | str]) -> tuple[Stint, ...] | None:
    """A hit, or ``None`` when the session must actually be loaded."""
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


def race_stints(year: int, round_num: int) -> tuple[Stint, ...]:
    """Every tyre stint of a race, by driver then stint order.

    Returns an empty tuple when the session cannot be loaded — a race that has
    not run, or a FastF1 source that is unavailable. Callers report the gap
    rather than presenting an empty strategy as a real one.
    """
    key = (year, round_num)
    cached = _cached(key)
    if cached is not None:
        return cached

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
        _store(key, ())
        return ()

    if laps is None or laps.empty:
        logger.info("race_stints.no_laps", year=year, round=round_num)
        _store(key, ())
        return ()

    # FastF1 keys laps by its own driver identifier, which is the number for
    # some seasons and the abbreviation for others; the results frame is what
    # maps either onto the three-letter code every other surface here uses.
    codes: dict[str, str] = {}
    results = session.results
    if results is not None and not results.empty:
        for _, row in results.iterrows():
            abbreviation = str(row.get("Abbreviation", "") or "").strip().upper()
            if not abbreviation:
                continue
            codes[str(row.get("DriverNumber", "") or "").strip()] = abbreviation
            codes[abbreviation] = abbreviation

    stints = _stints_from_laps(laps, codes)
    _store(key, stints)
    logger.info("race_stints.loaded", year=year, round=round_num, stints=len(stints))
    return stints
