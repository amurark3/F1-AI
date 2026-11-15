"""One race (or sprint) classification as f1db publishes it, with every column the Results tab shows.

f1db mirrors the FIA final classification, so a round found here is final.
``race_time`` already includes any time penalty (``race_time_penalty``), so the
place on the road is the order of ``race_time_millis - race_time_penalty_millis``.
``position_number`` is NULL, and ``position_text`` a status word, for every car
the FIA did not classify.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.f1db_source import connect

if TYPE_CHECKING:
    import sqlite3

TYPE_RACE = "RACE_RESULT"
TYPE_SPRINT = "SPRINT_RACE_RESULT"

_RESULT_QUERY = """
    SELECT rd.position_number AS position, rd.position_text AS position_text,
           d.abbreviation AS code, d.name AS name, con.name AS team,
           rd.race_laps AS laps, rd.race_time AS time, rd.race_time_millis AS time_millis,
           rd.race_time_penalty_millis AS penalty_millis,
           rd.race_gap AS gap, rd.race_gap_laps AS gap_laps,
           rd.race_reason_retired AS reason, rd.race_points AS points,
           rd.race_fastest_lap AS fastest_lap
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor con ON con.id = rd.constructor_id
    WHERE r.year = ? AND r.round = ? AND rd.type = ? AND d.abbreviation IS NOT NULL
    ORDER BY rd.position_display_order
"""

_FASTEST_LAP_QUERY = """
    SELECT d.abbreviation AS code, d.name AS name, con.name AS team,
           rd.fastest_lap_lap AS lap, rd.fastest_lap_time AS time
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor con ON con.id = rd.constructor_id
    WHERE r.year = ? AND r.round = ? AND rd.type = 'FASTEST_LAP' AND rd.position_number = 1
"""


@dataclass(frozen=True)
class ResultRow:
    """One car's line of the classification."""

    code: str
    name: str
    team: str
    #: The classified place, ``None`` for a car the FIA did not classify.
    position: int | None
    #: f1db's ``position_text``: "7", or "DNF", "DNS", "DSQ", "NC".
    position_text: str
    laps: int | None
    #: The winner's race time; every other car has a gap instead.
    time: str | None
    time_millis: int | None
    penalty_millis: int | None
    gap: str | None
    gap_laps: int | None
    reason: str | None
    points: float | None
    fastest_lap: bool


@dataclass(frozen=True)
class FastestLap:
    """The race's fastest lap."""

    code: str
    name: str
    team: str
    lap: int | None
    time: str | None


def _row(row: sqlite3.Row) -> ResultRow:
    return ResultRow(
        code=row["code"],
        name=row["name"],
        team=row["team"],
        position=row["position"],
        position_text=str(row["position_text"]).strip().upper(),
        laps=row["laps"],
        time=row["time"],
        time_millis=row["time_millis"],
        penalty_millis=row["penalty_millis"],
        gap=row["gap"],
        gap_laps=row["gap_laps"],
        reason=row["reason"],
        points=row["points"],
        fastest_lap=bool(row["fastest_lap"]),
    )


def result_rows(year: int, round_num: int, result_type: str = TYPE_RACE) -> tuple[ResultRow, ...]:
    """The round's classification in f1db's order; empty when f1db does not hold it."""
    with connect() as conn:
        return tuple(_row(row) for row in conn.execute(_RESULT_QUERY, (year, round_num, result_type)))


def fastest_lap(year: int, round_num: int) -> FastestLap | None:
    """The race's fastest lap, or ``None`` when f1db has no such row (a sprint has none)."""
    with connect() as conn:
        row = conn.execute(_FASTEST_LAP_QUERY, (year, round_num)).fetchone()
    if row is None:
        return None
    return FastestLap(code=row["code"], name=row["name"], team=row["team"], lap=row["lap"], time=row["time"])
