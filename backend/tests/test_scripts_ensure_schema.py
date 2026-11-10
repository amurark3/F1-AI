"""Tests for ``scripts.ensure_schema`` — every app table, made by the app's own code.

The migration to the VM (deploy/oracle/bin/migrate-from-supabase.sh) runs it
before it copies any data. What is pinned:

* **The app's own schema functions, all of them.** Each module that creates a
  table at first use is called, on one connection, so the target gets exactly
  the DDL the app would run, never a copy.
* **Any database on the server.** ``--dbname`` points the stack's
  ``DATABASE_URL`` at another database (the migration's dry run uses a scratch
  one), so no second URL with the password in it is needed.
* **Refuses rather than guesses.** No ``DATABASE_URL`` (it never reads
  ``backend/.env``, which points at production) is a non-zero exit before any
  connection is opened; a failed statement is another.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.data import analysis_cache, memory, store
from app.rag import pgvector_store
from app.utils.embeddings import EMBEDDING_DIM
from scripts import ensure_schema as script

pytestmark = pytest.mark.unit

_URL = "postgresql://f1ai:pw@postgres:5432/f1ai"


class _FakeConnection:
    def __init__(self, dbname: str, fail_on: str | None = None) -> None:
        self.info = SimpleNamespace(dbname=dbname)
        self.fail_on = fail_on
        self.statements: list[str] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        self.closed = True
        return False

    def execute(self, statement: str, params=None):
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError('permission denied to create extension "vector"')
        self.statements.append(statement)
        return self


@pytest.fixture
def connect(monkeypatch):
    """Install a fake ``psycopg`` whose ``connect`` records its arguments."""
    calls: list[tuple[str, dict]] = []

    def install(fail_on: str | None = None) -> tuple[list, list]:
        connections: list[_FakeConnection] = []

        def fake_connect(url: str, **kwargs) -> _FakeConnection:
            calls.append((url, kwargs))
            connection = _FakeConnection(kwargs.get("dbname", "f1ai"), fail_on)
            connections.append(connection)
            return connection

        fake = ModuleType("psycopg")
        fake.connect = fake_connect
        monkeypatch.setitem(sys.modules, "psycopg", fake)
        return calls, connections

    return install


def test_every_app_table_is_created_by_its_own_module(monkeypatch, capsys, connect):
    monkeypatch.setenv("DATABASE_URL", _URL)
    calls, connections = connect()

    status = script.main([])

    assert status == script.EXIT_OK
    assert calls == [(_URL, {"autocommit": True})]
    (connection,) = connections
    assert connection.statements == [
        store._SCHEMA_SQL,
        analysis_cache._SCHEMA_SQL,
        memory._SCHEMA_SQL,
        pgvector_store._SCHEMA_SQL,
    ]
    assert connection.closed
    out = capsys.readouterr().out
    for table in ("app_documents", "analysis_cache", "user_profile", "chat_message", "rulebook_chunk"):
        assert table in out
    assert "database f1ai" in out
    assert out.splitlines()[-1] == f"embedding dimension {EMBEDDING_DIM}"


def test_the_schema_functions_are_the_modules_public_ones():
    """A rename in a module must fail here, not on the VM halfway through a migration.

    Compared by name: other suites reload some of these modules, which makes new
    function objects with the same names.
    """
    assert [(ensure.__module__, ensure.__name__) for _, ensure in script.SCHEMAS] == [
        ("app.data.store", "ensure_schema"),
        ("app.data.analysis_cache", "ensure_schema"),
        ("app.data.memory", "ensure_schema"),
        ("app.rag.pgvector_store", "ensure_schema_conn"),
    ]


def test_dbname_points_the_url_at_another_database_on_the_server(monkeypatch, capsys, connect):
    monkeypatch.setenv("DATABASE_URL", _URL)
    calls, connections = connect()

    status = script.main(["--dbname", "f1ai_migrate_check"])

    assert status == script.EXIT_OK
    assert calls == [(_URL, {"autocommit": True, "dbname": "f1ai_migrate_check"})]
    assert len(connections[0].statements) == len(script.SCHEMAS)
    assert "database f1ai_migrate_check" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_dbname_is_rejected(capsys, value):
    with pytest.raises(SystemExit) as exc:
        script.main(["--dbname", value])

    assert exc.value.code == 2
    assert "database name" in capsys.readouterr().err


@pytest.mark.parametrize("url", [None, "", "  "])
def test_no_database_url_is_refused_before_any_connection(monkeypatch, capsys, connect, url):
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    calls, _ = connect()

    status = script.main([])

    assert status == script.EXIT_NO_DATABASE
    assert calls == []
    assert "DATABASE_URL is not set" in capsys.readouterr().out


def test_a_failed_statement_is_reported_and_exits_non_zero(monkeypatch, capsys, connect):
    monkeypatch.setenv("DATABASE_URL", _URL)
    _, connections = connect(fail_on="CREATE EXTENSION")

    status = script.main([])

    assert status == script.EXIT_FAILED
    # app_documents and analysis_cache need no extension and were created first.
    assert connections[0].statements == [store._SCHEMA_SQL, analysis_cache._SCHEMA_SQL]
    out = capsys.readouterr().out
    assert 'Schema not created: permission denied to create extension "vector"' in out
    assert "embedding dimension" not in out
