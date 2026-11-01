"""Tests for app.data.analysis_cache: kept OpenF1 loads for the Telemetry Lab.

* A row written under another ``schema_version`` reads as missing, so a changed
  payload shape never reaches code expecting the new one.
* A database failure is a cache miss, never an error: the load is fetched again.
* Without ``DATABASE_URL`` only process memory is used, bounded in size.

The Postgres path is exercised by faking ``psycopg.connect``.
"""

from __future__ import annotations

import psycopg
import pytest

from app.data.analysis_cache import AnalysisCache

pytestmark = pytest.mark.unit

DSN = "postgresql://user:secret@db.example.supabase.co:5432/postgres"


class FakeConnection:
    def __init__(self, row: tuple | None = None, fail_on: str | None = None) -> None:
        self.row = row
        self.fail_on = fail_on
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self.fail_on is not None and self.fail_on in sql:
            raise psycopg.OperationalError("connection to server failed")
        return self

    def fetchone(self):
        return self.row


@pytest.fixture
def connect(monkeypatch):
    def install(connection: FakeConnection) -> FakeConnection:
        monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: connection)
        return connection

    return install


def test_without_a_database_loads_are_kept_in_memory():
    cache = AnalysisCache(None, 4)

    assert cache.get("lap_trace", "1", 1) is None
    cache.put("lap_trace", "1", 1, {"t": [0.0]})

    assert cache.get("lap_trace", "1", 1) == {"t": [0.0]}
    assert cache.get("lap_trace", "1", 2) is None


def test_memory_holds_the_most_recently_used_loads_only():
    cache = AnalysisCache(None, 2)
    cache.put("k", "a", 1, {"n": "a"})
    cache.put("k", "b", 1, {"n": "b"})
    cache.get("k", "a", 1)
    cache.put("k", "c", 1, {"n": "c"})

    assert cache.get("k", "b", 1) is None
    assert cache.get("k", "a", 1) == {"n": "a"}
    assert cache.get("k", "c", 1) == {"n": "c"}


def test_a_kept_row_is_read_once_then_served_from_memory(connect):
    connection = connect(FakeConnection(row=({"laps": []},)))
    cache = AnalysisCache(DSN, 4)

    assert cache.get("session_laps", "2026:18:Q", 1) == {"laps": []}
    assert cache.get("session_laps", "2026:18:Q", 1) == {"laps": []}

    selects = [params for sql, params in connection.statements if sql.startswith("SELECT")]
    assert selects == [("session_laps", "2026:18:Q", 1)]
    assert sum("CREATE TABLE" in sql for sql, _ in connection.statements) == 1


@pytest.mark.parametrize("row", [None, ("not a document",)])
def test_a_missing_or_unusable_row_is_a_miss(connect, row):
    connect(FakeConnection(row=row))

    assert AnalysisCache(DSN, 4).get("lap_trace", "x", 1) is None


def test_a_failed_read_is_a_miss_not_an_error(connect):
    connect(FakeConnection(fail_on="SELECT"))

    assert AnalysisCache(DSN, 4).get("lap_trace", "x", 1) is None


def test_a_write_upserts_the_row_with_its_schema_version(connect):
    connection = connect(FakeConnection())
    cache = AnalysisCache(DSN, 4)

    cache.put("circuit", "9:2026", 1, {"rotation": 0})

    (insert,) = [params for sql, params in connection.statements if "INSERT INTO analysis_cache" in sql]
    assert insert[:3] == ("circuit", "9:2026", 1)
    assert insert[3].obj == {"rotation": 0}


def test_a_failed_write_still_keeps_the_load_in_memory(connect):
    connect(FakeConnection(fail_on="INSERT"))
    cache = AnalysisCache(DSN, 4)

    cache.put("circuit", "9:2026", 1, {"rotation": 0})

    assert cache.get("circuit", "9:2026", 1) == {"rotation": 0}
