"""A race's strategy in one payload: every stint, and every pit stop.

Two sources, joined because neither answers alone. Timing data (OpenF1, or
FastF1's lap frame; see :mod:`app.data.race_stints`) knows what compound a car
was on and for how long; f1db knows how long the crew held it stationary. A stint chart without stop times cannot say whether a slow
in-lap was the driver or the pit crew, and a stop list without compounds cannot
say what the stop was *for*.

They are joined on (driver, lap) rather than by index: a stop's lap is the lap
it happened on, which is the lap a stint ends. Where a stop has no matching
stint boundary — the lap data is incomplete, or the stop is the duplicated
row artifact f1db carries for some 2026 rounds — the stop is still reported,
unattached, rather than dropped or forced onto the wrong stint.

**Not every tyre change is a pit stop.** A red flag sends the whole field into
the pit lane to change tyres for free, and that shows up as a stint boundary
for every car. Monza 2026 was red-flagged on lap 3: 21 boundaries, against 9
real stops. Boundaries ending on a red-flagged lap are therefore counted
separately and never as stops.

**Where the two disagree on a lap, the stop sheet wins, if it can say which.**
OpenF1 numbered whole 2026 races a lap low (R1, R5, R6, R16) and ended some
first stints on lap 1 for stops made much later (Stroll, USA 2026), so no stop
attached and the chart showed boundaries a lap or more off. When a driver's
tyre changes (red-flag changes aside) and published stops are equal in number,
the changes are moved onto the stops' laps in order. Any other disagreement is
left as the timing data has it and reported. Across 2026 rounds 1-18 this left
16 tyre changes without a published stop outside Monaco, mostly stops the sheet
never published. Monaco (R6) keeps 41: its stint laps also disagree with
OpenF1's own lap feed, so its red-flag changes cannot be placed and count as
stops.

The counts a caller gets are deliberately three different facts:
``stops`` is what the driver actually did, ``red_flag_changes`` is what the
suspension gave them, and ``timed_stops`` is how many of the former have a
published stationary time. They differ, and flattening them hides either a
strategy or a gap in the source.
"""

from __future__ import annotations

from dataclasses import replace

import structlog

from app.data.f1db_pitstops import PitStop, race_pit_stops
from app.data.f1db_results import race_results
from app.data.race_stints import Stint, race_stints

logger = structlog.get_logger()

# Where a driver sorts when the race result does not place them — behind every
# classified runner, then alphabetically so the order is at least stable.
UNPLACED = 999

STINTS_UNAVAILABLE = (
    "Tyre stint data is not available for this race yet. It is published once "
    "the race has been run, and can be out of reach while another session is live."
)
STOPS_UNAVAILABLE = "No pit stops are published for this race yet."


def _partial_stops_warning(published: int, made: int) -> str:
    return (
        f"Only {published} of the {made} pit stops made in this race have a "
        "published stationary time. The stint chart shows every stop; the "
        "table below lists the ones the stop sheet timed."
    )


def _red_flag_note(changes: int) -> str:
    return (
        f"{changes} tyre change(s) happened while the race was red-flagged. "
        "Those are not counted as pit stops: the race was suspended and the "
        "change cost the driver nothing."
    )


def _realigned_note(drivers: int) -> str:
    return (
        f"Tyre changes for {drivers} driver(s) are shown on the laps the published "
        "stop sheet records. The timing feed placed them on different laps."
    )


def _realigned(rows: list[Stint], stops: list[PitStop]) -> list[Stint] | None:
    """One driver's stints with each pit-stop boundary moved onto its published lap.

    ``None`` when the stop sheet cannot settle it: a different number of stops
    than tyre changes, laps that already agree, or a move that would run a
    stint backwards past its neighbour.
    """
    boundaries = [index for index, stint in enumerate(rows[:-1]) if not stint.ended_under_red_flag]
    laps = sorted(stop.lap for stop in stops)
    if len(boundaries) != len(laps) or [rows[index].end_lap for index in boundaries] == laps:
        return None
    moved = dict(zip(boundaries, laps, strict=True))
    aligned: list[Stint] = []
    for index, stint in enumerate(rows):
        start = aligned[-1].end_lap + 1 if index - 1 in moved else stint.start_lap
        end = moved.get(index, stint.end_lap)
        if start > end:
            return None
        aligned.append(replace(stint, start_lap=start, end_lap=end, laps=end - start + 1))
    return aligned


def _align_to_stop_sheet(stints: tuple[Stint, ...], stops: tuple[PitStop, ...]) -> tuple[tuple[Stint, ...], int]:
    """Every stint, with boundaries moved onto the stop sheet where it settles them.

    Also returns how many drivers were moved, for the payload to say so.
    """
    stints_by_driver: dict[str, list[Stint]] = {}
    for stint in stints:
        stints_by_driver.setdefault(stint.driver_code, []).append(stint)
    stops_by_driver: dict[str, list[PitStop]] = {}
    for stop in stops:
        stops_by_driver.setdefault(stop.driver_code, []).append(stop)

    aligned: list[Stint] = []
    realigned = 0
    for code, rows in stints_by_driver.items():
        ordered = sorted(rows, key=lambda stint: stint.stint)
        moved = _realigned(ordered, stops_by_driver.get(code, []))
        realigned += moved is not None
        aligned.extend(moved or ordered)
    return tuple(aligned), realigned


def _stop_payload(stop: PitStop) -> dict:
    return {
        "driver_code": stop.driver_code,
        "stop": stop.stop,
        "lap": stop.lap,
        "time": stop.time,
        "millis": stop.millis,
    }


def _stint_payload(stint: Stint, stop: PitStop | None) -> dict:
    """One stint, with the stop that ended it when there was one.

    The final stint of a race ends at the flag, not in the pit lane, so its
    ``ended_by_stop`` is null — which is a fact about the race rather than
    missing data.
    """
    return {
        "driver_code": stint.driver_code,
        "stint": stint.stint,
        "compound": stint.compound,
        "start_lap": stint.start_lap,
        "end_lap": stint.end_lap,
        "laps": stint.laps,
        "tyre_life_start": stint.tyre_life_start,
        "fresh": stint.fresh,
        "ended_under_red_flag": stint.ended_under_red_flag,
        "ended_by_stop": None if stop is None else _stop_payload(stop),
    }


def _is_pit_stop(stint: dict, is_last: bool) -> bool:
    """Whether this stint ended in an actual pit stop.

    The last stint ends at the chequered flag, and a stint ended by a red flag
    ended because the race stopped — neither is a stop the driver chose to make.
    """
    return not is_last and not stint["ended_under_red_flag"]


def _driver_rows(
    stints: tuple[Stint, ...],
    stops: tuple[PitStop, ...],
    finishing_order: dict[str, int],
) -> list[dict]:
    """Group stints per driver, attaching the stop that closed each one.

    Ordered by finishing position, not alphabetically. A strategy chart is read
    against the result it produced — the winner's stint plan belongs at the top
    — and an alphabetical list puts ALB above the race winner for no reason.
    Drivers the result does not place (or a race with no published result yet)
    fall to the bottom in a stable alphabetical order rather than an arbitrary
    one.
    """
    by_driver_lap = {(stop.driver_code, stop.lap): stop for stop in stops}

    drivers: dict[str, list[dict]] = {}
    teams: dict[str, str] = {}
    for stint in stints:
        teams.setdefault(stint.driver_code, stint.team)
        # A stop is recorded on the lap the car came in, which is the last lap
        # of the stint it ends.
        stop = by_driver_lap.get((stint.driver_code, stint.end_lap))
        drivers.setdefault(stint.driver_code, []).append(_stint_payload(stint, stop))

    rows = [_driver_payload(code, stint_rows, teams, finishing_order) for code, stint_rows in drivers.items()]
    rows.sort(key=lambda row: (row["finish_position"] or UNPLACED, row["driver_code"]))
    return rows


def _driver_payload(
    code: str,
    rows: list[dict],
    teams: dict[str, str],
    finishing_order: dict[str, int],
) -> dict:
    last_index = len(rows) - 1
    # Counted from stint boundaries rather than the published stop sheet, which
    # can be incomplete — but excluding the boundaries that were not stops.
    stops = sum(1 for index, row in enumerate(rows) if _is_pit_stop(row, index == last_index))
    return {
        "driver_code": code,
        "team": teams.get(code, ""),
        # Null when the result does not place this driver, which is a different
        # state from finishing last.
        "finish_position": finishing_order.get(code),
        "stints": rows,
        "stops": stops,
        # Free tyre changes handed to the whole field by a suspended race.
        "red_flag_changes": sum(1 for row in rows if row["ended_under_red_flag"]),
        # How many of this driver's stops carry a published stationary time.
        "timed_stops": sum(1 for row in rows if row["ended_by_stop"] is not None),
        "total_laps": max((row["end_lap"] for row in rows), default=0),
    }


def _fastest_stop(stops: tuple[PitStop, ...]) -> dict | None:
    timed = [stop for stop in stops if stop.millis]
    if not timed:
        return None
    return _stop_payload(min(timed, key=lambda stop: stop.millis or 0))


def build_race_strategy(year: int, round_num: int) -> dict:
    """Stints and pit stops for one race, each reported on its own terms.

    Either source can be absent without the other being useless: f1db often
    publishes stops for a race whose timing data has not been cached yet, and
    the reverse happens too. The payload says which is missing rather than
    presenting a half-built strategy as a whole one.
    """
    stops = race_pit_stops(year, round_num)
    stints, realigned = _align_to_stop_sheet(race_stints(year, round_num), stops)

    warnings = []
    if not stints:
        warnings.append(STINTS_UNAVAILABLE)
    if not stops:
        warnings.append(STOPS_UNAVAILABLE)
    if realigned:
        warnings.append(_realigned_note(realigned))

    drivers = _driver_rows(stints, stops, race_results(year, round_num))

    # Stops whose lap matches no stint boundary: reported, never forced.
    attached = {
        (row["driver_code"], stint["end_lap"])
        for row in drivers
        for stint in row["stints"]
        if stint["ended_by_stop"] is not None
    }
    unmatched = [_stop_payload(stop) for stop in stops if (stop.driver_code, stop.lap) not in attached]

    stops_made = sum(driver["stops"] for driver in drivers)
    red_flag_changes = sum(driver["red_flag_changes"] for driver in drivers)

    # The two sources can legitimately disagree, and the gap is the interesting
    # part: the stop sheet is published separately from timing data and is
    # sometimes incomplete for a recent round.
    if stints and stops_made > len(stops):
        warnings.append(_partial_stops_warning(len(stops), stops_made))
    if red_flag_changes:
        warnings.append(_red_flag_note(red_flag_changes))

    logger.info(
        "race_strategy.built",
        year=year,
        round=round_num,
        stints=len(stints),
        published_stops=len(stops),
        stops_made=stops_made,
        red_flag_changes=red_flag_changes,
        unmatched=len(unmatched),
        realigned_drivers=realigned,
    )
    return {
        "year": year,
        "round": round_num,
        "available": bool(stints or stops),
        "has_stints": bool(stints),
        "has_stops": bool(stops),
        "drivers": drivers,
        "stops": [_stop_payload(stop) for stop in stops],
        # Stops the field actually made, from stint boundaries.
        "stops_made": stops_made,
        # Free tyre changes under a suspended race — not pit stops.
        "red_flag_changes": red_flag_changes,
        "unmatched_stops": unmatched,
        "fastest_stop": _fastest_stop(stops),
        "warnings": warnings,
    }
