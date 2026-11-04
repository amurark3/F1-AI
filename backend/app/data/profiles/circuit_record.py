"""A circuit's record in f1db: its layout and the Grands Prix it has hosted.

The Command Center's circuit panels read three things from here:

* the layout this round runs on — length, turns, direction, laps, distance —
  taken from the round's own ``race`` row, falling back to the ``circuit`` row
  where f1db has not filled the round in yet;
* the recent editions: who won, from which grid slot, and who took pole;
  each person by f1db's ``name`` and ``last_name`` (the surname as f1db
  stores it, "Sainz Jr." or "De Vries", so no client splits a name);
* how often pole became the win, and which of this season's race drivers have
  won here before.

History is every earlier race at the same ``circuit_id`` with a published
result — matched on the circuit, never the event name (see circuit_history.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.data.f1db_source import connect

if TYPE_CHECKING:
    import sqlite3

# Editions listed, and the sample the pole-to-win rate is measured over.
DEFAULT_EDITIONS = 10
# This season's drivers listed among past winners here.
ACTIVE_WINNER_ROWS = 3
DIRECTIONS = {"CLOCKWISE": "clockwise", "ANTI_CLOCKWISE": "anti-clockwise"}

_ROUND_QUERY = """
    SELECT r.circuit_id, r.laps, r.distance,
           COALESCE(r.course_length, c.length) AS length,
           COALESCE(r.turns, c.turns) AS turns,
           COALESCE(r.direction, c.direction) AS direction,
           c.full_name AS name, c.place_name AS place
    FROM race r
    JOIN circuit c ON c.id = r.circuit_id
    WHERE r.year = ? AND r.round = ?
"""

# Every query below selects the earlier races here that have a published result,
# with the parameters (circuit, year, year, round) in that order.

_SPAN_QUERY = """
    SELECT MIN(r.year) AS first_year, COUNT(*) AS races FROM race r
    WHERE r.circuit_id = ? AND (r.year < ? OR (r.year = ? AND r.round < ?))
      AND EXISTS (SELECT 1 FROM race_data rd WHERE rd.race_id = r.id AND rd.type = 'RACE_RESULT')
"""

_EDITIONS_QUERY = """
    SELECT r.id AS id, r.year AS year FROM race r
    WHERE r.circuit_id = ? AND (r.year < ? OR (r.year = ? AND r.round < ?))
      AND EXISTS (SELECT 1 FROM race_data rd WHERE rd.race_id = r.id AND rd.type = 'RACE_RESULT')
    ORDER BY r.year DESC, r.round DESC
    LIMIT ?
"""

# The winner and pole sitter of each race the editions query picks; the race
# list is the same subquery with the same parameters, so the two agree.
_HEADLINERS_QUERY = """
    SELECT rd.race_id AS race_id, rd.driver_id AS driver_id, d.name AS driver_name,
           d.last_name AS last_name, rd.constructor_id AS team_id, c.name AS team_name,
           rd.position_number AS position, rd.race_grid_position_number AS grid,
           rd.race_pole_position AS pole
    FROM race_data rd
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor c ON c.id = rd.constructor_id
    WHERE rd.type = 'RACE_RESULT'
      AND (rd.position_number = 1 OR rd.race_pole_position = 1)
      AND rd.race_id IN (
          SELECT r.id FROM race r
          WHERE r.circuit_id = ? AND (r.year < ? OR (r.year = ? AND r.round < ?))
            AND EXISTS (SELECT 1 FROM race_data x WHERE x.race_id = r.id AND x.type = 'RACE_RESULT')
          ORDER BY r.year DESC, r.round DESC
          LIMIT ?
      )
"""

_ACTIVE_WINNERS_QUERY = """
    SELECT rd.driver_id AS driver_id, d.name AS driver_name, d.last_name AS last_name,
           COUNT(*) AS wins, MAX(r.year) AS last_win
    FROM race r
    JOIN race_data rd ON rd.race_id = r.id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.circuit_id = ? AND (r.year < ? OR (r.year = ? AND r.round < ?))
      AND rd.type = 'RACE_RESULT' AND rd.position_number = 1
      AND rd.driver_id IN (
          SELECT driver_id FROM season_entrant_driver WHERE year = ? AND test_driver = 0
      )
    GROUP BY rd.driver_id, d.name, d.last_name
    ORDER BY wins DESC, last_win DESC
    LIMIT ?
"""


def _person(row: sqlite3.Row) -> dict:
    return {
        "driver_id": row["driver_id"],
        "driver_name": row["driver_name"],
        "last_name": row["last_name"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
    }


def _edition(year: int, rows: list[sqlite3.Row]) -> dict:
    winner = next((row for row in rows if row["position"] == 1), None)
    pole = next((row for row in rows if row["pole"]), None)
    return {
        "year": year,
        "winner": {**_person(winner), "grid": winner["grid"]} if winner else None,
        "pole": _person(pole) if pole else None,
        "won_from_pole": bool(winner and winner["pole"]),
    }


def _editions(conn: sqlite3.Connection, earlier: tuple, limit: int) -> list[dict]:
    races = conn.execute(_EDITIONS_QUERY, (*earlier, limit)).fetchall()
    rows = conn.execute(_HEADLINERS_QUERY, (*earlier, limit)).fetchall()
    return [_edition(int(race["year"]), [row for row in rows if row["race_id"] == race["id"]]) for race in races]


def _active_winners(conn: sqlite3.Connection, earlier: tuple, year: int) -> list[dict]:
    rows = conn.execute(_ACTIVE_WINNERS_QUERY, (*earlier, year, ACTIVE_WINNER_ROWS)).fetchall()
    return [
        {
            "driver_id": row["driver_id"],
            "driver_name": row["driver_name"],
            "last_name": row["last_name"],
            "wins": int(row["wins"]),
            "last_win": int(row["last_win"]),
        }
        for row in rows
    ]


def circuit_record(year: int, round_num: int, editions: int = DEFAULT_EDITIONS) -> dict | None:
    """The circuit ``year``/``round_num`` runs on and its history before it; None for an unknown round."""
    with connect() as conn:
        layout = conn.execute(_ROUND_QUERY, (year, round_num)).fetchone()
        if layout is None:
            return None
        earlier = (layout["circuit_id"], year, year, round_num)
        span = conn.execute(_SPAN_QUERY, earlier).fetchone()
        history = _editions(conn, earlier, editions)
        winners = _active_winners(conn, earlier, year)
    with_pole = [edition for edition in history if edition["pole"]]
    return {
        "circuit_id": layout["circuit_id"],
        "name": layout["name"],
        "place": layout["place"],
        "length_km": layout["length"],
        "turns": layout["turns"],
        "direction": DIRECTIONS.get(layout["direction"]),
        "laps": layout["laps"],
        "distance_km": layout["distance"],
        "first_year": span["first_year"],
        "races_held": int(span["races"]),
        "pole_conversion": {
            "wins_from_pole": sum(1 for edition in with_pole if edition["won_from_pole"]),
            "editions": len(with_pole),
        },
        "editions": history,
        "active_winners": winners,
    }
