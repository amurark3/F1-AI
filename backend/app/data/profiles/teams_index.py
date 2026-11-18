"""Every team of a season with its drivers' points split, for the Teams index.

A driver's share is the points scored *for that team* (race and sprint), not
their championship total, so a stand-in's few points stay with the car they
were scored in and a team's drivers add up to its constructor total.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.data.f1db_source import connect
from app.data.identity import team_color
from app.data.profiles.results import Finish, results_through, rounds_label, season_results, season_rounds
from app.data.profiles.standings import season_standings

if TYPE_CHECKING:
    from collections.abc import Mapping
    import sqlite3

    from app.data.profiles.standings import Standing

# A driver who raced for the team counts even if f1db flags them a test driver.
_ENTRANTS_QUERY = """
    SELECT DISTINCT c.id AS team_id, c.name AS team_name, c.full_name AS full_name,
           d.id AS id, d.name AS name, d.last_name AS last_name, d.abbreviation AS code
    FROM season_entrant_driver sed
    JOIN constructor c ON c.id = sed.constructor_id
    JOIN driver d ON d.id = sed.driver_id
    WHERE sed.year = ?
      AND (sed.test_driver = 0 OR EXISTS (
          SELECT 1 FROM race_data rd JOIN race r ON r.id = rd.race_id
          WHERE r.year = sed.year AND rd.driver_id = sed.driver_id
            AND rd.constructor_id = sed.constructor_id
            AND rd.type IN ('RACE_RESULT', 'SPRINT_RACE_RESULT')))
    ORDER BY d.name
"""


def _driver(row: sqlite3.Row, finishes: list[Finish]) -> dict:
    rounds = sorted({item.round for item in finishes if item.session == "race"})
    return {
        "id": row["id"],
        "name": row["name"],
        "last_name": row["last_name"],
        "code": row["code"],
        "points": sum(item.points for item in finishes),
        "rounds": rounds,
        "rounds_label": rounds_label(rounds),
    }


def _team(rows: list[sqlite3.Row], results: tuple[Finish, ...], table: Mapping[str, Standing]) -> dict:
    head = rows[0]
    mine = [item for item in results if item.constructor_id == head["team_id"]]
    raced = {item.driver_id for item in mine}
    # Drivers with a result for the team; its entrants while it has none.
    listed = [row for row in rows if row["id"] in raced] if raced else rows
    drivers = sorted(
        (_driver(row, [item for item in mine if item.driver_id == row["id"]]) for row in listed),
        key=lambda item: (-item["points"], item["rounds"][0] if item["rounds"] else 0, item["name"]),
    )
    standing = table.get(head["team_id"])
    return {
        "id": head["team_id"],
        "name": head["team_name"],
        "full_name": head["full_name"] or head["team_name"],
        "color": team_color(head["team_id"]),
        "position": standing.position if standing else None,
        "points": standing.points if standing else 0,
        "drivers": drivers,
    }


def teams_index(year: int) -> dict:
    """Every team of ``year`` in championship order, each with its drivers' points for it."""
    standings = season_standings(year)
    with connect() as conn:
        rows = conn.execute(_ENTRANTS_QUERY, (year,)).fetchall()
        results = season_results(conn, year)
        through = results_through(conn, year, season_rounds(conn, year))
    by_team: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_team.setdefault(row["team_id"], []).append(row)
    teams = [_team(group, results, standings.teams) for group in by_team.values()]
    teams.sort(key=lambda team: (team["position"] is None, team["position"] or 0, team["name"]))
    return {"year": year, "teams": teams, "results_through": through, **standings.meta}
