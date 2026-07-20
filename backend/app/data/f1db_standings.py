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
