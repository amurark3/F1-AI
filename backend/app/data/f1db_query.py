"""Guarded read-only SQL access to the local f1db dataset.

Powers the text-to-SQL tool: the model writes a SELECT against the f1db
schema and this module executes it safely.  The whole of F1 history
(1950–present) is queryable, so the assistant can answer questions no
hand-written tool anticipates.

Safety layers (defense in depth):
  1. The connection is opened ``mode=ro`` — SQLite itself rejects any write.
  2. Only a single ``SELECT`` / ``WITH`` statement is accepted; a denylist of
     mutating keywords is rejected before execution.
  3. A row cap is enforced (appended as ``LIMIT`` when absent) and a wall-clock
     budget aborts runaway queries via a progress handler.
"""

from __future__ import annotations

from collections import Counter
import re
import time

from app.data.f1db_source import connect

DEFAULT_MAX_ROWS = 50
DEFAULT_TIMEOUT_SECONDS = 5.0

# Mutating / dangerous keywords — rejected even though the connection is
# read-only, so the model gets a clear error rather than a SQLite exception.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|"
    r"pragma|vacuum|reindex|analyze|truncate|grant|revoke)\b",
    re.IGNORECASE,
)
_HAS_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)

# Compact, LLM-facing schema.  Kept curated (not the full 31 tables) so the
# model sees the useful surface without noise.  Included verbatim in the tool
# docstring the model reads before writing SQL.
F1DB_SCHEMA_DOC = """\
f1db SQLite (read-only, 1950-present). All *_id are lowercase slugs, e.g.
driver_id='max-verstappen', constructor_id='ferrari', circuit_id='monza',
grand_prix_id='monaco'.

TABLES (key columns):
- race(id, year, round, date, grand_prix_id, circuit_id, official_name)
- circuit(id, name, type, place_name, country_id)
- driver(id, name, abbreviation, nationality_country_id, total_race_wins,
    total_podiums, total_pole_positions, total_points, total_championship_wins,
    total_race_starts)
- constructor(id, name, total_race_wins, total_pole_positions,
    total_championship_wins, total_points)
- race_data(race_id, type, position_number, position_text, driver_id,
    constructor_id, race_points, race_grid_position_number,
    race_positions_gained, race_reason_retired, qualifying_q1/q2/q3)
- season_driver_standing(year, position_number, driver_id, points, championship_won)
- season_constructor_standing(year, position_number, constructor_id, points, championship_won)
- race_driver_standing(race_id, position_number, driver_id, points)  -- per-round

RULES:
- race_data = every session result; ALWAYS filter by `type`: RACE_RESULT,
  QUALIFYING_RESULT, SPRINT_RACE_RESULT, STARTING_GRID_POSITION, FASTEST_LAP, PIT_STOP.
- Join race_data.race_id = race.id for year/round/circuit filters.
- position_number: 1 = winner/pole; NULL for DNF/DNS/DSQ (see position_text).
- WIN: type='RACE_RESULT' AND position_number=1. POLE: type='QUALIFYING_RESULT' AND position_number=1.
- Season champion: season_driver_standing WHERE championship_won=1.
- For career totals prefer driver/constructor lifetime columns (total_*).
- Driver name from id: JOIN driver ON driver.id = race_data.driver_id.
- Naming a driver in a result? ALSO select the team they drove for in that race:
  JOIN constructor c ON c.id = d.constructor_id (with race_data as d). race_data
  holds the team per race, so it is right even after a mid-season switch. Teams
  change every year — never state one from memory.
- Mentioning points? SELECT d.race_points for those rows — it holds what each
  RACE_RESULT and SPRINT_RACE_RESULT row scored. Never work points out from
  memory: the scales change (a sprint win paid 3 points in 2021, more today).

EXAMPLE — each 2025 race winner, with their team and points:
  SELECT r.round, dr.name AS driver, c.name AS team, d.race_points
  FROM race_data d JOIN race r ON r.id=d.race_id
  JOIN driver dr ON dr.id=d.driver_id JOIN constructor c ON c.id=d.constructor_id
  WHERE r.year=2025 AND d.type='RACE_RESULT' AND d.position_number=1 ORDER BY r.round;

EXAMPLE — wins at Monza:
  SELECT r.year FROM race_data d JOIN race r ON r.id=d.race_id
  WHERE d.type='RACE_RESULT' AND d.position_number=1
    AND d.driver_id='max-verstappen' AND r.circuit_id='monza' ORDER BY r.year;
"""


_LATEST_RESULTS_ROUND_SQL = """
SELECT r.year, r.round, r.grand_prix_id FROM race r
WHERE EXISTS (SELECT 1 FROM race_data d WHERE d.race_id = r.id AND d.type = 'RACE_RESULT')
ORDER BY r.year DESC, r.round DESC
LIMIT 1
"""


def latest_results_round() -> dict | None:
    """The newest race f1db holds a result for — where query answers stop.

    f1db is published a few days after each race weekend, so the newest round
    on the calendar can be finished yet absent here. Scheduled rounds are
    already in ``race`` long before they run, so "has a result" is the test.
    """
    with connect() as conn:
        row = conn.execute(_LATEST_RESULTS_ROUND_SQL).fetchone()
    return dict(row) if row else None


# Every points-scoring sprint and race finish of the newest season with results.
_SEASON_POINTS_SQL = """
SELECT r.year, d.type, d.position_number, d.race_points FROM race_data d
JOIN race r ON r.id = d.race_id
WHERE r.year = (
    SELECT MAX(r2.year) FROM race r2 JOIN race_data d2 ON d2.race_id = r2.id WHERE d2.type = 'RACE_RESULT'
)
  AND d.type IN ('RACE_RESULT', 'SPRINT_RACE_RESULT')
  AND d.position_number IS NOT NULL AND d.race_points > 0
"""

_SCALE_KEYS = {"RACE_RESULT": "race", "SPRINT_RACE_RESULT": "sprint"}


def points_scale() -> dict | None:
    """What each finishing position paid in the newest season, read from f1db.

    Returns ``{"year": 2026, "race": [25.0, 18.0, ...], "sprint": [8.0, ...]}``,
    lists ordered from P1. The model's memory of the scales is stale (a sprint
    win paid 3 in 2021), so they are read rather than written down. The most
    common value per position is taken: a half-points race or a bonus point
    must not distort it.
    """
    with connect() as conn:
        rows = conn.execute(_SEASON_POINTS_SQL).fetchall()
    if not rows:
        return None
    paid = Counter((row["type"], row["position_number"], row["race_points"]) for row in rows)
    usual: dict[tuple[str, int], float] = {}
    for (kind, position, points), _count in paid.most_common():
        usual.setdefault((kind, position), points)
    return {
        "year": rows[0]["year"],
        **{
            key: [points for (kind, _pos), points in sorted(usual.items()) if kind == result_type]
            for result_type, key in _SCALE_KEYS.items()
        },
    }


def constructor_names() -> frozenset[str]:
    """Every team name in f1db, past and present.

    The claim checker uses it to recognise a team named in prose — including
    one long gone that the model reached for from memory ("Alfa Romeo").
    """
    with connect() as conn:
        return frozenset(row["name"] for row in conn.execute("SELECT name FROM constructor"))


class QueryValidationError(ValueError):
    """Raised when a submitted query is not a permitted read-only statement."""


def validate_query(sql: str) -> str:
    """Return the cleaned SQL if it is a single read-only SELECT, else raise."""
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise QueryValidationError("Query is empty.")
    if ";" in cleaned:
        raise QueryValidationError("Only a single statement is allowed (no ';').")
    lowered = cleaned.lower()
    if not (lowered.startswith(("select", "with"))):
        raise QueryValidationError("Only SELECT or WITH (CTE) queries are allowed.")
    if _FORBIDDEN.search(cleaned):
        raise QueryValidationError("Query contains a forbidden keyword. Only read-only SELECT is permitted.")
    return cleaned


def run_readonly_query(
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Execute a validated read-only query against f1db.

    Returns ``{"columns": [...], "rows": [ {col: val}, ... ], "row_count": N,
    "sql": <executed sql>}``.  Raises :class:`QueryValidationError` for
    disallowed input; other database errors propagate to the caller.
    """
    cleaned = validate_query(sql)
    if not _HAS_LIMIT.search(cleaned):
        cleaned = f"{cleaned}\nLIMIT {max_rows}"

    with connect() as conn:
        start = time.monotonic()

        def _budget_guard() -> int:
            # Progress handler: return non-zero to abort a runaway query.
            return 1 if (time.monotonic() - start) > timeout_seconds else 0

        conn.set_progress_handler(_budget_guard, 10_000)
        try:
            cursor = conn.execute(cleaned)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = [dict(row) for row in cursor.fetchmany(max_rows)]
        finally:
            conn.set_progress_handler(None, 0)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "sql": cleaned,
    }
