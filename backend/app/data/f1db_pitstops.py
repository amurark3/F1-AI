"""Race pit stops from the local f1db dataset.

f1db records each stop under ``race_data.type = 'PIT_STOP'`` with the lap it
happened on, which stop of the race it was for that driver, and the stationary
time. The stationary time is the part worth showing: it is the crew's work,
separate from the pit-lane transit that dominates the lap-time loss.

De-duplication is deliberate, not defensive habit. The 2023–2025 seasons are
clean — every row is a distinct (driver, stop) pair — but the in-progress 2026
release carries nine duplicated rows, identical in lap and time but written
under different ``position_display_order`` values. Rendered straight, a driver
appears to have stopped twice on the same lap. Collapsing on (driver, stop)
keeps a data-quality artifact from reading as a race event.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.f1db_source import connect

logger = structlog.get_logger()

_PIT_STOP_QUERY = """
    SELECT d.abbreviation AS code,
           rd.pit_stop_stop AS stop,
           rd.pit_stop_lap AS lap,
           rd.pit_stop_time AS time,
           rd.pit_stop_time_millis AS millis
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ? AND r.round = ? AND rd.type = 'PIT_STOP'
      AND d.abbreviation IS NOT NULL
    ORDER BY rd.pit_stop_lap, rd.pit_stop_stop
"""


@dataclass(frozen=True)
class PitStop:
    """One stop: which lap, which stop of the race, and how long stationary."""

    driver_code: str
    #: Which stop of the race this was for the driver, counting from 1.
    stop: int
    lap: int
    #: Stationary time as published, e.g. ``"24.681"`` or ``"1:14.773"``.
    time: str | None
    #: The same duration in milliseconds, for ranking.
    millis: int | None


def race_pit_stops(year: int, round_num: int) -> tuple[PitStop, ...]:
    """Every pit stop of a race, earliest lap first.

    Returns an empty tuple when f1db holds no stops for the round — the normal
    state for a race that has not run.
    """
    with connect() as conn:
        rows = conn.execute(_PIT_STOP_QUERY, (year, round_num)).fetchall()

    seen: set[tuple[str, int]] = set()
    stops: list[PitStop] = []
    for row in rows:
        if row["stop"] is None or row["lap"] is None:
            continue
        key = (row["code"], int(row["stop"]))
        if key in seen:
            continue
        seen.add(key)
        stops.append(
            PitStop(
                driver_code=row["code"],
                stop=int(row["stop"]),
                lap=int(row["lap"]),
                time=(row["time"] or "").strip() or None,
                millis=None if row["millis"] is None else int(row["millis"]),
            )
        )

    dropped = len(rows) - len(stops)
    if dropped:
        logger.info("f1db_pitstops.duplicates_collapsed", year=year, round=round_num, dropped=dropped)

    logger.info("f1db_pitstops.loaded", year=year, round=round_num, stops=len(stops))
    return tuple(stops)
