"""Championship standings sourced from the local f1db dataset.

Replaces the rate-limited live Ergast standings calls (which generated hundreds
of HTTP 429s during dataset collection). f1db carries per-round standings in
``race_driver_standing`` / ``race_constructor_standing``, so both the training
collection (standings *before* a given race) and live inference (latest standings
of a season) can be served from one local file with no API limits.

Note on freshness: f1db is a pinned snapshot, so the current in-progress season is
only as fresh as the last ``f1db_source`` refresh. Callers that need the very
latest in-progress round should fall back to the live API when f1db lacks it.
"""

from __future__ import annotations

import structlog

from app.data.f1db_source import connect

logger = structlog.get_logger()

# (year, round) -> {driver_code: position}
_driver_cache: dict[tuple[int, int], dict[str, int]] = {}
# (year, round) -> [{constructor_name, position}]
_constructor_cache: dict[tuple[int, int], list[dict]] = {}


def _latest_round(conn, year: int) -> int:
    row = conn.execute(
        "SELECT MAX(r.round) FROM race_driver_standing rds "
        "JOIN race r ON r.id = rds.race_id WHERE r.year = ?",
        (year,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def driver_standings_after_round(year: int, round_num: int) -> dict[str, int]:
    """Return ``{driver_code: championship_position}`` as of ``round_num``.

    Returns an empty mapping when that round isn't in the dataset (e.g. before the
    season started, or a round not yet released in the current season).
    """
    if round_num < 1:
        return {}
    cache_key = (year, round_num)
    cached = _driver_cache.get(cache_key)
    if cached is not None:
        return cached

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.abbreviation AS code, rds.position_number AS position
            FROM race_driver_standing rds
            JOIN race r ON r.id = rds.race_id
            JOIN driver d ON d.id = rds.driver_id
            WHERE r.year = ? AND r.round = ? AND d.abbreviation IS NOT NULL
            """,
            (year, round_num),
        ).fetchall()

    result = {row["code"]: int(row["position"]) for row in rows}
    _driver_cache[cache_key] = result
    return result


def constructor_standings_after_round(year: int, round_num: int) -> list[dict]:
    """Return ``[{constructor_name, position}]`` as of ``round_num`` (empty if absent)."""
    if round_num < 1:
        return []
    cache_key = (year, round_num)
    cached = _constructor_cache.get(cache_key)
    if cached is not None:
        return cached

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT con.name AS name, rcs.position_number AS position
            FROM race_constructor_standing rcs
            JOIN race r ON r.id = rcs.race_id
            JOIN constructor con ON con.id = rcs.constructor_id
            WHERE r.year = ? AND r.round = ?
            ORDER BY rcs.position_number
            """,
            (year, round_num),
        ).fetchall()

    result = [{"constructor_name": row["name"], "position": int(row["position"])} for row in rows]
    _constructor_cache[cache_key] = result
    return result


def _season_wins_by_driver_code(conn, year: int) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT d.abbreviation AS code, COUNT(*) AS wins
        FROM race_data rd
        JOIN race r ON r.id = rd.race_id
        JOIN driver d ON d.id = rd.driver_id
        WHERE r.year = ? AND rd.type = 'RACE_RESULT' AND rd.position_number = 1
        GROUP BY d.id
        """,
        (year,),
    ).fetchall()
    return {row["code"]: int(row["wins"]) for row in rows}


def driver_standings_detailed(year: int) -> list[dict]:
    """Rich latest-round driver standings for the UI.

    Each row: ``{code, name, team, position, points, wins, nationality, driver_id}``.
    Empty list when the season isn't in the dataset yet.
    """
    with connect() as conn:
        latest = _latest_round(conn, year)
        if not latest:
            return []
        rows = conn.execute(
            """
            SELECT d.abbreviation AS code, d.name AS name, d.id AS driver_id,
                   rds.position_number AS position, rds.points AS points,
                   con.name AS team, cty.name AS nationality
            FROM race_driver_standing rds
            JOIN race r ON r.id = rds.race_id
            JOIN driver d ON d.id = rds.driver_id
            LEFT JOIN season_entrant_driver sed
                   ON sed.year = r.year AND sed.driver_id = d.id
            LEFT JOIN constructor con ON con.id = sed.constructor_id
            LEFT JOIN country cty ON cty.id = d.nationality_country_id
            WHERE r.year = ? AND r.round = ? AND d.abbreviation IS NOT NULL
            ORDER BY rds.position_number
            """,
            (year, latest),
        ).fetchall()
        wins_by_code = _season_wins_by_driver_code(conn, year)

    result: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        code = row["code"]
        if code in seen:  # a mid-season team change can duplicate the join row
            continue
        seen.add(code)
        result.append({
            "code": code,
            "name": row["name"],
            "team": row["team"] or "",
            "position": int(row["position"]),
            "points": float(row["points"]) if row["points"] is not None else 0.0,
            "wins": wins_by_code.get(code, 0),
            "nationality": row["nationality"] or "",
            "driver_id": row["driver_id"],
        })
    return result


def constructor_standings_detailed(year: int) -> list[dict]:
    """Rich latest-round constructor standings: ``{team, position, points, wins}``."""
    with connect() as conn:
        latest = _latest_round(conn, year)
        if not latest:
            return []
        rows = conn.execute(
            """
            SELECT con.name AS team, rcs.position_number AS position, rcs.points AS points
            FROM race_constructor_standing rcs
            JOIN race r ON r.id = rcs.race_id
            JOIN constructor con ON con.id = rcs.constructor_id
            WHERE r.year = ? AND r.round = ?
            ORDER BY rcs.position_number
            """,
            (year, latest),
        ).fetchall()
        wins_rows = conn.execute(
            """
            SELECT con.name AS team, COUNT(*) AS wins
            FROM race_data rd
            JOIN race r ON r.id = rd.race_id
            JOIN constructor con ON con.id = rd.constructor_id
            WHERE r.year = ? AND rd.type = 'RACE_RESULT' AND rd.position_number = 1
            GROUP BY con.id
            """,
            (year,),
        ).fetchall()
    wins_by_team = {row["team"]: int(row["wins"]) for row in wins_rows}
    return [
        {
            "team": row["team"],
            "position": int(row["position"]),
            "points": float(row["points"]) if row["points"] is not None else 0.0,
            "wins": wins_by_team.get(row["team"], 0),
        }
        for row in rows
    ]


def current_driver_standings(year: int) -> dict[str, int]:
    """Latest available driver standings for a season (for live inference)."""
    with connect() as conn:
        latest = _latest_round(conn, year)
    return driver_standings_after_round(year, latest) if latest else {}


def current_constructor_standings(year: int) -> list[dict]:
    """Latest available constructor standings for a season (for live inference)."""
    with connect() as conn:
        latest = _latest_round(conn, year)
    return constructor_standings_after_round(year, latest) if latest else []
