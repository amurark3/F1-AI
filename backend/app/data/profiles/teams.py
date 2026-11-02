"""A constructor's season: line-up, wins, and every car's result per round.

The line-up is read from race starts, not the entry list, because the entry
list cannot order a mid-season swap. The current drivers are the ones who
started the team's latest race; anyone else who raced for it is listed with
the rounds they raced ("Liam Lawson · R12–14").
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
from app.data.profiles.standings import Standing, season_standings

if TYPE_CHECKING:
    from collections.abc import Mapping
    import sqlite3

_TEAM_QUERY = "SELECT id, name, full_name FROM constructor WHERE id = ?"

_ENTRANTS_QUERY = """
    SELECT DISTINCT sed.driver_id AS id, d.name AS name, d.abbreviation AS code,
           d.permanent_number AS number
    FROM season_entrant_driver sed
    JOIN driver d ON d.id = sed.driver_id
    WHERE sed.year = ? AND sed.constructor_id = ? AND sed.test_driver = 0
    ORDER BY d.name
"""

PODIUM_POSITIONS = 3


@dataclass(frozen=True)
class _Season:
    year: int
    team: sqlite3.Row
    entrants: list[sqlite3.Row]
    rounds: tuple[RoundInfo, ...]
    finishes: tuple[Finish, ...]
    drivers: Mapping[str, Standing]
    standing: Standing | None
    through: dict | None
    #: Which round the championship table is after, whether provisional, and its sources.
    table_meta: dict


def _race_finishes(season: _Season) -> list[Finish]:
    return [item for item in season.finishes if item.session == "race"]


def _current_ids(season: _Season) -> set[str]:
    races = _race_finishes(season)
    if not races:
        return {row["id"] for row in season.entrants}
    latest = max(item.round for item in races)
    return {item.driver_id for item in races if item.round == latest}


def _driver(row: sqlite3.Row, season: _Season, current: set[str]) -> dict:
    races = [item for item in _race_finishes(season) if item.driver_id == row["id"]]
    rounds = [item.round for item in races]
    standing = season.drivers.get(row["id"])
    number = races[-1].number if races and races[-1].number is not None else as_int(row["number"])
    return {
        "id": row["id"],
        "name": row["name"],
        "code": row["code"],
        "number": number,
        "current": row["id"] in current,
        "rounds": rounds,
        "rounds_label": rounds_label(rounds),
        "position": standing.position if standing else None,
        "points": standing.points if standing else 0.0,
        "wins": sum(1 for item in races if item.position == 1),
    }


def _drivers(season: _Season) -> list[dict]:
    current = _current_ids(season)
    raced = {item.driver_id for item in _race_finishes(season)}
    drivers = [_driver(row, season, current) for row in season.entrants if row["id"] in raced or row["id"] in current]
    # Current line-up in championship order, then everyone else by first start.
    return sorted(
        drivers,
        key=lambda item: (
            not item["current"],
            item["position"] is None,
            item["position"] or 0,
            item["rounds"][0] if item["rounds"] else 0,
        ),
    )


def _rounds(season: _Season) -> list[dict]:
    through = season.through["round"] if season.through else 0
    cumulative = 0.0
    payload = []
    for info in season.rounds:
        finishes = [item for item in season.finishes if item.round == info.round]
        complete = info.round <= through
        points = sum(item.points for item in finishes)
        cumulative += points
        by_driver: dict[str, dict] = {}
        for item in finishes:
            entry = by_driver.setdefault(item.driver_id, {"driver_id": item.driver_id, "race": None, "sprint": None})
            entry[item.session] = item.as_dict()
        payload.append(
            {
                "round": info.round,
                "name": info.name,
                "short_name": info.short_name,
                "date": info.date,
                "status": "complete" if complete else "pending",
                "results": list(by_driver.values()),
                "points": points,
                "cumulative_points": cumulative if complete else None,
            }
        )
    return payload


def _wins(season: _Season) -> list[dict]:
    names = {item.round: item for item in season.rounds}
    return [
        {
            "round": item.round,
            "name": names[item.round].name,
            "short_name": names[item.round].short_name,
            "driver_id": item.driver_id,
            "grid": item.grid,
        }
        for item in _race_finishes(season)
        if item.position == 1
    ]


def _payload(season: _Season) -> dict:
    races = _race_finishes(season)
    team = season.team
    return {
        "year": season.year,
        "team": {
            "id": team["id"],
            "name": team["name"],
            "full_name": team["full_name"] or team["name"],
            "color": team_color(team["id"]),
            "position": season.standing.position if season.standing else None,
            "points": season.standing.points if season.standing else sum(item.points for item in season.finishes),
            "wins": sum(1 for item in races if item.position == 1),
            "podiums": sum(1 for item in races if item.position is not None and item.position <= PODIUM_POSITIONS),
            "poles": sum(1 for item in races if item.pole),
        },
        "drivers": _drivers(season),
        "wins": _wins(season),
        "rounds": _rounds(season),
        "results_through": season.through,
        **season.table_meta,
    }


def team_season(year: int, constructor_id: str) -> dict | None:
    """``constructor_id``'s season, or ``None`` when it did not enter ``year``."""
    standings = season_standings(year)
    with connect() as conn:
        team = conn.execute(_TEAM_QUERY, (constructor_id,)).fetchone()
        entrants = conn.execute(_ENTRANTS_QUERY, (year, constructor_id)).fetchall()
        if team is None or not entrants:
            return None
        rounds = season_rounds(conn, year)
        season = _Season(
            year=year,
            team=team,
            entrants=entrants,
            rounds=rounds,
            finishes=season_results(conn, year, constructor_id=constructor_id),
            drivers=standings.drivers,
            standing=standings.teams.get(constructor_id),
            through=results_through(conn, year, rounds),
            table_meta=standings.meta,
        )
    return _payload(season)
