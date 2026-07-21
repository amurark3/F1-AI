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

EXAMPLE — wins at Monza:
  SELECT r.year FROM race_data d JOIN race r ON r.id=d.race_id
  WHERE d.type='RACE_RESULT' AND d.position_number=1
    AND d.driver_id='max-verstappen' AND r.circuit_id='monza' ORDER BY r.year;
"""


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
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise QueryValidationError("Only SELECT or WITH (CTE) queries are allowed.")
    if _FORBIDDEN.search(cleaned):
        raise QueryValidationError(
            "Query contains a forbidden keyword. Only read-only SELECT is permitted."
        )
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
