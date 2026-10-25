"""Tests for app.data.f1db_query — the guarded SQL surface the LLM writes into.

This is the only place in the backend where model-authored text reaches a
database engine. The guards are the security boundary: a single read-only
statement, a mutating-keyword denylist, a row cap, and a wall-clock budget that
aborts a runaway query before it pins a worker. Each of those is tested for the
behaviour it promises, against a real SQLite file so the SQL itself runs.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.data import f1db_query
from app.data.f1db_query import QueryValidationError, run_readonly_query, validate_query

# A query heavy enough to trip the 10k-opcode progress handler at least once,
# which is the only way the wall-clock budget can ever be consulted.
_HEAVY_QUERY = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x < 500000) SELECT COUNT(*) AS n FROM c"
)


# ---------------------------------------------------------------------------
# validate_query
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SELECT 1", "SELECT 1"),
        ("  SELECT 1  ", "SELECT 1"),
        ("SELECT 1;", "SELECT 1"),
        ("SELECT 1 ; ", "SELECT 1"),
        ("with x as (select 1) select * from x", "with x as (select 1) select * from x"),
    ],
    ids=["plain", "surrounding-space", "trailing-semicolon", "spaced-semicolon", "cte"],
)
def test_validate_query_accepts_and_normalises_a_single_read_only_statement(raw, expected):
    assert validate_query(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["", "   ", ";", None], ids=["empty", "blank", "semicolon-only", "none"])
def test_validate_query_rejects_an_empty_query(raw):
    with pytest.raises(QueryValidationError, match="empty"):
        validate_query(raw)


@pytest.mark.unit
def test_validate_query_rejects_a_stacked_second_statement():
    """Statement stacking is the classic path from a SELECT to a DROP."""
    with pytest.raises(QueryValidationError, match="single statement"):
        validate_query("SELECT 1; SELECT 2")


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    ["UPDATE driver SET name = 'x'", "EXPLAIN SELECT 1", "PRAGMA table_info(race)", "-- SELECT 1"],
    ids=["update", "explain", "pragma", "comment-prefixed"],
)
def test_validate_query_rejects_anything_not_starting_with_select_or_with(raw):
    with pytest.raises(QueryValidationError, match="Only SELECT or WITH"):
        validate_query(raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "keyword",
    ["insert", "update", "delete", "drop", "alter", "create", "replace", "attach", "detach", "vacuum"],
)
def test_validate_query_rejects_a_mutating_keyword_anywhere_in_the_statement(keyword):
    """Defense in depth: the connection is read-only, but the model gets a
    readable error instead of a raw SQLite exception."""
    with pytest.raises(QueryValidationError, match="forbidden keyword"):
        validate_query(f"WITH t AS (SELECT 1) {keyword} FROM t")  # noqa: S608 — the injection IS the test


@pytest.mark.unit
def test_validate_query_denylist_is_case_insensitive():
    with pytest.raises(QueryValidationError, match="forbidden keyword"):
        validate_query("SELECT * FROM race WHERE 1=1 UNION DrOp")


# ---------------------------------------------------------------------------
# latest_results_round
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_latest_results_round_is_the_newest_race_with_a_result(fake_f1db):
    """2026 round 3 is on the calendar but unraced, so it must not count.

    f1db publishes a few days after each weekend; this is how a query result
    says where the data stops, so a season question can spot a missing round.
    """
    assert f1db_query.latest_results_round() == {"year": 2026, "round": 2, "grand_prix_id": "monaco"}


@pytest.mark.integration
def test_latest_results_round_is_none_for_a_dataset_with_no_results(empty_f1db):
    assert f1db_query.latest_results_round() is None


# ---------------------------------------------------------------------------
# run_readonly_query — result shape
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_run_readonly_query_returns_columns_rows_and_count(fake_f1db):
    result = run_readonly_query(
        "SELECT id, full_name FROM driver WHERE id = 'charles-leclerc'",
    )

    assert result["columns"] == ["id", "full_name"]
    assert result["rows"] == [{"id": "charles-leclerc", "full_name": "Charles Leclerc"}]
    assert result["row_count"] == 1


@pytest.mark.integration
def test_run_readonly_query_answers_a_real_f1_question(fake_f1db):
    """The shape of query the text-to-SQL tool actually emits."""
    result = run_readonly_query(
        """
        SELECT r.year AS year FROM race_data d JOIN race r ON r.id = d.race_id
        WHERE d.type = 'RACE_RESULT' AND d.position_number = 1
          AND d.driver_id = 'max-verstappen' ORDER BY r.year
        """
    )

    # VER won all four seeded races: two in 2025 and two in 2026.
    assert [row["year"] for row in result["rows"]] == [2025, 2025, 2026, 2026]


@pytest.mark.integration
def test_run_readonly_query_appends_a_row_cap_when_the_query_has_none(fake_f1db):
    result = run_readonly_query("SELECT id FROM driver", max_rows=2)

    assert result["sql"].endswith("LIMIT 2")
    assert result["row_count"] == 2


@pytest.mark.integration
def test_run_readonly_query_keeps_an_explicit_limit(fake_f1db):
    result = run_readonly_query("SELECT id FROM driver LIMIT 1", max_rows=50)

    assert result["sql"] == "SELECT id FROM driver LIMIT 1"
    assert result["row_count"] == 1


@pytest.mark.integration
def test_run_readonly_query_caps_the_fetch_even_when_the_query_asks_for_more(fake_f1db):
    """A model-supplied ``LIMIT 1000`` must not defeat the server-side cap."""
    result = run_readonly_query("SELECT id FROM driver LIMIT 1000", max_rows=1)

    assert result["row_count"] == 1


@pytest.mark.integration
def test_run_readonly_query_returns_an_empty_result_set_without_error(fake_f1db):
    result = run_readonly_query("SELECT id FROM driver WHERE id = 'nobody'")

    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["columns"] == ["id"], "column metadata survives a zero-row result"


@pytest.mark.integration
def test_run_readonly_query_rejects_a_write_before_touching_the_database(empty_f1db):
    with pytest.raises(QueryValidationError):
        run_readonly_query("DELETE FROM driver")


# ---------------------------------------------------------------------------
# run_readonly_query — the wall-clock budget
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_run_readonly_query_aborts_a_query_that_exceeds_its_time_budget(fake_f1db):
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        run_readonly_query(_HEAVY_QUERY, timeout_seconds=0.0)


@pytest.mark.integration
def test_run_readonly_query_lets_a_long_query_finish_inside_its_budget(fake_f1db):
    """The same query the budget aborts above completes when given room, so the
    guard is timing out on elapsed time rather than on query complexity."""
    result = run_readonly_query(_HEAVY_QUERY, timeout_seconds=60.0)

    assert result["rows"] == [{"n": 500000}]


@pytest.mark.integration
def test_run_readonly_query_clears_the_progress_handler_after_a_failure(fake_f1db, monkeypatch):
    """The handler is per-connection, but a leaked one would keep firing if the
    connection were ever pooled — the ``finally`` must run on the error path."""
    cleared: list[object] = []
    real_connect = f1db_query.connect

    class _RecordingConnection:
        """``sqlite3.Connection`` is immutable, so wrap it to observe the calls."""

        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self._conn.__exit__(*exc)

        def set_progress_handler(self, handler, n):
            cleared.append(handler)
            return self._conn.set_progress_handler(handler, n)

        def execute(self, *args):
            return self._conn.execute(*args)

    monkeypatch.setattr(f1db_query, "connect", lambda: _RecordingConnection(real_connect()))

    with pytest.raises(sqlite3.OperationalError):
        run_readonly_query(_HEAVY_QUERY, timeout_seconds=0.0)

    assert cleared[-1] is None


# ---------------------------------------------------------------------------
# Schema documentation handed to the model
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "table",
    ["race", "race_data", "season_driver_standing", "season_constructor_standing", "race_driver_standing"],
)
def test_schema_doc_describes_the_tables_the_seeded_database_actually_has(table, fake_f1db):
    """The doc is the model's only view of the schema; a stale table name there
    turns into an invalid query at runtime."""
    with f1db_query.connect() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert table in names
    assert table in f1db_query.F1DB_SCHEMA_DOC


# The join the schema doc tells the model to use, verbatim.
_TEAM_JOIN = "JOIN constructor c ON c.id = d.constructor_id"


@pytest.mark.integration
def test_the_team_join_the_doc_recommends_returns_each_drivers_team_for_that_race(fake_f1db):
    """The model's memory of the grid predates the season, so it invented teams
    ("Kimi Antonelli (Alfa Romeo)") when its rows carried only driver names. It
    is told to read the team from race_data instead; that join has to work."""
    assert _TEAM_JOIN in f1db_query.F1DB_SCHEMA_DOC

    result = run_readonly_query(
        "SELECT dr.name AS driver, c.name AS team FROM race_data d "
        "JOIN driver dr ON dr.id = d.driver_id "
        "JOIN constructor c ON c.id = d.constructor_id "
        "JOIN race r ON r.id = d.race_id "
        "WHERE d.type = 'RACE_RESULT' AND d.position_number = 1 AND r.year = 2026 ORDER BY r.round"
    )

    assert result["rows"] == [{"driver": "Verstappen", "team": "Red Bull"}] * 2


# The column the schema doc tells the model to read points from, verbatim.
_POINTS_SELECT = "SELECT d.race_points"


@pytest.mark.integration
def test_the_points_column_the_doc_recommends_holds_sprint_and_race_points(fake_f1db):
    """Its memory of the sprint scale is from 2021, when a win paid 3, so it told a
    user Russell's three sprint wins were worth 9 points. Points come from rows."""
    assert _POINTS_SELECT in f1db_query.F1DB_SCHEMA_DOC

    result = run_readonly_query(
        "SELECT d.type, dr.name AS driver, d.race_points AS points FROM race_data d "
        "JOIN driver dr ON dr.id = d.driver_id JOIN race r ON r.id = d.race_id "
        "WHERE r.year = 2026 AND r.round = 1 AND d.position_number = 1 "
        "AND d.type IN ('RACE_RESULT', 'SPRINT_RACE_RESULT') ORDER BY d.type"
    )

    assert result["rows"] == [
        {"type": "RACE_RESULT", "driver": "Verstappen", "points": 25.0},
        {"type": "SPRINT_RACE_RESULT", "driver": "Leclerc", "points": 8.0},
    ]


def _doc_example(title: str) -> str:
    """The SQL of one EXAMPLE block in the schema doc, exactly as the model reads it."""
    doc = f1db_query.F1DB_SCHEMA_DOC
    body = doc[doc.index(f"EXAMPLE — {title}") :].split("\n", 1)[1]
    return body[: body.index(";")].strip()


@pytest.mark.integration
def test_the_doc_example_for_results_selects_team_and_points_and_runs(fake_f1db):
    """Rules alone did not move the model — told to select race_points, "always"
    included, it still did not. Given a worked example that does, it copied it.
    The example is executed verbatim, so it cannot drift from the schema."""
    result = run_readonly_query(_doc_example("each 2025 race winner"))

    assert result["rows"] == [
        {"round": 1, "driver": "Verstappen", "team": "Red Bull", "race_points": 25.0},
        {"round": 2, "driver": "Verstappen", "team": "Red Bull", "race_points": 25.0},
    ]


# ---------------------------------------------------------------------------
# points_scale
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_points_scale_reads_what_each_position_paid_in_the_latest_season(fake_f1db):
    """Its memory of the scales is stale — a sprint win paid 3 in 2021 — so it
    priced a race win at 12 and a sprint win at 3. The scale comes from the data."""
    assert f1db_query.points_scale() == {"year": 2026, "race": [25.0, 18.0], "sprint": [8.0, 7.0]}


@pytest.mark.integration
def test_a_half_points_race_does_not_distort_the_scale(fake_f1db):
    """A shortened race pays half; the most common value per position wins out."""
    with sqlite3.connect(fake_f1db) as conn:
        conn.execute(
            "INSERT INTO race_data (race_id, type, position_display_order, position_number, position_text, "
            "driver_id, constructor_id, race_points) VALUES (5, 'RACE_RESULT', 1, 1, '1', 'max-verstappen', "
            "'red-bull', 12.5)"
        )

    assert f1db_query.points_scale()["race"][0] == 25.0


@pytest.mark.integration
def test_points_scale_is_none_for_a_dataset_with_no_results(empty_f1db):
    assert f1db_query.points_scale() is None


# ---------------------------------------------------------------------------
# constructor_names
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_names_lists_every_team_in_the_dataset(fake_f1db):
    """The claim checker recognises a team in prose by name — including a long-gone
    one the model might reach for from memory, so it is every team, not this season's."""
    assert f1db_query.constructor_names() == frozenset({"Red Bull", "Ferrari", "McLaren"})


@pytest.mark.integration
def test_constructor_names_is_empty_for_an_empty_dataset(empty_f1db):
    assert f1db_query.constructor_names() == frozenset()
