"""The previous grand prix at a round's circuit: who won it and who took pole.

Matched on f1db's ``circuit_id``, which is stable across seasons, not on the
event name — "Mexico City GP" and "Mexican GP" are one circuit. The latest
earlier edition with a published result is used, so a circuit that skipped a
year still has history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.data.f1db_source import connect

if TYPE_CHECKING:
    import sqlite3

_CIRCUIT_QUERY = "SELECT circuit_id FROM race WHERE year = ? AND round = ?"

_PREVIOUS_QUERY = """
    SELECT r.id AS id, r.year AS year, r.round AS round, gp.full_name AS name
    FROM race r
    JOIN grand_prix gp ON gp.id = r.grand_prix_id
    WHERE r.circuit_id = ? AND r.year < ?
      AND EXISTS (SELECT 1 FROM race_data rd WHERE rd.race_id = r.id AND rd.type = 'RACE_RESULT')
    ORDER BY r.year DESC, r.round DESC
    LIMIT 1
"""

_HEADLINE_QUERY = """
    SELECT rd.driver_id AS driver_id, d.name AS driver_name,
           rd.constructor_id AS team_id, c.name AS team_name,
           rd.position_number AS position, rd.race_pole_position AS pole
    FROM race_data rd
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor c ON c.id = rd.constructor_id
    WHERE rd.race_id = ? AND rd.type = 'RACE_RESULT'
      AND (rd.position_number = 1 OR rd.race_pole_position = 1)
"""


def _person(row: sqlite3.Row) -> dict:
    return {
        "driver_id": row["driver_id"],
        "driver_name": row["driver_name"],
        "team_id": row["team_id"],
        "team_name": row["team_name"],
    }


def previous_edition(year: int, round_num: int) -> dict | None:
    """The last race at ``year``/``round_num``'s circuit before ``year``."""
    with connect() as conn:
        circuit = conn.execute(_CIRCUIT_QUERY, (year, round_num)).fetchone()
        if circuit is None:
            return None
        race = conn.execute(_PREVIOUS_QUERY, (circuit["circuit_id"], year)).fetchone()
        if race is None:
            return None
        rows = conn.execute(_HEADLINE_QUERY, (race["id"],)).fetchall()
    winner = next((row for row in rows if row["position"] == 1), None)
    pole = next((row for row in rows if row["pole"]), None)
    return {
        "year": int(race["year"]),
        "round": int(race["round"]),
        "name": race["name"],
        "winner": _person(winner) if winner else None,
        "pole": _person(pole) if pole else None,
    }
