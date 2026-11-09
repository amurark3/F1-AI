"""A fake ``app_documents`` table behind ``psycopg.connect``, for store tests.

It interprets exactly the statements ``PostgresDocumentStore`` sends, holding
each row as ``(payload, version)``. Two store or cache instances pointed at one
table stand in for two processes sharing the production database, and
:meth:`DocumentTable.before_next_write` lets a test act as the other process at
the worst moment: after the running instance has read the document and before
its conditional write lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

import psycopg

from app.data import store as store_module

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

FAILURE_MESSAGE = "connection to server failed: the database is paused"


@dataclass(frozen=True)
class _Cursor:
    row: tuple | None = None
    rowcount: int = 0

    def fetchone(self) -> tuple | None:
        return self.row


class DocumentTable:
    """The rows of ``app_documents`` plus the knobs a test turns."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[dict, int]] = {}
        # A statement containing this text raises, as a paused database would.
        self.fail_on: str | None = None
        self.statements: list[str] = []
        self._hooks: list[Callable[[], None]] = []

    # -- what a test reads and writes directly ------------------------------
    def payload(self, name: str) -> dict:
        return self.rows[name][0]

    def version(self, name: str) -> int:
        return self.rows[name][1]

    def put(self, name: str, payload: dict) -> None:
        """Write as another process would: a new payload under a new version."""
        _, version = self.rows.get(name, ({}, 0))
        self.rows = {**self.rows, name: (payload, version + 1)}

    def before_next_write(self, hook: Callable[[], None]) -> None:
        """Run ``hook`` once, just before the next conditional write is applied."""
        self._hooks = [*self._hooks, hook]

    def connect(self, _dsn: str, **_kwargs: object) -> _Connection:
        return _Connection(self)

    # -- statement handlers -------------------------------------------------
    def _run_hooks(self) -> None:
        hooks, self._hooks = self._hooks, []
        for hook in hooks:
            hook()

    def _insert_if_absent(self, params: tuple) -> _Cursor:
        self._run_hooks()
        name, jsonb = params
        if name in self.rows:
            return _Cursor(rowcount=0)
        self.rows = {**self.rows, name: (jsonb.obj, 1)}
        return _Cursor(rowcount=1)

    def _update_if_version(self, params: tuple) -> _Cursor:
        self._run_hooks()
        jsonb, name, expected = params
        if name not in self.rows or self.rows[name][1] != expected:
            return _Cursor(rowcount=0)
        self.rows = {**self.rows, name: (jsonb.obj, expected + 1)}
        return _Cursor(rowcount=1)

    def _upsert(self, params: tuple) -> _Cursor:
        name, jsonb = params
        self.put(name, jsonb.obj)
        return _Cursor(rowcount=1)

    def execute(self, sql: str, params: tuple | None) -> _Cursor:
        self.statements = [*self.statements, sql]
        if self.fail_on is not None and self.fail_on in sql:
            raise psycopg.OperationalError(FAILURE_MESSAGE)
        if "CREATE TABLE" in sql:
            return _Cursor()
        if sql.strip() == "SELECT 1":
            return _Cursor(row=(1,))
        if "SELECT payload, version" in sql:
            assert params is not None
            return _Cursor(row=self.rows.get(params[0]))
        assert params is not None, sql
        if "DO NOTHING" in sql:
            return self._insert_if_absent(params)
        if sql.strip().startswith("UPDATE app_documents"):
            return self._update_if_version(params)
        if "ON CONFLICT (name)" in sql:
            return self._upsert(params)
        raise AssertionError(f"unexpected statement: {sql}")


class _Connection:
    """Context-managed stand-in for ``psycopg.Connection``."""

    def __init__(self, table: DocumentTable) -> None:
        self._table = table

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple | None = None) -> _Cursor:
        return self._table.execute(sql, params)


def install_document_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DocumentTable:
    """Route every ``psycopg.connect`` in the test to one shared fake table.

    A document with no row falls back to its local file, so those are moved to
    ``tmp_path`` too: the developer's own ``data/*.json`` must never leak in.
    """
    table = DocumentTable()
    monkeypatch.setattr(psycopg, "connect", table.connect)
    monkeypatch.setattr(
        store_module,
        "_FALLBACK_FILES",
        {name: str(tmp_path / Path(path).name) for name, path in store_module._FALLBACK_FILES.items()},
    )
    return table
