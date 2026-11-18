"""The FIA document store: one row per document, in files or Postgres (faked)."""

from __future__ import annotations

import json

import psycopg
import pytest

from app.data.fia_documents import store
from app.data.fia_documents.document import SourceDocument
from app.data.fia_documents.store import FiaStoreError, FileFiaStore, PostgresFiaStore

pytestmark = pytest.mark.unit

DSN = "postgresql://user:secret@db.example.supabase.co:5432/postgres"
MEXICO = "Mexico City Grand Prix"
VEGAS = "Las Vegas Grand Prix"


def doc(url: str, event: str = MEXICO, **overrides) -> SourceDocument:
    fields = {
        "url": url,
        "event": event,
        "title": f"Doc 1 - {url}",
        "published": "01.11.26 20:00",
        "sha256": "abc",
        "fetched_at": "2026-11-17T20:00:00+00:00",
        "text": "text",
    }
    return SourceDocument(**{**fields, **overrides})


@pytest.fixture
def files(tmp_path) -> FileFiaStore:
    return FileFiaStore(tmp_path / "fia")


def test_files_keep_each_document_once_by_url(files):
    files.save(2026, (doc("a"), doc("b"), doc("c", VEGAS)))
    files.save(2026, (doc("a", text=None, error="download failed"),))

    assert files.events(2026) == frozenset({MEXICO, VEGAS})
    assert files.events(2025) == frozenset()
    assert files.load_event(2026, MEXICO) == (doc("a", text=None, error="download failed"), doc("b"))
    assert files.load_event(2026, VEGAS) == (doc("c", VEGAS),)


def test_files_skip_an_entry_missing_its_identity(files):
    files.save(2026, (doc("a"),))
    path = files._path(2026)
    path.write_text(json.dumps({"a": doc("a").as_dict(), "broken": {"event": MEXICO}}))

    assert files.load_event(2026, MEXICO) == (doc("a"),)


class FakeConnection:
    def __init__(self, rows: list[tuple] | None = None, fail: bool = False) -> None:
        self.rows = rows or []
        self.fail = fail
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self.fail and "CREATE TABLE" not in sql:
            raise psycopg.OperationalError("connection to server failed")
        return self

    def executemany(self, sql, params):
        self.statements.append((sql, list(params)))
        if self.fail:
            raise psycopg.OperationalError("connection to server failed")

    def cursor(self):
        return self

    def fetchall(self):
        return self.rows


@pytest.fixture
def connect(monkeypatch):
    def install(connection: FakeConnection) -> FakeConnection:
        monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: connection)
        return connection

    return install


def _queries(connection: FakeConnection) -> list[tuple[str, object]]:
    return [statement for statement in connection.statements if "CREATE TABLE" not in statement[0]]


def test_postgres_events_are_the_distinct_events_of_the_year(connect):
    connection = connect(FakeConnection(rows=[(MEXICO,), (VEGAS,)]))

    assert PostgresFiaStore(DSN).events(2026) == frozenset({MEXICO, VEGAS})
    [(sql, params)] = _queries(connection)
    assert "SELECT DISTINCT event FROM fia_documents WHERE year = %s" in sql
    assert params == (2026,)


def test_postgres_load_event_reads_rows_back_as_documents(connect):
    stored = doc("a", withdrawn="no longer listed on the FIA event page")
    connection = connect(FakeConnection(rows=[tuple(stored.as_dict().values())]))

    assert PostgresFiaStore(DSN).load_event(2026, MEXICO) == (stored,)
    [(sql, params)] = _queries(connection)
    assert "WHERE year = %s AND event = %s" in sql
    assert params == (2026, MEXICO)


def test_postgres_save_upserts_on_url(connect):
    connection = connect(FakeConnection())

    PostgresFiaStore(DSN).save(2026, (doc("a"),))

    [(sql, params)] = _queries(connection)
    assert "ON CONFLICT (url) DO UPDATE" in sql
    assert params == [(2026, *doc("a").as_dict().values())]


def test_the_schema_is_created_once_per_store(connect):
    connection = connect(FakeConnection())
    postgres = PostgresFiaStore(DSN)

    postgres.events(2026)
    postgres.events(2026)

    assert sum("CREATE TABLE" in sql for sql, _ in connection.statements) == 1


def test_the_module_reads_and_writes_through_the_configured_store(files, monkeypatch):
    monkeypatch.setattr(store, "STORE", files)

    store.save(2026, (doc("a"),))

    assert store.events(2026) == frozenset({MEXICO})
    assert store.load_event(2026, MEXICO) == (doc("a"),)


@pytest.mark.parametrize(
    "call",
    [
        lambda: store.events(2026),
        lambda: store.load_event(2026, MEXICO),
        lambda: store.save(2026, (doc("a"),)),
    ],
)
def test_a_store_failure_is_raised_as_one_error(connect, monkeypatch, call):
    connect(FakeConnection(fail=True))
    monkeypatch.setattr(store, "STORE", PostgresFiaStore(DSN))

    with pytest.raises(FiaStoreError, match="connection to server failed"):
        call()


def test_the_store_follows_database_url():
    assert isinstance(store._build(DSN), PostgresFiaStore)
    assert isinstance(store._build(""), FileFiaStore)
