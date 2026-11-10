"""Kept OpenF1 loads for the Telemetry Lab: lap lists, lap traces, circuit corners.

OpenF1 rate-limits bursts and refuses every request while an F1 session is
live, so a session analysed once should not need OpenF1 again. What is kept is
the **measured input** (laps, car samples, race-control windows), never a
modelled result: changing the fuel effect or the traffic threshold must not
serve numbers computed under the old ones.

A row is keyed by ``(kind, key)`` and carries the payload's ``schema_version``;
a row written under another version reads as missing. Callers only store a
session once it has ended and settled, and never store an empty load.

This is its own table, not more documents in ``app_documents``: that store
holds each document whole in memory and rewrites it on every write, and a
season of lap traces runs to megabytes. Without ``DATABASE_URL`` (local
development) only the in-process memory is used.
"""

from __future__ import annotations

from collections import OrderedDict
import os
import threading
from typing import TYPE_CHECKING

import structlog

from app.config import ANALYSIS_MEMORY_ENTRIES

if TYPE_CHECKING:
    import psycopg

logger = structlog.get_logger()

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    kind           TEXT NOT NULL,
    key            TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload        JSONB NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, key)
);

-- Supabase publishes every public table over PostgREST; RLS with no policies
-- denies that API while this backend, connecting as the owner, is unaffected.
ALTER TABLE analysis_cache ENABLE ROW LEVEL SECURITY;
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create ``analysis_cache`` on ``conn``'s database. Idempotent."""
    conn.execute(_SCHEMA_SQL)


CacheKey = tuple[str, str, int]


class AnalysisCache:
    """Recently used loads in memory, in front of a Postgres table."""

    def __init__(self, dsn: str | None, max_entries: int) -> None:
        self._dsn = dsn
        self._max_entries = max_entries
        self._memory: OrderedDict[CacheKey, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._schema_ready = False

    def _connect(self) -> psycopg.Connection:
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self, conn: psycopg.Connection) -> None:
        if not self._schema_ready:
            ensure_schema(conn)
            self._schema_ready = True

    def _remember(self, key: CacheKey, payload: dict) -> None:
        with self._lock:
            self._memory[key] = payload
            self._memory.move_to_end(key)
            while len(self._memory) > self._max_entries:
                self._memory.popitem(last=False)

    def _recall(self, key: CacheKey) -> dict | None:
        with self._lock:
            payload = self._memory.get(key)
            if payload is not None:
                self._memory.move_to_end(key)
            return payload

    def _read_row(self, kind: str, key: str, version: int) -> dict | None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT payload FROM analysis_cache WHERE kind = %s AND key = %s AND schema_version = %s",
                (kind, key, version),
            ).fetchone()
        return row[0] if row and isinstance(row[0], dict) else None

    def get(self, kind: str, key: str, version: int) -> dict | None:
        """The kept payload, or None when nothing usable is kept (or the database failed)."""
        cache_key = (kind, key, version)
        payload = self._recall(cache_key)
        if payload is not None or not self._dsn:
            return payload
        try:
            payload = self._read_row(kind, key, version)
        except Exception as exc:
            logger.warning("analysis_cache.read_failed", kind=kind, key=key, error=str(exc))
            return None
        if payload is not None:
            self._remember(cache_key, payload)
        return payload

    def put(self, kind: str, key: str, version: int, payload: dict) -> None:
        """Keep a payload. A failed database write is logged; the load is still served."""
        self._remember((kind, key, version), payload)
        if not self._dsn:
            return
        try:
            from psycopg.types.json import Jsonb

            with self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO analysis_cache (kind, key, schema_version, payload, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (kind, key)
                    DO UPDATE SET schema_version = EXCLUDED.schema_version,
                                  payload = EXCLUDED.payload,
                                  updated_at = now()
                    """,
                    (kind, key, version, Jsonb(payload)),
                )
        except Exception as exc:
            logger.warning("analysis_cache.write_failed", kind=kind, key=key, error=str(exc))


analysis_cache = AnalysisCache(os.getenv("DATABASE_URL", "").strip() or None, ANALYSIS_MEMORY_ENTRIES)
