"""Race session results sourced from the local f1db dataset.

Replaces the FastF1 session loads used during training-data collection. FastF1's
``.load()`` internally hits the rate-limited jolpi/Ergast mirror for
results/qualifying/sprint data, so on a cold cache (e.g. a CI runner) it triggers
a 429 storm. f1db carries the same classified positions in ``race_data`` and can
be queried offline with no API at all.

Position semantics match the old FastF1 path: ``position_number`` is set for every
classified driver (including retirements that completed enough laps); truly
unclassified entries (DNF/NC/DNS) have a NULL ``position_number`` and are excluded,
exactly as the FastF1 code filtered ``NaN`` positions.
"""

from __future__ import annotations

from typing import Literal

import structlog

from app.data.f1db_source import connect

logger = structlog.get_logger()


def race_schedule(year: int) -> list[dict]:
    """Return the season's rounds as ``[{round, name, location}]``.

    ``location`` is f1db's stable ``circuit_id`` (e.g. ``"monaco"``) — a better
    circuit-history key than a display string because it is constant across seasons.
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.round AS round, gp.name AS name, r.circuit_id AS location
            FROM race r
            JOIN grand_prix gp ON gp.id = r.grand_prix_id
            WHERE r.year = ?
            ORDER BY r.round
            """,
            (year,),
        ).fetchall()
    return [{"round": int(r["round"]), "name": r["name"], "location": r["location"]} for r in rows]


# The two orderings this module queries by, as complete literal statements.
#
# A column name cannot be a bound parameter, so selecting the ordering at all
# would mean interpolating an identifier into SQL. Both finished statements are
# written out instead: nothing is assembled at runtime, `PositionColumn` is a
# closed type, and there is no code path that can produce a third query.
PositionColumn = Literal["position_number", "position_display_order"]

_QUERY_BY_POSITION_NUMBER = """
    SELECT d.abbreviation AS code, rd.position_number AS position
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ? AND r.round = ? AND rd.type = ?
      AND rd.position_number IS NOT NULL AND d.abbreviation IS NOT NULL
"""

_QUERY_BY_DISPLAY_ORDER = """
    SELECT d.abbreviation AS code, rd.position_display_order AS position
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    WHERE r.year = ? AND r.round = ? AND rd.type = ?
      AND rd.position_display_order IS NOT NULL AND d.abbreviation IS NOT NULL
"""

_POSITION_QUERIES: dict[PositionColumn, str] = {
    "position_number": _QUERY_BY_POSITION_NUMBER,
    "position_display_order": _QUERY_BY_DISPLAY_ORDER,
}


def _positions_by_type(year: int, round_num: int, result_type: str, column: PositionColumn) -> dict[str, int]:
    """Return ``{driver_code: position}`` for one session type of a race.

    ``column`` selects the ordering: ``position_number`` (classified only) or
    ``position_display_order`` (every entrant, ranked, DNFs included).
    """
    with connect() as conn:
        rows = conn.execute(
            _POSITION_QUERIES[column],
            (year, round_num, result_type),
        ).fetchall()
    return {r["code"]: int(r["position"]) for r in rows}


def qualifying_positions(year: int, round_num: int) -> dict[str, int]:
    """{driver_code: qualifying_position} for a race weekend (classified quali order)."""
    return _positions_by_type(year, round_num, "QUALIFYING_RESULT", "position_number")


def race_results(year: int, round_num: int) -> dict[str, int]:
    """{driver_code: finishing_position} for a completed race.

    Uses ``position_display_order`` so every entrant gets a finishing position —
    including retirements, ranked by official classification — matching the old
    FastF1 behaviour where DNFs still received a classified position.
    """
    return _positions_by_type(year, round_num, "RACE_RESULT", "position_display_order")


def sprint_positions(year: int, round_num: int) -> dict[str, int]:
    """{driver_code: sprint_finish_position}, empty if no sprint that weekend."""
    return _positions_by_type(year, round_num, "SPRINT_RACE_RESULT", "position_display_order")


def driver_teams(year: int, round_num: int) -> dict[str, str]:
    """{driver_code: constructor_name} for a race weekend."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.abbreviation AS code, con.name AS team
            FROM race_data rd
            JOIN race r ON r.id = rd.race_id
            JOIN driver d ON d.id = rd.driver_id
            JOIN constructor con ON con.id = rd.constructor_id
            WHERE r.year = ? AND r.round = ? AND rd.type = 'RACE_RESULT'
              AND d.abbreviation IS NOT NULL
            """,
            (year, round_num),
        ).fetchall()
    return {r["code"]: r["team"] for r in rows}


def race_retirements(year: int, round_num: int) -> dict[str, str | None]:
    """``{driver_code: race_reason_retired}`` for every race entrant.

    The reason is ``None`` for classified finishers and a retirement cause
    (e.g. ``"Accident"``, ``"Engine"``) for DNFs — enough to profile a driver's
    reliability/incident history.
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.abbreviation AS code, rd.race_reason_retired AS reason
            FROM race_data rd
            JOIN race r ON r.id = rd.race_id
            JOIN driver d ON d.id = rd.driver_id
            WHERE r.year = ? AND r.round = ? AND rd.type = 'RACE_RESULT'
              AND d.abbreviation IS NOT NULL
            """,
            (year, round_num),
        ).fetchall()
    return {r["code"]: r["reason"] for r in rows}
