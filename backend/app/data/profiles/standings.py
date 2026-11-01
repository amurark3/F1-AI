"""The latest published championship tables, keyed by f1db id.

``f1db_standings`` keys its tables by code and display name, which is right for
the standings screen and wrong for a page addressed by id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

_DRIVER_QUERY = """
    SELECT rds.driver_id AS id, rds.position_number AS position, rds.points AS points
    FROM race_driver_standing rds
    JOIN race r ON r.id = rds.race_id
    WHERE r.year = ? AND r.round = (
        SELECT MAX(r2.round)
        FROM race_driver_standing rds2
        JOIN race r2 ON r2.id = rds2.race_id
        WHERE r2.year = ?
    )
"""

_CONSTRUCTOR_QUERY = """
    SELECT rcs.constructor_id AS id, rcs.position_number AS position, rcs.points AS points
    FROM race_constructor_standing rcs
    JOIN race r ON r.id = rcs.race_id
    WHERE r.year = ? AND r.round = (
        SELECT MAX(r2.round)
        FROM race_constructor_standing rcs2
        JOIN race r2 ON r2.id = rcs2.race_id
        WHERE r2.year = ?
    )
"""


@dataclass(frozen=True)
class Standing:
    position: int | None
    points: float


def _table(conn: sqlite3.Connection, query: str, year: int) -> dict[str, Standing]:
    return {
        row["id"]: Standing(
            position=int(row["position"]) if row["position"] is not None else None,
            points=float(row["points"] or 0),
        )
        for row in conn.execute(query, (year, year)).fetchall()
    }


def driver_standings(conn: sqlite3.Connection, year: int) -> dict[str, Standing]:
    return _table(conn, _DRIVER_QUERY, year)


def constructor_standings(conn: sqlite3.Connection, year: int) -> dict[str, Standing]:
    return _table(conn, _CONSTRUCTOR_QUERY, year)
