"""The official pit-stop sheet for a race, and the stops on it that were real.

**Where the sheet comes from, in order** (``docs/DATA_SOURCES.md``):

1. Jolpica's pit stops, through FastF1's Ergast client. Published hours after
   the race. Its ``duration`` is the **pit-lane time**, entry to exit.
2. f1db (:mod:`app.data.f1db_pitstops`), the same sheet once its release
   covers the round, for when Jolpica cannot answer.

OpenF1's ``pit.stop_duration`` is the time the car stood still. It is attached
to the matching entry when OpenF1 publishes it, which it did not for any stop
of Mexico 2026.

**A suspended race is not a round of pit stops.** A red flag sends every
running car into the pit lane, and the sheet lists each one as a stop:

* the cars sit there for the whole suspension, so their entry runs to tens of
  minutes (~38 min at Mexico 2026, against ~22 s for a real stop);
* a lapped car is on an earlier lap when the flag comes out, so its long
  entry sits on its own lap, and it passes through the pit lane again on the
  leader's red-flag lap (55-61 s for five cars at Mexico 2026).

:func:`without_suspension` therefore leaves out every entry on the leader's
red-flag lap, and every entry over two minutes in the laps just before it. A
lap counts as a red flag when long entries from several cars mark it, or when
the stint data saw the field change tyres under it. A single long entry with no
red flag is a car in the garage for repairs, and stays a stop. Real stops on
the lap before the flag (Hamilton, Gasly, Piastri and Russell at Mexico 2026)
are kept, and what remains is renumbered per driver.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import TYPE_CHECKING

from fastf1.ergast import Ergast
from fastf1.exceptions import ErgastError
import pandas as pd
import structlog

from app.data.f1db_pitstops import PitStop, race_pit_stops as f1db_pit_stops
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import entry_list, find_session, session_ended
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import timedelta

logger = structlog.get_logger()

JOLPICA_SOURCE = "jolpica-pitstops"
F1DB_SOURCE = "f1db-pit-stops"

# Jolpica answers 30 rows unless asked for more. A red-flagged race doubles
# the sheet: Mexico 2026 had 58 entries.
JOLPICA_PAGE_LIMIT = 100

# Longer than any stop a car makes and rejoins from in normal running.
SUSPENSION_MIN_MILLIS = 120_000
# A red flag is long entries from at least this many cars, so one car in the
# garage for repairs is never mistaken for a suspended race.
SUSPENSION_MIN_CARS = 3
# How far behind the leader a lapped car's suspension entry can sit.
SUSPENSION_LAP_SPREAD = 3

# A published sheet can still gain a late entry, so it is read again after a while.
SHEET_TTL_SECONDS = 30 * 60
EMPTY_RETRY_SECONDS = 5 * 60

MILLIS_PER_MINUTE = 60_000


@dataclass(frozen=True)
class PitSheet:
    """Every entry of a race's published pit sheet, and where it came from."""

    source: str | None
    entries: tuple[PitStop, ...]


@dataclass(frozen=True)
class RealStops:
    """The sheet without the suspension: the stops drivers chose to make."""

    stops: tuple[PitStop, ...]
    #: Entries left out because the race was suspended, not because anyone stopped.
    suspension_entries: int


NO_SHEET = PitSheet(source=None, entries=())

_cache: TtlCache[tuple[int, int], PitSheet] = TtlCache()


def format_duration(duration: timedelta) -> str:
    """A duration as the sheet prints it: ``22.466``, ``1:00.513``, ``38:04.660``."""
    millis = round(duration.total_seconds() * 1000)
    minutes, rest = divmod(millis, MILLIS_PER_MINUTE)
    seconds = rest / 1000
    return f"{minutes}:{seconds:06.3f}" if minutes else f"{seconds:.3f}"


def _whole(value: object) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def stops_from_jolpica(rows: list[dict], codes: dict[str, str]) -> tuple[PitStop, ...]:
    """Jolpica pit-stop rows (as FastF1's Ergast client flattens them) as stops.

    ``codes`` maps Jolpica's driver ids onto three-letter codes; the sheet
    carries only the id. An entry for a driver it cannot name is skipped.
    """
    stops: list[PitStop] = []
    for row in rows:
        code, lap, stop = codes.get(str(row.get("driverId"))), _whole(row.get("lap")), _whole(row.get("stop"))
        if code is None or lap is None or stop is None:
            continue
        duration = row.get("duration")
        timed = duration is not None and not pd.isna(duration)
        stops.append(
            PitStop(
                driver_code=code,
                stop=stop,
                lap=lap,
                time=format_duration(duration) if timed else None,
                millis=round(duration.total_seconds() * 1000) if timed else None,
            )
        )
    return tuple(stops)


def _is_long(stop: PitStop) -> bool:
    return stop.millis is not None and stop.millis > SUSPENSION_MIN_MILLIS


def _runs(laps: Iterable[int]) -> list[list[int]]:
    """Laps grouped into runs no more than :data:`SUSPENSION_LAP_SPREAD` apart."""
    runs: list[list[int]] = []
    for lap in sorted(laps):
        if runs and lap - runs[-1][-1] <= SUSPENSION_LAP_SPREAD:
            runs[-1].append(lap)
        else:
            runs.append([lap])
    return runs


def suspension_laps(entries: tuple[PitStop, ...], flagged_laps: frozenset[int]) -> frozenset[int]:
    """The leader's lap at each red flag, read from the sheet and the stints.

    ``flagged_laps`` are the laps on which the stint data saw a car change
    tyres under a red flag (each car's own lap). The leader's lap is the
    latest lap of each run: lapped cars sit on earlier ones.
    """
    long_cars: dict[int, set[str]] = {}
    for entry in entries:
        if _is_long(entry):
            long_cars.setdefault(entry.lap, set()).add(entry.driver_code)
    laps: set[int] = set()
    for run in _runs(set(long_cars) | flagged_laps):
        cars = set().union(*(long_cars.get(lap, set()) for lap in run))
        if len(cars) >= SUSPENSION_MIN_CARS or not flagged_laps.isdisjoint(run):
            laps.add(run[-1])
    return frozenset(laps)


def _renumbered(stops: list[PitStop]) -> tuple[PitStop, ...]:
    """Each driver's stops numbered 1, 2, 3 in lap order, keeping the sheet's order."""
    numbers: dict[PitStop, int] = {}
    counts: dict[str, int] = {}
    for stop in sorted(stops, key=lambda item: item.lap):
        counts[stop.driver_code] = counts.get(stop.driver_code, 0) + 1
        numbers[stop] = counts[stop.driver_code]
    return tuple(replace(stop, stop=numbers[stop]) for stop in stops)


def without_suspension(entries: tuple[PitStop, ...], flagged_laps: frozenset[int]) -> RealStops:
    """The sheet's real stops: the red-flag suspension left out, the rest renumbered."""
    red_flags = suspension_laps(entries, flagged_laps)

    def suspended(entry: PitStop) -> bool:
        if entry.lap in red_flags:
            return True
        return _is_long(entry) and any(0 < flag - entry.lap <= SUSPENSION_LAP_SPREAD for flag in red_flags)

    kept = [entry for entry in entries if not suspended(entry)]
    return RealStops(stops=_renumbered(kept), suspension_entries=len(entries) - len(kept))


def _jolpica_entries(year: int, round_num: int) -> tuple[PitStop, ...]:
    try:
        ergast = Ergast()
        response = ergast.get_pit_stops(season=year, round=round_num, limit=JOLPICA_PAGE_LIMIT)
        if not response.content:
            return ()
        if not response.is_complete:
            # Part of a sheet would undercount the stops; f1db has the whole one.
            logger.warning("pit_sheet.jolpica_incomplete", year=year, round=round_num)
            return ()
        results = ergast.get_race_results(season=year, round=round_num)
    # requests' errors are OSErrors; FastF1 raises ErgastError for a bad answer.
    except (ErgastError, OSError, ValueError, KeyError) as exc:
        logger.warning("pit_sheet.jolpica_unavailable", year=year, round=round_num, error=str(exc))
        return ()
    rows = results.content[0].to_dict("records") if results.content else []
    codes = {str(row["driverId"]): row["driverCode"] for row in rows if isinstance(row.get("driverCode"), str)}
    return stops_from_jolpica(response.content[0].to_dict("records"), codes)


def _openf1_stationary(year: int, round_num: int) -> dict[tuple[str, int], int]:
    """OpenF1's stationary times in milliseconds, by (driver, lap); empty when unpublished."""
    try:
        with new_client() as client:
            race = find_session(client, year, round_num, "R")
            if race is None or not session_ended(race):
                return {}
            rows = [
                row for row in get_json(client, "pit", {"session_key": race.session_key}) if row.get("stop_duration")
            ]
            if not rows:
                return {}
            entries = entry_list(client, race.session_key)
    # The calendar lookup reaches FastF1's schedule backend, which raises
    # ValueError/KeyError for a bad season and OSError for a network failure.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("pit_sheet.openf1_unavailable", year=year, round=round_num, error=str(exc))
        return {}
    return {
        (entries[number].code, int(row["lap_number"])): round(float(row["stop_duration"]) * 1000)
        for row in rows
        if (number := row.get("driver_number")) in entries and row.get("lap_number") is not None
    }


def race_pit_sheet(year: int, round_num: int) -> PitSheet:
    """Every entry of the race's published pit sheet, suspension included.

    Callers leave the suspension out with :func:`without_suspension`, which
    needs the stints' red-flag laps. :data:`NO_SHEET` when nothing is published.
    """
    key = (year, round_num)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    sheet = NO_SHEET
    if entries := _jolpica_entries(year, round_num):
        sheet = PitSheet(source=JOLPICA_SOURCE, entries=entries)
    elif entries := f1db_pit_stops(year, round_num):
        sheet = PitSheet(source=F1DB_SOURCE, entries=entries)
    if sheet.entries and (stationary := _openf1_stationary(year, round_num)):
        timed = tuple(
            replace(entry, stationary_millis=stationary.get((entry.driver_code, entry.lap))) for entry in sheet.entries
        )
        sheet = PitSheet(source=sheet.source, entries=timed)
    _cache.put(key, sheet, SHEET_TTL_SECONDS if sheet.entries else EMPTY_RETRY_SECONDS)
    logger.info("pit_sheet.loaded", year=year, round=round_num, source=sheet.source, entries=len(sheet.entries))
    return sheet
