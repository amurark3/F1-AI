"""The championship tables the profile pages show, keyed by f1db id.

The tables are ``current_standings``'s: f1db's last round plus each later
round's published points, keyed by driver code and team name. A profile page
is addressed by f1db id, so:

* **Confirmed** (nothing past f1db): f1db's own tables, read by id. Exact for
  every season, including the past ones where two drivers share a code
  (MON in 2006: Montagny and Monteiro).
* **Provisional** (a later round added): the computed rows, matched to ids
  through the season's entrants. Only a live season is ever provisional.

Either way the payload says which round the table is after and where it came
from (:attr:`SeasonStandings.meta`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.current_standings import current_standings
from app.data.f1db_source import connect

if TYPE_CHECKING:
    from collections.abc import Mapping
    import sqlite3

    from app.data import standings_table

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

# The keys the computed table uses (driver code, f1db team name), mapped to f1db ids.
_DRIVER_IDS_QUERY = """
    SELECT DISTINCT d.abbreviation AS key, d.id AS id
    FROM season_entrant_driver sed
    JOIN driver d ON d.id = sed.driver_id
    WHERE sed.year = ? AND d.abbreviation IS NOT NULL
"""

_CONSTRUCTOR_IDS_QUERY = """
    SELECT DISTINCT c.name AS key, c.id AS id
    FROM season_entrant_driver sed
    JOIN constructor c ON c.id = sed.constructor_id
    WHERE sed.year = ?
"""


@dataclass(frozen=True)
class Standing:
    position: int | None
    points: float


@dataclass(frozen=True)
class SeasonStandings:
    """Both championships by f1db id, and how fresh they are."""

    drivers: Mapping[str, Standing]
    teams: Mapping[str, Standing]
    #: ``as_of_round``, ``provisional`` and ``sources``, as every standings payload carries them.
    meta: dict


def _table(conn: sqlite3.Connection, query: str, year: int) -> dict[str, Standing]:
    return {
        row["id"]: Standing(
            position=int(row["position"]) if row["position"] is not None else None,
            points=float(row["points"] or 0),
        )
        for row in conn.execute(query, (year, year)).fetchall()
    }


def _by_id(
    conn: sqlite3.Connection, query: str, year: int, rows: tuple[standings_table.Standing, ...]
) -> dict[str, Standing]:
    """Computed rows keyed by f1db id; a row the season's entrants cannot name is left out."""
    ids = {row["key"]: row["id"] for row in conn.execute(query, (year,)).fetchall()}
    return {ids[row.key]: Standing(position=row.position, points=row.points) for row in rows if row.key in ids}


def season_standings(year: int) -> SeasonStandings:
    """Both championships of ``year`` as of the newest round with published points."""
    computed = current_standings(year)
    with connect() as conn:
        if computed.provisional:
            drivers = _by_id(conn, _DRIVER_IDS_QUERY, year, computed.drivers)
            teams = _by_id(conn, _CONSTRUCTOR_IDS_QUERY, year, computed.teams)
        else:
            drivers = _table(conn, _DRIVER_QUERY, year)
            teams = _table(conn, _CONSTRUCTOR_QUERY, year)
    return SeasonStandings(drivers=drivers, teams=teams, meta=computed.meta())
