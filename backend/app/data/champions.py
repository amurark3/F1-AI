"""Champions query service over the local f1db dataset.

Pure read functions that turn f1db rows into plain JSON-ready dicts for the
``/api/champions`` endpoints. Results are cached in-process because the
underlying data only changes when a new f1db release is pulled.

Key f1db facts this relies on (verified against schema v2026.10.0):
  - ``season_driver_standing`` / ``season_constructor_standing`` carry
    ``position_number`` (1 = leader) and a ``championship_won`` boolean. For a
    completed season the leader has ``championship_won = 1``; for the in-progress
    season the leader has ``championship_won = 0`` (title not yet decided).
  - ``championship_won`` turns 1 as soon as a title is mathematically decided,
    rounds left or not (2026: Antonelli after round 19 of 23). ``is_in_progress``
    means the drivers' title is undecided; ``rounds_completed < round_count``
    means the season still runs.
  - Race winners are ``race_data`` rows with ``type = 'RACE_RESULT'`` and
    ``position_number = 1``.
  - A driver's team for a season comes from ``season_entrant_driver``.
  - A driver is printed by ``driver.name`` ("Juan Manuel Fangio", "Carlos Sainz
    Jr."), with ``last_name`` on driver records. Never ``full_name``: it is the
    legal name ("Juan Manuel Fangio Déramo", "Carlos Sainz Vázquez de Castro").
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING

import structlog

from app.data.f1db_source import connect, installed_version

if TYPE_CHECKING:
    import sqlite3

logger = structlog.get_logger()

# Cache computed results. Keyed by the installed f1db version: the refresh loop installs
# releases in a running process, so an unkeyed cache would never show a new title.
_cache: dict[tuple[str | None, str], object] = {}


def _key(name: str) -> tuple[str | None, str]:
    return (installed_version(), name)


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
        SELECT d.id, d.name, d.last_name, d.abbreviation, sds.points, sds.championship_won,
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
        "name": row["name"],
        "last_name": row["last_name"],
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


def _round_counts(conn: sqlite3.Connection, year: int) -> tuple[int, int]:
    """``(round_count, rounds_completed)``: rounds on the calendar, and rounds with a race result."""
    row = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(EXISTS (SELECT 1 FROM race_data rd WHERE rd.race_id = r.id AND rd.type = 'RACE_RESULT')), 0)
        FROM race r WHERE r.year = ?
        """,
        (year,),
    ).fetchone()
    return row[0], row[1]


def _decider(conn: sqlite3.Connection, year: int) -> dict | None:
    """The race that decided the drivers' title."""
    row = conn.execute(
        """
        SELECT r.round, r.date, ci.place_name
        FROM race r LEFT JOIN circuit ci ON ci.id = r.circuit_id
        WHERE r.year = ? AND r.drivers_championship_decider = 1
        """,
        (year,),
    ).fetchone()
    return None if row is None else {"round": row["round"], "date": row["date"], "place": row["place_name"]}


def _age(born: date, on: date) -> dict[str, int]:
    """Whole years and the days since the last birthday (a 29 Feb birthday falls on 1 Mar off leap years)."""
    years = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    year = born.year + years
    leap_day = (born.month, born.day) == (2, 29) and not calendar.isleap(year)
    birthday = date(year, 3, 1) if leap_day else born.replace(year=year)
    return {"years": years, "days": (on - birthday).days}


def _lived(row: sqlite3.Row) -> int | None:
    """Days lived at the title decider, or None without a birth date or a decider."""
    if not row["date_of_birth"] or not row["date"]:
        return None
    return (date.fromisoformat(row["date"]) - date.fromisoformat(row["date_of_birth"])).days


def _age_at_decider(row: sqlite3.Row) -> dict[str, int]:
    return _age(date.fromisoformat(row["date_of_birth"]), date.fromisoformat(row["date"]))


def _title_person(row: sqlite3.Row) -> dict:
    return {"season": row["year"], "name": row["name"], "last_name": row["last_name"]}


def latest_champion() -> dict:
    """The newest decided drivers' title, with the records it sets (age, nationality, count)."""
    cache_key = _key("latest")
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sds.year, d.id, d.name, d.last_name, d.date_of_birth, co.name AS nationality,
                   r.round, r.date, ci.place_name
            FROM season_driver_standing sds
            JOIN driver d ON d.id = sds.driver_id
            LEFT JOIN country co ON co.id = d.nationality_country_id
            LEFT JOIN race r ON r.year = sds.year AND r.drivers_championship_decider = 1
            LEFT JOIN circuit ci ON ci.id = r.circuit_id
            WHERE sds.championship_won = 1
            ORDER BY sds.year
            """
        ).fetchall()
        if not rows:
            return {"error": "No decided drivers' title in f1db"}
        latest, earlier = rows[-1], rows[:-1]
        round_count, rounds_completed = _round_counts(conn, latest["year"])

    lived = _lived(latest)
    dated = [(days, row) for row in earlier if (days := _lived(row)) is not None]
    youngest = min(dated, key=lambda pair: pair[0], default=None)
    compatriot = next(
        (
            row
            for row in reversed(earlier)
            if latest["nationality"] is not None
            and row["nationality"] == latest["nationality"]
            and row["id"] != latest["id"]
        ),
        None,
    )
    result = {
        "season": latest["year"],
        "name": latest["name"],
        "last_name": latest["last_name"],
        "nationality": latest["nationality"],
        "decided_at": None
        if latest["round"] is None
        else {"round": latest["round"], "date": latest["date"], "place": latest["place_name"]},
        "round_count": round_count,
        "rounds_completed": rounds_completed,
        "age": None if lived is None else _age_at_decider(latest),
        "previous_youngest": None
        if youngest is None
        else {**_title_person(youngest[1]), "age": _age_at_decider(youngest[1])},
        "youngest_ever": lived is not None and youngest is not None and lived < youngest[0],
        "previous_compatriot": None if compatriot is None else _title_person(compatriot),
        "title_number": sum(1 for row in rows if row["id"] == latest["id"]),
        "champion_number": len({row["id"] for row in rows}),
    }
    _cache[cache_key] = result
    return result


def list_champions() -> list[dict]:
    """One row per season 1950→latest, newest first."""
    cached = _cache.get(_key("list"))
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        years = [r[0] for r in conn.execute("SELECT year FROM season ORDER BY year DESC")]
        result = []
        for year in years:
            driver = _driver_champion(conn, year)
            round_count, rounds_completed = _round_counts(conn, year)
            result.append(
                {
                    "season": year,
                    "is_in_progress": bool(driver and not driver["title_decided"]),
                    "driver_champion": driver,
                    "constructor_champion": _constructor_champion(conn, year),
                    "round_count": round_count,
                    "rounds_completed": rounds_completed,
                }
            )

    _cache[_key("list")] = result
    logger.info("champions.list_built", seasons=len(result))
    return result


def get_season_detail(year: int) -> dict:
    """Champions plus every race winner for a single season."""
    cache_key = _key(f"detail:{year}")
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
                   d.name AS winner, d.id AS driver_id,
                   con.name AS team, rd.constructor_id AS team_id
            FROM race_data rd
            JOIN race r ON r.id = rd.race_id
            JOIN driver d ON d.id = rd.driver_id
            LEFT JOIN constructor con ON con.id = rd.constructor_id
            WHERE r.year = ? AND rd.type = 'RACE_RESULT' AND rd.position_number = 1
            ORDER BY r.round
            """,
            (year,),
        ).fetchall()

        round_count, rounds_completed = _round_counts(conn, year)
        decided_at = _decider(conn, year)
        driver = _driver_champion(conn, year)
        constructor = _constructor_champion(conn, year)
        runner_up = conn.execute(
            """
            SELECT d.name AS name, d.last_name AS last_name, sds.points
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
        "round_count": round_count,
        "rounds_completed": rounds_completed,
        "decided_at": decided_at,
        "runner_up": (
            {"name": runner_up["name"], "last_name": runner_up["last_name"], "points": float(runner_up["points"])}
            if runner_up
            else None
        ),
        "race_winners": [
            {
                "round": w["round"],
                "race_name": w["race_name"],
                "date": w["date"],
                "winner": w["winner"],
                "driver_id": w["driver_id"],
                "team": w["team"],
                "team_id": w["team_id"],
            }
            for w in winners
        ],
    }
    _cache[cache_key] = detail
    return detail


def get_champion_stats() -> dict:
    """Aggregate leaderboards for the stats/visuals section."""
    cached = _cache.get(_key("stats"))
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect() as conn:
        driver_titles = conn.execute(
            """
            SELECT d.name AS name, d.last_name AS last_name, COUNT(*) AS titles
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
        "most_driver_titles": [
            {"name": r["name"], "last_name": r["last_name"], "titles": r["titles"]} for r in driver_titles
        ],
        "most_constructor_titles": [{"name": r["name"], "titles": r["titles"]} for r in constructor_titles],
    }
    _cache[_key("stats")] = stats
    return stats
