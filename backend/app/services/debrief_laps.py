"""The debrief's lap data: who led each lap and the top five's gap to the leader at every line.

A car crosses the line at the end of lap n when that lap ends (start plus time),
or, with no time published, where its next lap starts. Laps are OpenF1's; the
order of the top five is the classification's (the FIA's authority), never the
order OpenF1's timing implies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.data.openf1.session_laps import load_session_laps
from app.data.openf1.sessions import canonical_entry
from app.data.race_neutralisations import lap_ranges
from app.services.race_results import build_session_result

if TYPE_CHECKING:
    from datetime import datetime

    from app.data.openf1.laps import Lap
    from app.data.openf1.session_laps import SessionLaps

TRACE_CARS = 5
UNAVAILABLE_REASON = "OpenF1 hasn't published this race's laps yet."

Crossings = dict[tuple[int, int], "datetime"]


def _crossings(laps: tuple[Lap, ...]) -> Crossings:
    """Each car's line crossing at the end of each lap it has one for."""
    starts = {(lap.driver, lap.number): lap.start for lap in laps}
    found: Crossings = {}
    for lap in laps:
        moment = lap.end or starts.get((lap.driver, lap.number + 1))
        if moment is not None:
            found[(lap.driver, lap.number)] = moment
    return found


def _leaders(crossings: Crossings, total: int) -> list[int | None]:
    """The car with the earliest crossing of each lap, by number; None when nobody has one."""
    best: dict[int, tuple[datetime, int]] = {}
    for (driver, number), moment in crossings.items():
        if number not in best or (moment, driver) < best[number]:
            best[number] = (moment, driver)
    return [best[n][1] if n in best else None for n in range(1, total + 1)]


def _trace_cars(session: SessionLaps, year: int, round_num: int) -> list[tuple[int, int]]:
    """The first five classified cars OpenF1 lists, as (car number, classified position)."""
    race = build_session_result(year, round_num, "race")
    classified = sorted(
        (row for row in (race["classification"] if race else []) if row["position"] is not None),
        key=lambda row: row["position"],
    )[:TRACE_CARS]
    cars = [(session.driver_by_code(row["driver_code"]), row["position"]) for row in classified]
    return [(driver.number, position) for driver, position in cars if driver is not None]


def _gaps(crossings: Crossings, leaders: list[int | None], number: int) -> list[float | None]:
    gaps: list[float | None] = []
    for lap, leader in enumerate(leaders, start=1):
        own, ahead = crossings.get((number, lap)), crossings.get((leader, lap)) if leader is not None else None
        gaps.append(None if own is None or ahead is None else round((own - ahead).total_seconds(), 3))
    return gaps


def _driver(session: SessionLaps, year: int, number: int) -> dict:
    entry = canonical_entry(session.drivers[number], year)
    return {"driver_code": entry.code, "driver_name": entry.name, "team": entry.team}


def _empty() -> dict:
    return {
        "available": False,
        "reason": UNAVAILABLE_REASON,
        "total_laps": 0,
        "drivers": [],
        "leaders": [],
        "trace": [],
        "neutralisations": [],
    }


def build_debrief_laps(year: int, round_num: int) -> dict:
    session = load_session_laps(year, round_num, "R")
    if session is None or not session.laps:
        return _empty()
    crossings = _crossings(tuple(lap for lap in session.laps if lap.driver in session.drivers))
    total = max((number for _, number in crossings), default=0)
    leaders = _leaders(crossings, total)
    cars = _trace_cars(session, year, round_num)
    trace = [
        {
            "driver_code": session.drivers[number].code,
            "position": position,
            "gaps": _gaps(crossings, leaders, number),
        }
        for number, position in cars
    ]
    numbers = list(dict.fromkeys([*(n for n in leaders if n is not None), *(n for n, _ in cars)]))
    return {
        "available": True,
        "reason": None,
        "total_laps": total,
        "drivers": [_driver(session, year, number) for number in numbers],
        "leaders": [None if n is None else session.drivers[n].code for n in leaders],
        "trace": trace,
        "neutralisations": lap_ranges(session.laps, session.windows),
    }
