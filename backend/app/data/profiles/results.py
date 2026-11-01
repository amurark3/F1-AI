"""A season's race and sprint results, read once for a team or driver page.

Only grand prix and sprint classifications are read. Qualifying and the grid
already have their own pages, and the profile tables show where a car finished.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from app.data.identity import as_int

if TYPE_CHECKING:
    import sqlite3

SessionKind = Literal["race", "sprint"]

_SESSION_TYPES: dict[str, SessionKind] = {"RACE_RESULT": "race", "SPRINT_RACE_RESULT": "sprint"}

_ROUNDS_QUERY = """
    SELECT r.round AS round, gp.full_name AS name, gp.short_name AS short_name,
           r.date AS date, r.circuit_id AS circuit_id
    FROM race r
    JOIN grand_prix gp ON gp.id = r.grand_prix_id
    WHERE r.year = ?
    ORDER BY r.round
"""

# One statement serves both pages: a NULL filter matches every row.
_RESULTS_QUERY = """
    SELECT r.round AS round, rd.type AS type, rd.driver_id AS driver_id,
           rd.constructor_id AS constructor_id, rd.driver_number AS number,
           rd.position_number AS position, rd.position_text AS position_text,
           rd.race_grid_position_number AS grid, rd.race_points AS points,
           rd.race_positions_gained AS positions_gained,
           rd.race_reason_retired AS reason_retired,
           rd.race_fastest_lap AS fastest_lap, rd.race_pole_position AS pole
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    WHERE r.year = ? AND rd.type IN ('RACE_RESULT', 'SPRINT_RACE_RESULT')
      AND (? IS NULL OR rd.driver_id = ?)
      AND (? IS NULL OR rd.constructor_id = ?)
    ORDER BY r.round, rd.type, rd.position_display_order
"""

_LATEST_RESULT_QUERY = """
    SELECT MAX(r.round) AS round
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    WHERE r.year = ? AND rd.type = 'RACE_RESULT'
"""

# Not starting is not a retirement, though f1db records a reason for both.
_NOT_A_RETIREMENT = frozenset({"DNS", "DSQ", "DNQ", "DNPQ", "EX"})


@dataclass(frozen=True)
class RoundInfo:
    round: int
    name: str
    short_name: str
    date: str
    circuit_id: str


@dataclass(frozen=True)
class Finish:
    """One car's classification in one race or sprint."""

    round: int
    session: SessionKind
    driver_id: str
    constructor_id: str
    number: int | None
    position: int | None
    position_text: str
    grid: int | None
    points: float
    positions_gained: int | None
    reason_retired: str | None
    fastest_lap: bool
    pole: bool

    @property
    def retired(self) -> bool:
        return self.reason_retired is not None and self.position_text not in _NOT_A_RETIREMENT

    def as_dict(self) -> dict:
        payload = asdict(self)
        for key in ("round", "session", "driver_id", "constructor_id"):
            payload.pop(key)
        return payload


def season_rounds(conn: sqlite3.Connection, year: int) -> tuple[RoundInfo, ...]:
    return tuple(
        RoundInfo(
            round=int(row["round"]),
            name=row["name"],
            short_name=row["short_name"] or row["name"],
            date=row["date"],
            circuit_id=row["circuit_id"],
        )
        for row in conn.execute(_ROUNDS_QUERY, (year,)).fetchall()
    )


def season_results(
    conn: sqlite3.Connection,
    year: int,
    *,
    driver_id: str | None = None,
    constructor_id: str | None = None,
) -> tuple[Finish, ...]:
    """Every race and sprint classification of ``year``, optionally filtered."""
    rows = conn.execute(_RESULTS_QUERY, (year, driver_id, driver_id, constructor_id, constructor_id)).fetchall()
    return tuple(
        Finish(
            round=int(row["round"]),
            session=_SESSION_TYPES[row["type"]],
            driver_id=row["driver_id"],
            constructor_id=row["constructor_id"],
            number=as_int(row["number"]),
            position=as_int(row["position"]),
            position_text=row["position_text"] or "",
            grid=as_int(row["grid"]),
            points=float(row["points"] or 0),
            positions_gained=as_int(row["positions_gained"]),
            reason_retired=row["reason_retired"],
            fastest_lap=bool(row["fastest_lap"]),
            pole=bool(row["pole"]),
        )
        for row in rows
    )


def results_through(conn: sqlite3.Connection, year: int, rounds: tuple[RoundInfo, ...]) -> dict | None:
    """The season's latest round with a published race result.

    Season-wide on purpose: a driver who sat out the last race still has
    results "through" it, and the page should say so.
    """
    row = conn.execute(_LATEST_RESULT_QUERY, (year,)).fetchone()
    latest = next((item for item in rounds if item.round == row["round"]), None)
    return {"round": latest.round, "name": latest.name} if latest else None


def rounds_label(rounds: list[int]) -> str:
    """``[1, 2, 3, 7, 9, 10]`` → ``"R1–3, R7, R9–10"``."""
    spans: list[list[int]] = []
    for value in sorted(set(rounds)):
        if spans and value == spans[-1][-1] + 1:
            spans[-1].append(value)
        else:
            spans.append([value])
    return ", ".join(f"R{span[0]}" if len(span) == 1 else f"R{span[0]}–{span[-1]}" for span in spans)
