"""Champions query service over the local f1db dataset.

Pure read functions that turn f1db rows into plain JSON-ready dicts for the
``/api/champions`` endpoints. Results are cached in-process because the
underlying data only changes when a new f1db release is pulled.

Key f1db facts this relies on (verified against schema v2026.10.0):
  - ``season_driver_standing`` / ``season_constructor_standing`` carry
    ``position_number`` (1 = leader) and a ``championship_won`` boolean. For a
    completed season the leader has ``championship_won = 1``; for the in-progress
    season the leader has ``championship_won = 0`` (title not yet decided).
  - Race winners are ``race_data`` rows with ``type = 'RACE_RESULT'`` and
    ``position_number = 1``.
  - A driver's team for a season comes from ``season_entrant_driver``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.f1db_source import connect

if TYPE_CHECKING:
    import sqlite3

logger = structlog.get_logger()

# Cache computed results — the dataset is static between f1db refreshes.
_cache: dict[str, object] = {}


def _rounds_count(rounds_text: str | None) -> int:
    """f1db stores a driver's rounds as a ``'1;2;3'`` string — count the entries."""
    if not rounds_text:
        return 0
    return len([r for r in str(rounds_text).split(";") if r.strip()])


def _champion_team(conn: sqlite3.Connection, year: int, driver_id: str) -> str | None:
    """The constructor a driver raced most rounds for in a season (their title team)."""
    rows = conn.execute(
        """
        SELECT con.name AS team, sed.rounds_text AS rounds
        FROM season_entrant_driver sed
        JOIN constructor con ON con.id = sed.constructor_id
        WHERE sed.year = ? AND sed.driver_id = ? AND sed.test_driver = 0
        """,
        (year, driver_id),
    ).fetchall()
    if not rows:
        return None
    return max(rows, key=lambda r: _rounds_count(r["rounds"]))["team"]


def _driver_wins(conn: sqlite3.Connection, year: int, driver_id: str) -> int:
    return conn.execute(
        """
        SELECT COUNT(*) FROM race_data rd
        JOIN race r ON r.id = rd.race_id
        WHERE r.year = ? AND rd.type = 'RACE_RESULT'
          AND rd.position_number = 1 AND rd.driver_id = ?
        """,
        (year, driver_id),
    ).fetchone()[0]


def _driver_champion(conn: sqlite3.Connection, year: int) -> dict | None:
    row = conn.execute(
        """
        SELECT d.id, d.full_name, d.abbreviation, sds.points, sds.championship_won,
               co.name AS nationality
        FROM season_driver_standing sds
        JOIN driver d ON d.id = sds.driver_id
        LEFT JOIN country co ON co.id = d.nationality_country_id
        WHERE sds.year = ? AND sds.position_number = 1
        """,
        (year,),
    ).fetchone()
    if row is None:
        return None
    return {
        "name": row["full_name"],
        "code": row["abbreviation"],
        "team": _champion_team(conn, year, row["id"]),
        "points": float(row["points"]) if row["points"] is not None else 0.0,
        "wins": _driver_wins(conn, year, row["id"]),
        "nationality": row["nationality"],
        "title_decided": bool(row["championship_won"]),
    }


def _constructor_champion(conn: sqlite3.Connection, year: int) -> dict | None:
    row = conn.execute(
        """
        SELECT con.name, scs.points, scs.championship_won
        FROM season_constructor_standing scs
        JOIN constructor con ON con.id = scs.constructor_id
        WHERE scs.year = ? AND scs.position_number = 1
        """,
        (year,),
    ).fetchone()
    if row is None:
        return None  # constructors' title only exists from 1958
    return {
        "name": row["name"],
        "points": float(row["points"]) if row["points"] is not None else 0.0,
        "title_decided": bool(row["championship_won"]),
    }


def list_champions() -> list[dict]:
    """One row per season 1950→latest, newest first."""
    cached = _cache.get("list")
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        years = [r[0] for r in conn.execute("SELECT year FROM season ORDER BY year DESC")]
        result = []
        for year in years:
            driver = _driver_champion(conn, year)
            result.append(
                {
                    "season": year,
                    "is_in_progress": bool(driver and not driver["title_decided"]),
                    "driver_champion": driver,
                    "constructor_champion": _constructor_champion(conn, year),
                    "round_count": conn.execute("SELECT COUNT(*) FROM race WHERE year = ?", (year,)).fetchone()[0],
                }
            )

    _cache["list"] = result
    logger.info("champions.list_built", seasons=len(result))
    return result


def get_season_detail(year: int) -> dict:
    """Champions plus every race winner for a single season."""
    cache_key = f"detail:{year}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM season WHERE year = ?", (year,)).fetchone()
        if exists is None:
            return {"error": f"No F1 season found for {year}"}

        winners = conn.execute(
            """
            SELECT r.round, r.official_name AS race_name, r.date,
                   d.full_name AS winner, con.name AS team
            FROM race_data rd
            JOIN race r ON r.id = rd.race_id
            JOIN driver d ON d.id = rd.driver_id
            LEFT JOIN constructor con ON con.id = rd.constructor_id
            WHERE r.year = ? AND rd.type = 'RACE_RESULT' AND rd.position_number = 1
            ORDER BY r.round
            """,
            (year,),
        ).fetchall()

        driver = _driver_champion(conn, year)
        constructor = _constructor_champion(conn, year)
        runner_up = conn.execute(
            """
            SELECT d.full_name AS name, sds.points
            FROM season_driver_standing sds
            JOIN driver d ON d.id = sds.driver_id
            WHERE sds.year = ? AND sds.position_number = 2
            """,
            (year,),
        ).fetchone()

    detail = {
        "season": year,
        "is_in_progress": bool(driver and not driver["title_decided"]),
        "driver_champion": driver,
        "constructor_champion": constructor,
        "runner_up": ({"name": runner_up["name"], "points": float(runner_up["points"])} if runner_up else None),
        "race_winners": [
            {
                "round": w["round"],
                "race_name": w["race_name"],
                "date": w["date"],
                "winner": w["winner"],
                "team": w["team"],
            }
            for w in winners
        ],
    }
    _cache[cache_key] = detail
    return detail


def get_champion_stats() -> dict:
    """Aggregate leaderboards for the stats/visuals section."""
    cached = _cache.get("stats")
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        driver_titles = conn.execute(
            """
            SELECT d.full_name AS name, COUNT(*) AS titles
            FROM season_driver_standing sds
            JOIN driver d ON d.id = sds.driver_id
            WHERE sds.championship_won = 1
            GROUP BY sds.driver_id
            ORDER BY titles DESC, name
            LIMIT 15
            """
        ).fetchall()
        constructor_titles = conn.execute(
            """
            SELECT con.name AS name, COUNT(*) AS titles
            FROM season_constructor_standing scs
            JOIN constructor con ON con.id = scs.constructor_id
            WHERE scs.championship_won = 1
            GROUP BY scs.constructor_id
            ORDER BY titles DESC, name
            LIMIT 15
            """
        ).fetchall()

    stats = {
        "most_driver_titles": [{"name": r["name"], "titles": r["titles"]} for r in driver_titles],
        "most_constructor_titles": [{"name": r["name"], "titles": r["titles"]} for r in constructor_titles],
    }
    _cache["stats"] = stats
    return stats
