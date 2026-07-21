"""Durable document store with a Postgres backend and JSON-file fallback.

Small JSON documents (the prediction snapshot cache and the prediction
accuracy history) were previously written only to local disk.  On hosts with
an ephemeral filesystem (e.g. Render) every deploy or cold start wiped that
data, silently resetting accumulated prediction history.

This module persists those documents to Postgres (Supabase) when
``DATABASE_URL`` is configured, and transparently falls back to the original
JSON files for local development.  When a Postgres row does not yet exist it
reads from the local file, so existing data keeps working and is promoted to
Postgres on the next write.  All operations degrade gracefully and never
raise — durability must not come at the cost of breaking a request.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Protocol

import structlog

from app.config import PREDICTION_CACHE_PATH, PREDICTION_HISTORY_PATH

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Document identifiers + their local fallback files
# ---------------------------------------------------------------------------
DOCUMENT_PREDICTION_CACHE = "prediction_cache"
DOCUMENT_PREDICTION_HISTORY = "prediction_history"
DOCUMENT_PREDICTION_POSTMORTEMS = "prediction_postmortems"

_FALLBACK_FILES: dict[str, str] = {
    DOCUMENT_PREDICTION_CACHE: PREDICTION_CACHE_PATH,
    DOCUMENT_PREDICTION_HISTORY: PREDICTION_HISTORY_PATH,
    DOCUMENT_PREDICTION_POSTMORTEMS: "data/prediction_postmortems.json",
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_documents (
    name       TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _json_default(value: Any) -> str:
    """Fallback serializer for non-native types (datetimes, etc.)."""
    return str(value)


class DocumentStore(Protocol):
    """A named-document key/value store returning JSON-compatible dicts."""

    def read(self, name: str) -> dict | None: ...

    def write(self, name: str, payload: dict) -> None: ...


# ---------------------------------------------------------------------------
# File backend (local dev / fallback)
# ---------------------------------------------------------------------------
class FileDocumentStore:
    """Reads/writes each document to its configured JSON file (atomic writes)."""

    def read(self, name: str) -> dict | None:
        path_str = _FALLBACK_FILES.get(name)
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return None
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("store.file_read_failed", document=name, error=str(exc))
            return None

    def write(self, name: str, payload: dict) -> None:
        path_str = _FALLBACK_FILES.get(name)
        if not path_str:
            logger.warning("store.file_write_skipped_unknown_document", document=name)
            return
        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, indent=2, default=_json_default), encoding="utf-8"
            )
            tmp_path.replace(path)  # Atomic on POSIX
        except OSError as exc:
            logger.warning("store.file_write_failed", document=name, error=str(exc))
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Postgres backend (Supabase / production)
# ---------------------------------------------------------------------------
class PostgresDocumentStore:
    """Persists documents to a single JSONB-backed Postgres table.

    Falls back to the local JSON file when a row is absent (so existing local
    data keeps working and is promoted to Postgres on the next write) and when
    a database operation fails (so a transient outage never loses a write).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._file_fallback = FileDocumentStore()
        self._schema_ready = False
        self._lock = threading.Lock()
        # Fail fast if the driver is missing so the factory can fall back.
        import psycopg  # noqa: F401

    def _connect(self):
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        with self._lock:
            if self._schema_ready:
                return
            conn.execute(_SCHEMA_SQL)
            self._schema_ready = True

    def read(self, name: str) -> dict | None:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT payload FROM app_documents WHERE name = %s", (name,)
                ).fetchone()
            if row and isinstance(row[0], dict):
                return row[0]
        except Exception as exc:
            logger.error("store.pg_read_failed", document=name, error=str(exc))
            return self._file_fallback.read(name)
        # No row yet — read any existing local file (transparent migration).
        return self._file_fallback.read(name)

    def write(self, name: str, payload: dict) -> None:
        from psycopg.types.json import Jsonb

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO app_documents (name, payload, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (name)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                    """,
                    (name, Jsonb(payload, dumps=lambda o: json.dumps(o, default=_json_default))),
                )
        except Exception as exc:
            logger.error("store.pg_write_failed_using_file_fallback", document=name, error=str(exc))
            self._file_fallback.write(name, payload)


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------
def _build_store() -> DocumentStore:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn:
        try:
            store = PostgresDocumentStore(dsn)
            logger.info("store.backend_selected", backend="postgres")
            return store
        except Exception as exc:
            logger.error("store.postgres_unavailable_using_file", error=str(exc))
    else:
        logger.info("store.backend_selected", backend="file")
    return FileDocumentStore()


document_store: DocumentStore = _build_store()
