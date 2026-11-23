"""The order at the line, lap by lap, and why each place changed (pure: plain data in, plain data out).

A car crosses the line at the end of lap n where its next lap starts, else when
the lap ends. Its place there is OpenF1's ``position`` stream sampled at that
moment. Nothing here infers who finished: callers pass the classification's
finishers in.
"""

from __future__ import annotations

from bisect import bisect_right, insort
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from statistics import median
from typing import TYPE_CHECKING

from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable
    from datetime import datetime

    from app.data.openf1.laps import Lap

Crossings = dict[tuple[int, int], "datetime"]
Samples = dict[int, tuple[list["datetime"], list[int]]]

# shortcut: OpenF1 stamps the new place just after the line; 1 s matches the reference derivation on R19, revisit if a race reads wrong
SAMPLE_LAG = timedelta(seconds=1)
# a lane time over 1.5 × the race's median is a red-flag entry or a restart wait, not a stop
STOP_LANE_FACTOR = 1.5
# A stop counts on the lap it ends and the one after: the in-lap and the out-lap.
STOP_WINDOW = 1


def crossings(laps: Iterable[Lap]) -> Crossings:
    """Each car's line crossing at the end of each lap it has one for."""
    laps = tuple(laps)
    starts = {(lap.driver, lap.number): lap.start for lap in laps}
    found: Crossings = {}
    for lap in laps:
        moment = starts.get((lap.driver, lap.number + 1)) or lap.end
        if moment is not None:
            found[(lap.driver, lap.number)] = moment
    return found


def _samples(rows: Iterable[dict]) -> Samples:
    """Each car's position rows as sorted (dates, places)."""
    stamped: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for row in rows:
        moment = parse_iso(row.get("date"))
        if moment is not None and row.get("driver_number") is not None and row.get("position") is not None:
            insort(stamped[int(row["driver_number"])], (moment, int(row["position"])))
    return {car: ([m for m, _ in pairs], [p for _, p in pairs]) for car, pairs in stamped.items()}


def place_at(samples: tuple[list[datetime], list[int]], moment: datetime) -> int:
    """The car's last place stamped at or before ``moment`` + SAMPLE_LAG; its first when none is earlier."""
    dates, places = samples
    return places[max(bisect_right(dates, moment + SAMPLE_LAG) - 1, 0)]


def lap_orders(laps: Iterable[Lap], position_rows: Iterable[dict], finishers: Collection[int]) -> list[list[int]]:
    """Per lap (1…total), the car numbers in place order at the line.

    A car with no crossing on a lap, or no position row at all, is left out of
    that lap. On the last lap each finisher whose last crossing came earlier (a
    lapped car) joins, placed by its sample at that crossing.
    """
    found = crossings(laps)
    samples = _samples(position_rows)
    total = max((number for _, number in found), default=0)
    rows: list[list[tuple[int, datetime, int]]] = [[] for _ in range(total)]
    last: dict[int, int] = {}
    for (car, number), moment in found.items():
        if car in samples:
            rows[number - 1].append((place_at(samples[car], moment), moment, car))
            last[car] = max(last.get(car, 0), number)
    for car in finishers:
        if car in last and last[car] < total:
            moment = found[(car, last[car])]
            rows[total - 1].append((place_at(samples[car], moment), moment, car))
    return [[car for _, _, car in sorted(lap_rows)] for lap_rows in rows]


def _lane(row: dict) -> float | None:
    return row["lane_duration"] if row.get("lane_duration") is not None else row.get("pit_duration")


def real_stops(pit_rows: Iterable[dict], codes: dict[int, str]) -> list[tuple[str, int]]:
    """Each real stop as (driver code, lap), in lap order.

    A row is a stop when its lane time is under STOP_LANE_FACTOR × the race's
    median lane time. OpenF1 omits ``stop_duration`` for stops that are on the
    official pit sheet, so it is not required.
    """
    rows = [(row, _lane(row)) for row in pit_rows]
    lanes = [lane for _, lane in rows if lane is not None]
    if not lanes:
        return []
    limit = STOP_LANE_FACTOR * median(lanes)
    found = {
        (codes[int(row["driver_number"])], int(row["lap_number"]))
        for row, lane in rows
        if lane is not None and lane < limit and int(row["driver_number"]) in codes
    }
    return sorted(found, key=lambda stop: (stop[1], stop[0]))


def overtake_laps(rows: Iterable[dict], laps: Iterable[Lap], codes: dict[int, str]) -> dict[int, set[frozenset[str]]]:
    """Each overtakes row on the lap the overtaking car was on at its date, as the pair of codes."""
    starts: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for lap in laps:
        if lap.start is not None:
            insort(starts[lap.driver], (lap.start, lap.number))
    found: dict[int, set[frozenset[str]]] = defaultdict(set)
    for row in rows:
        by, past, moment = (
            row.get("overtaking_driver_number"),
            row.get("overtaken_driver_number"),
            parse_iso(row.get("date")),
        )
        if by not in codes or past not in codes or moment is None:
            continue
        dated = starts.get(by, [])
        index = bisect_right([start for start, _ in dated], moment) - 1
        found[dated[index][1] if index >= 0 else 1].add(frozenset((codes[by], codes[past])))
    return dict(found)


def track_status(neutralisations: Iterable[dict], lap: int) -> str | None:
    """ "red", "sc" or "vsc" when a range covers the lap (red over sc over vsc), else None."""
    kinds = {row["kind"] for row in neutralisations if row["start_lap"] <= lap <= row["end_lap"]}
    return next((kind for kind in ("red", "sc", "vsc") if kind in kinds), None)


def _stop_lap(stops: dict[str, list[int]], code: str, lap: int) -> int | None:
    """The car's latest stop on ``lap`` or the lap before, if any."""
    return next((s for s in sorted(stops.get(code, []), reverse=True) if lap - STOP_WINDOW <= s <= lap), None)


@dataclass(frozen=True)
class LapView:
    """What explains a lap's changes: the order before and after it, the stops, the pass pairs and the track."""

    lap: int
    prev: list[str]
    cur: list[str]
    stops: dict[str, list[int]]
    passes: set[frozenset[str]]
    status: str | None


def classify(code: str, view: LapView) -> dict:
    """Why ``code`` changed place on the lap: the first reason that holds, never an unexplained "overtake"."""
    prev, cur, stops, lap = view.prev, view.cur, view.stops, view.lap
    before, after = prev.index(code), cur.index(code)
    swapped = [m for m in prev if m in cur and (prev.index(m) < before) != (cur.index(m) < after) and m != code]
    kind, rival, stop_lap = "change", None, None
    if (stop_lap := _stop_lap(stops, code, lap)) is not None:
        kind = "own_stop"
    elif (stopper := next((m for m in swapped if _stop_lap(stops, m, lap) is not None), None)) is not None:
        kind, rival, stop_lap = "rival_stop", stopper, _stop_lap(stops, stopper, lap)
    elif after < before and (gone := next((m for m in prev[:before] if m not in cur), None)) is not None:
        kind, rival = "retirement", gone
    elif view.status is not None:
        kind = "neutralised"
    elif (passed := next((m for m in swapped if frozenset((code, m)) in view.passes), None)) is not None:
        kind, rival = "pass", passed
    return {
        "driver_code": code,
        "from": before + 1,
        "to": after + 1,
        "kind": kind,
        "rival": rival,
        "stop_lap": stop_lap,
    }


def lap_changes(view: LapView) -> list[dict]:
    """``classify`` for every car whose place moved on the lap, by new place."""
    return [
        classify(code, view) for code in view.cur if code in view.prev and view.prev.index(code) != view.cur.index(code)
    ]
