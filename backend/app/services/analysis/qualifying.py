"""Qualifying segments: each driver's best per segment, and the part they reached.

Segment windows come from race control (:func:`~app.data.openf1.race_control.segment_windows`);
a lap belongs to the segment it began in. Segments are never inferred from lap gaps:
a session whose race control publishes no phases stays ungrouped, with a notice.

The part a driver reached follows the **on-road** knock-outs. The classification
(OpenF1 ``session_result``) has a disqualified car removed, which moves every car
behind it up a place; but that car still ran, so it is put back where it qualified
on the road, and the cuts (10 reach Q3; 16 reach Q2, or 15 when 20 or fewer cars ran) are
made on that order. A disqualification never lifts a car into a part it did not run
(Mexico City 2026: Lawson ran Q3, so Hülkenberg, P10 after his DSQ, was out in Q2).
OpenF1 does not flag the disqualification (``dsq`` stays false), so f1db's
``position_text`` "DSQ" says who was disqualified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.f1db_sessions import KIND_QUALIFYING, TYPE_SPRINT_QUALIFYING, session_classification
from app.services.analysis.common import driver_json
from app.services.analysis.lap_selection import fastest_valid_lap, segment_of

if TYPE_CHECKING:
    from app.data.openf1.session_laps import SessionLaps

logger = structlog.get_logger()

LABELS = {"Q": ("Q1", "Q2", "Q3"), "SQ": ("SQ1", "SQ2", "SQ3")}
TYPE_QUALIFYING = "QUALIFYING_RESULT"
F1DB_TYPES = {"Q": TYPE_QUALIFYING, "SQ": TYPE_SPRINT_QUALIFYING}
Q3_SIZE = 10
# Cars through to the second segment: 16 of 21-22 runners (2026), 15 of 20 (2023-25).
Q2_SIZE = 16
SMALL_FIELD = 20
Q2_SIZE_SMALL_FIELD = 15
# OpenF1 and race control publish times to the millisecond.
TIME_TOLERANCE_SECONDS = 0.0015
GROUPS = {3: "q3", 2: "out_q2", 1: "out_q1"}
GROUP_DISQUALIFIED = "disqualified"

Bests = tuple[float | None, float | None, float | None]


def _segment_bests(session: SessionLaps, number: int) -> Bests:
    """The fastest valid lap time in each segment."""
    own = session.laps_of(number)
    best = [fastest_valid_lap(tuple(lap for lap in own if segment_of(lap, session.segments) == n)) for n in (1, 2, 3)]
    times = [None if lap is None else lap.time for lap in best]
    return (times[0], times[1], times[2])


def _same(a: float | None, b: float | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= TIME_TOLERANCE_SECONDS)


def _confirmed(session: SessionLaps, bests: dict[int, Bests], disqualified: set[int]) -> bool:
    """Whether every driver's segment bests are the times OpenF1's classification holds.

    A disqualified car's classification drops times it did set (Lawson's Q1, Mexico City 2026,
    78.097 on the road, null in OpenF1), so a segment it has no classified time in is not checked.
    """
    clean = bool(session.result)
    for row in session.result:
        for index, (ours, theirs) in enumerate(zip(bests.get(row.driver, (None,) * 3), row.durations, strict=True), 1):
            if not _same(ours, theirs) and not (row.driver in disqualified and theirs is None):
                clean = False
                logger.warning(
                    "analysis.qualifying.segment_mismatch",
                    session_key=session.session.session_key,
                    driver=row.driver,
                    segment=index,
                    from_laps=ours,
                    from_classification=theirs,
                )
    return clean


def _disqualified(session: SessionLaps) -> set[int]:
    """Car numbers f1db classifies "DSQ" in this session; none when f1db cannot say."""
    try:
        entries = session_classification(session.year, session.round, F1DB_TYPES[session.session.code], KIND_QUALIFYING)
    except Exception as exc:
        logger.warning("analysis.qualifying.f1db_unavailable", year=session.year, round=session.round, error=str(exc))
        return set()
    codes = {entry.driver_code for entry in entries if entry.position_text == "DSQ"}
    return {number for number, driver in session.drivers.items() if driver.code in codes}


def _key(bests: Bests) -> tuple[int, float]:
    """Where a car ranks on the road: the later the segment it set a time in, the better, then the time."""
    last = max((n for n, time in enumerate(bests, 1) if time is not None), default=0)
    return (-last, bests[last - 1] or 0.0)


def _on_road_order(session: SessionLaps, bests: dict[int, Bests]) -> list[int]:
    """Classified cars in order, with each unclassified one (a disqualified car) put back by its times."""
    cars = [row for row in session.result if row.driver in session.drivers]
    order = [row.driver for row in sorted(cars, key=lambda row: row.position or 0) if row.position is not None]
    for row in cars:
        if row.position is None:
            ahead = (i for i, other in enumerate(order) if _key(bests[other]) > _key(bests[row.driver]))
            order.insert(next(ahead, len(order)), row.driver)
    return order


def _reached(index: int, entries: int) -> int:
    through_q1 = Q2_SIZE if entries > SMALL_FIELD else Q2_SIZE_SMALL_FIELD
    return 3 if index < Q3_SIZE else 2 if index < through_q1 else 1


def _driver_fields(session: SessionLaps, bests: dict[int, Bests], out: set[int]) -> dict[int, dict]:
    order = _on_road_order(session, bests)
    classified = {row.driver: row.position for row in session.result}
    fields = {}
    for index, number in enumerate(order):
        ahead = [
            driver_json(session.drivers[other], session.year)["name"].split()[-1]
            for other in order[:index]
            if other in out
        ]
        position = classified[number]
        reached = _reached(index, len(order))
        note = None
        if ahead and position is not None:
            note = f"P{position} after {' and '.join(f"{name}'s DSQ" for name in ahead)}"
        fields[number] = {
            "segment_reached": reached,
            "group": GROUP_DISQUALIFIED if number in out else GROUPS[reached],
            "disqualified": number in out,
            "classified": position,
            "note": note,
        }
    return fields


def qualifying_view(session: SessionLaps) -> tuple[dict, dict[int, dict]]:
    """The session's segment block, and per-driver fields (best per segment, group) keyed by car number."""
    labels = LABELS[session.session.code]
    if not session.segments:
        return {
            "available": False,
            "labels": list(labels),
            "notice": f"{'/'.join(labels)} not published for this session",
        }, {}
    bests = {number: _segment_bests(session, number) for number in session.drivers}
    disqualified = _disqualified(session)
    block = {
        "available": True,
        "labels": list(labels),
        "windows": [
            {"segment": w.number, "label": labels[w.number - 1], "start": w.start.isoformat(), "end": w.end.isoformat()}
            for w in session.segments
        ],
        "confirmed": _confirmed(session, bests, disqualified),
        "notice": None,
    }
    fields = _driver_fields(session, bests, disqualified)
    return block, {n: {"segment_bests": list(bests[n]), **fields.get(n, {})} for n in session.drivers}
