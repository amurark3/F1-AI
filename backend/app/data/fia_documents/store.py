"""Every FIA document collected, one row per document.

About 85 documents a weekend, so a season's text runs to megabytes: one row
per document (keyed by its URL, looked up by season and event) instead of one
document-store entry that every run would read and rewrite whole.

Only the ingest job writes here. Without ``DATABASE_URL`` one JSON file per
season under ``FIA_DOCUMENTS_DIR`` stands in. One Postgres table, created on
first use; ``ensure_schema(conn)`` is the same DDL for a deploy script. Unlike
the OpenF1 read-through store, a failure here is raised as
:class:`FiaStoreError`: the ingest must stop rather than treat an outage as a
season with nothing collected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import FIA_DOCUMENTS_DIR
from app.data.fia_documents.document import SourceDocument

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import psycopg

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fia_documents (
    url TEXT PRIMARY KEY, year SMALLINT NOT NULL, event TEXT NOT NULL, title TEXT NOT NULL,
    published TEXT NOT NULL, sha256 TEXT NOT NULL, fetched_at TEXT NOT NULL,
    text TEXT, error TEXT, withdrawn TEXT);
CREATE INDEX IF NOT EXISTS fia_documents_event ON fia_documents (year, event);
-- Supabase publishes every public table over PostgREST; RLS with no policies
-- denies that API while this backend, connecting as the owner, is unaffected.
ALTER TABLE fia_documents ENABLE ROW LEVEL SECURITY;
"""
_EVENTS_SQL = "SELECT DISTINCT event FROM fia_documents WHERE year = %s"
_LOAD_EVENT_SQL = (
    "SELECT url, event, title, published, sha256, fetched_at, text, error, withdrawn "
    "FROM fia_documents WHERE year = %s AND event = %s ORDER BY url"
)
_SAVE_SQL = (
    "INSERT INTO fia_documents (year, url, event, title, published, sha256, fetched_at, text, error, withdrawn) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO UPDATE SET "
    "year = EXCLUDED.year, event = EXCLUDED.event, title = EXCLUDED.title, published = EXCLUDED.published, "
    "sha256 = EXCLUDED.sha256, fetched_at = EXCLUDED.fetched_at, text = EXCLUDED.text, "
    "error = EXCLUDED.error, withdrawn = EXCLUDED.withdrawn"
)


class FiaStoreError(RuntimeError):
    """The FIA document store could not be read or written."""


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(_SCHEMA_SQL)


class FileFiaStore:
    """One ``<year>.json`` per season: ``{url: document}``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, year: int) -> Path:
        return self._root / f"{year}.json"

    def _read(self, year: int) -> dict[str, dict]:
        path = self._path(year)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def events(self, year: int) -> frozenset[str]:
        return frozenset(entry.get("event") for entry in self._read(year).values() if entry.get("event"))

    def load_event(self, year: int, event: str) -> tuple[SourceDocument, ...]:
        entries = (SourceDocument.from_dict(entry) for url, entry in sorted(self._read(year).items()))
        return tuple(document for document in entries if document is not None and document.event == event)

    def save(self, year: int, documents: Iterable[SourceDocument]) -> None:
        held = self._read(year)
        held.update({document.url: document.as_dict() for document in documents})
        path = self._path(year)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.tmp")
        temp.write_text(json.dumps(held), encoding="utf-8")
        os.replace(temp, path)


class PostgresFiaStore:
    """The ``fia_documents`` table, one short connection per call."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._schema_ready = False

    def _connect(self) -> psycopg.Connection:
        import psycopg

        conn = psycopg.connect(self._dsn, autocommit=True, connect_timeout=5)
        if not self._schema_ready:
            ensure_schema(conn)
            self._schema_ready = True
        return conn

    def events(self, year: int) -> frozenset[str]:
        with self._connect() as conn:
            return frozenset(row[0] for row in conn.execute(_EVENTS_SQL, (year,)).fetchall())

    def load_event(self, year: int, event: str) -> tuple[SourceDocument, ...]:
        with self._connect() as conn:
            rows = conn.execute(_LOAD_EVENT_SQL, (year, event)).fetchall()
        return tuple(SourceDocument(*row) for row in rows)

    def save(self, year: int, documents: Iterable[SourceDocument]) -> None:
        values = [(year, *document.as_dict().values()) for document in documents]
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.executemany(_SAVE_SQL, values)


def _build(dsn: str) -> FileFiaStore | PostgresFiaStore:
    return PostgresFiaStore(dsn) if dsn else FileFiaStore(Path(FIA_DOCUMENTS_DIR))


STORE = _build(os.getenv("DATABASE_URL", "").strip())


def _guarded[T](action: str, call: Callable[[], T]) -> T:
    try:
        return call()
    except Exception as exc:
        raise FiaStoreError(f"the FIA document store could not {action}: {exc}") from exc


def events(year: int) -> frozenset[str]:
    """The events of ``year`` with at least one document held."""
    return _guarded("be read", lambda: STORE.events(year))


def load_event(year: int, event: str) -> tuple[SourceDocument, ...]:
    """Every document held for one event, withdrawn and unread ones included."""
    return _guarded("be read", lambda: STORE.load_event(year, event))


def save(year: int, documents: Iterable[SourceDocument]) -> None:
    """Insert or replace each document by its URL; nothing else held changes."""
    _guarded("be written", lambda: STORE.save(year, documents))
