"""A driver's season: every round's result, wins, and the teams they raced for.

Rounds the driver sat out stay in the list with no result, so a seat swap
reads as a gap ("—") rather than silently renumbering the season.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.f1db_source import connect
from app.data.identity import as_int, team_color
from app.data.profiles.results import (
    Finish,
    RoundInfo,
    results_through,
    rounds_label,
    season_results,
    season_rounds,
)
from app.data.profiles.standings import Standing, driver_standings
from app.data.profiles.teams import PODIUM_POSITIONS

if TYPE_CHECKING:
    import sqlite3

_DRIVER_QUERY = """
    SELECT d.id AS id, d.name AS name, d.abbreviation AS code,
           d.permanent_number AS number, cty.name AS nationality
    FROM driver d
    LEFT JOIN country cty ON cty.id = d.nationality_country_id
    WHERE d.id = ?
"""

_ENTRIES_QUERY = """
    SELECT DISTINCT sed.constructor_id AS id, c.name AS name
    FROM season_entrant_driver sed
    JOIN constructor c ON c.id = sed.constructor_id
    WHERE sed.year = ? AND sed.driver_id = ? AND sed.test_driver = 0
    ORDER BY c.name
"""


@dataclass(frozen=True)
class _Season:
    year: int
    driver: sqlite3.Row
    entries: list[sqlite3.Row]
    rounds: tuple[RoundInfo, ...]
    finishes: tuple[Finish, ...]
    standing: Standing | None
    through: dict | None


def _races(season: _Season) -> list[Finish]:
    return [item for item in season.finishes if item.session == "race"]


def _teams(season: _Season) -> list[dict]:
    names = {row["id"]: row["name"] for row in season.entries}
    rounds: dict[str, list[int]] = {}
    for item in _races(season):
        rounds.setdefault(item.constructor_id, []).append(item.round)
    if not rounds:
        rounds = {row["id"]: [] for row in season.entries}
    return [
        {
            "id": team_id,
            "name": names.get(team_id, team_id),
            "color": team_color(team_id),
            "rounds": raced,
            "rounds_label": rounds_label(raced),
        }
        for team_id, raced in rounds.items()
    ]


def _stats(season: _Season) -> dict:
    races = _races(season)
    return {
        "starts": sum(1 for item in races if item.position_text != "DNS"),
        "wins": sum(1 for item in races if item.position == 1),
        "podiums": sum(1 for item in races if item.position is not None and item.position <= PODIUM_POSITIONS),
        "poles": sum(1 for item in races if item.pole),
        "fastest_laps": sum(1 for item in races if item.fastest_lap),
        "retirements": sum(1 for item in races if item.retired),
        "best_finish": min((item.position for item in races if item.position is not None), default=None),
    }


def _rounds(season: _Season) -> list[dict]:
    through = season.through["round"] if season.through else 0
    payload = []
    for info in season.rounds:
        finishes = {item.session: item for item in season.finishes if item.round == info.round}
        race = finishes.get("race")
        sprint = finishes.get("sprint")
        either = race or sprint
        payload.append(
            {
                "round": info.round,
                "name": info.name,
                "short_name": info.short_name,
                "date": info.date,
                "status": "complete" if info.round <= through else "pending",
                "team_id": either.constructor_id if either else None,
                "race": race.as_dict() if race else None,
                "sprint": sprint.as_dict() if sprint else None,
            }
        )
    return payload


def _payload(season: _Season) -> dict:
    races = _races(season)
    teams = _teams(season)
    latest = races[-1] if races else None
    current = next((team for team in teams if latest and team["id"] == latest.constructor_id), teams[0])
    driver = season.driver
    names = {item.round: item for item in season.rounds}
    return {
        "year": season.year,
        "driver": {
            "id": driver["id"],
            "name": driver["name"],
            "code": driver["code"],
            "number": latest.number if latest and latest.number is not None else as_int(driver["number"]),
            "nationality": driver["nationality"],
            "team_id": current["id"],
            "team_name": current["name"],
            "color": current["color"],
        },
        "standing": {
            "position": season.standing.position if season.standing else None,
            "points": season.standing.points if season.standing else sum(item.points for item in season.finishes),
        },
        "stats": _stats(season),
        "teams": teams,
        "wins": [
            {"round": item.round, "name": names[item.round].name, "short_name": names[item.round].short_name}
            for item in races
            if item.position == 1
        ],
        "rounds": _rounds(season),
        "results_through": season.through,
    }


def driver_season(year: int, driver_id: str) -> dict | None:
    """``driver_id``'s season, or ``None`` when they did not race in ``year``."""
    with connect() as conn:
        driver = conn.execute(_DRIVER_QUERY, (driver_id,)).fetchone()
        entries = conn.execute(_ENTRIES_QUERY, (year, driver_id)).fetchall()
        if driver is None or not entries:
            return None
        rounds = season_rounds(conn, year)
        season = _Season(
            year=year,
            driver=driver,
            entries=entries,
            rounds=rounds,
            finishes=season_results(conn, year, driver_id=driver_id),
            standing=driver_standings(conn, year).get(driver_id),
            through=results_through(conn, year, rounds),
        )
    return _payload(season)
