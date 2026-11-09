"""Durable document store with a Postgres backend and JSON-file fallback.

Small JSON documents (the prediction snapshot cache, the prediction accuracy
history, and race post-mortems) were previously written only to local disk.  On
hosts with an ephemeral filesystem (e.g. Render) every deploy or cold start
wiped that data, silently resetting accumulated prediction history.

This module persists those documents to Postgres (Supabase) when
``DATABASE_URL`` is configured, and falls back to the original JSON files for
local development.  When Postgres holds no row yet it reads from the local file,
so existing data keeps working and is promoted to Postgres on the next write.

Failures are reported, never disguised.  A failed read returns
``ReadResult(ok=False)`` rather than an empty document, and a failed Postgres
write is **not** diverted to the local file — on an ephemeral host that would
turn a visible outage into silent data loss.  The payload is held in memory
instead and retried on the next write, so a transient outage self-heals.

More than one process writes these documents (the API, a backfill script, a
scheduled job), and some callers hold a document in memory for the life of the
process.  ``update`` therefore takes a *change* rather than a whole document: it
reads the latest row and its ``version``, applies the change, and writes only
while the row is still at that version (``UPDATE … WHERE version = seen``),
otherwise re-reading and re-applying, a bounded number of times.  A change queued
through an outage is re-applied the same way, and a whole document queued by
``write`` is replayed only while the row is still at the version this process
last read, so a stale copy never overwrites a newer write.  Only a database
error queues a change: one that cannot apply (lost every race, or raised) would
fail again on every retry, so it is reported and dropped instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

import contextlib
import dataclasses
import json
import os
from pathlib import Path
import threading
import time

import structlog

from app.api.errors import new_error_id
from app.config import PREDICTION_CACHE_PATH, PREDICTION_HISTORY_PATH
from app.data.store_queue import PendingWrites, compose
from app.data.store_types import DocumentChange, DocumentStore, ReadResult, StoreHealth, UpdateResult, WriteResult

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Document identifiers + their local fallback files
# ---------------------------------------------------------------------------
DOCUMENT_PREDICTION_CACHE = "prediction_cache"
DOCUMENT_PREDICTION_HISTORY = "prediction_history"
DOCUMENT_PREDICTION_POSTMORTEMS = "prediction_postmortems"
DOCUMENT_DRIVER_AVAILABILITY = "driver_availability"
DOCUMENT_CIRCUIT_REFERENCE = "circuit_reference"
# Extracted text of the FIA power-unit documents, written only by the ingest job.
DOCUMENT_POWER_UNIT_SOURCES = "power_unit_sources"
# Each element's season allowance, as the FIA states it (or as pinned by hand).
DOCUMENT_POWER_UNIT_ALLOWANCES = "power_unit_allowances"
# When the ingest job last ran and what it found — the screen's "last updated".
DOCUMENT_POWER_UNIT_STATUS = "power_unit_ingest_status"
# Each finished race's tyre stints, once a source has resolved them.
DOCUMENT_RACE_STINTS = "race_stints"

_FALLBACK_FILES: dict[str, str] = {
    DOCUMENT_PREDICTION_CACHE: PREDICTION_CACHE_PATH,
    DOCUMENT_PREDICTION_HISTORY: PREDICTION_HISTORY_PATH,
    DOCUMENT_PREDICTION_POSTMORTEMS: "data/prediction_postmortems.json",
    DOCUMENT_DRIVER_AVAILABILITY: "data/driver_availability.json",
    DOCUMENT_CIRCUIT_REFERENCE: "data/circuit_reference.json",
    DOCUMENT_POWER_UNIT_SOURCES: "data/power_unit_sources.json",
    DOCUMENT_POWER_UNIT_ALLOWANCES: "data/power_unit_allowances.json",
    DOCUMENT_POWER_UNIT_STATUS: "data/power_unit_ingest_status.json",
    DOCUMENT_RACE_STINTS: "data/race_stints.json",
}

# How many times ``update`` re-reads and re-applies a change after another writer
# changed the document between its read and its write. These documents are
# written rarely (a computed prediction, a circuit reference, a race's stints),
# so running out means something is rewriting the document in a loop.
MAX_UPDATE_ATTEMPTS = 5

BACKEND_POSTGRES = "postgres"
BACKEND_FILE = "file"

# Client-safe classification of a configured host. Answers "did my connection
# string change take effect?" without naming the host or project.
HOST_SUPABASE_DIRECT = "supabase_direct"  # db.<ref>.supabase.co — IPv6-only
HOST_SUPABASE_POOLER = "supabase_pooler"  # <region>.pooler.supabase.com
HOST_OTHER = "other"

# Client-safe classification of a connection failure. Each maps to a distinct
# operator action, which is the whole point of separating them.
# DNS: host does not resolve — wrong name, or an IPv6-only host on an
# IPv4-only network.
REASON_DNS = "dns_unresolved"
REASON_REFUSED = "connection_refused"  # resolved, nothing listening — wrong port
REASON_AUTH = "auth_failed"  # reached it, credentials rejected
REASON_TIMEOUT = "timeout"  # no answer — firewall or egress block
REASON_TLS = "tls_error"
REASON_UNKNOWN = "unknown"

# Supavisor identifies the project from the *username*, which must be
# ``postgres.<project-ref>``. Pasting the direct connection string's plain
# ``postgres`` user into a pooler host is the easiest mistake to make and its
# error says nothing obvious, so it gets its own code.
REASON_POOLER_USER = "pooler_user_invalid"

# Matched against the lower-cased driver message. Order matters: the first hit
# wins, so put the specific signatures ahead of the generic ones.
_REASON_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("could not translate host name", REASON_DNS),
    ("name or service not known", REASON_DNS),
    ("nodename nor servname", REASON_DNS),
    ("failed to resolve host", REASON_DNS),
    ("temporary failure in name resolution", REASON_DNS),
    # Supavisor tenant-resolution failures. Verified against a live pooler:
    # a plain "postgres" user yields ENOIDENTIFIER, a bad ref yields ENOTFOUND.
    ("enoidentifier", REASON_POOLER_USER),
    ("no tenant identifier", REASON_POOLER_USER),
    ("enotfound", REASON_POOLER_USER),
    ("tenant/user", REASON_POOLER_USER),
    ("tenant or user not found", REASON_POOLER_USER),
    ("password authentication failed", REASON_AUTH),
    ("authentication failed", REASON_AUTH),
    ("no pg_hba.conf entry", REASON_AUTH),
    ('role "', REASON_AUTH),
    ("connection refused", REASON_REFUSED),
    ("timeout expired", REASON_TIMEOUT),
    ("timed out", REASON_TIMEOUT),
    ("ssl", REASON_TLS),
)


def classify_failure(message: str) -> str:
    """Map a driver error message to a client-safe reason code."""
    lowered = (message or "").lower()
    for signature, reason in _REASON_SIGNATURES:
        if signature in lowered:
            return reason
    return REASON_UNKNOWN


def classify_host(dsn: str) -> str:
    """Classify the configured host without revealing it."""
    try:
        from urllib.parse import urlparse

        host = (urlparse(dsn).hostname or "").lower()
    except ValueError:
        return HOST_OTHER

    if host.endswith(".pooler.supabase.com"):
        return HOST_SUPABASE_POOLER
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return HOST_SUPABASE_DIRECT
    return HOST_OTHER


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_documents (
    name       TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Supabase publishes every public table over PostgREST, so a table without RLS
-- is readable and writable by anyone holding the project URL + anon key.  This
-- backend connects as the owning role over plain Postgres, which bypasses RLS,
-- so enabling it with no policies denies the anon/authenticated API while
-- leaving the app untouched.  Idempotent: a no-op once already enabled.
ALTER TABLE app_documents ENABLE ROW LEVEL SECURITY;

-- Optimistic concurrency: every write moves the version on, and ``update``
-- writes only while the row is still at the version it read.  Idempotent, so an
-- existing table gains the column on the next boot.
ALTER TABLE app_documents ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
"""


def _json_default(value: object) -> str:
    """Fallback serializer for non-native types (datetimes, etc.)."""
    return str(value)


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=_json_default)


class DocumentUpdateError(RuntimeError):
    """An update could not be applied: the document kept changing, or its base was unreadable."""


# ---------------------------------------------------------------------------
# File backend (local dev / fallback)
# ---------------------------------------------------------------------------
class FileDocumentStore:
    """Reads/writes each document to its configured JSON file (atomic writes).

    Local development only, where one process owns the files: ``update`` applies
    the change to what is on disk under a process-local lock.
    """

    def __init__(self) -> None:
        self._update_lock = threading.Lock()

    def read(self, name: str) -> ReadResult:
        path_str = _FALLBACK_FILES.get(name)
        if not path_str:
            return ReadResult(ok=False, error=f"unknown document {name!r}")

        path = Path(path_str)
        if not path.exists():
            return ReadResult()

        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("store.file_read_failed", document=name, error=str(exc))
            return ReadResult(ok=False, error=str(exc))

        if not content:
            return ReadResult()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            # A corrupt file is a failure, not an empty document. Reporting it as
            # empty would invite the caller to overwrite it with a fresh one.
            logger.warning("store.file_parse_failed", document=name, error=str(exc))
            return ReadResult(ok=False, error=str(exc))

        if not isinstance(data, dict):
            return ReadResult(ok=False, error="document is not a JSON object")
        return ReadResult(payload=data)

    def write(self, name: str, payload: dict) -> WriteResult:
        path_str = _FALLBACK_FILES.get(name)
        if not path_str:
            logger.warning("store.file_write_skipped_unknown_document", document=name)
            return WriteResult(ok=False, durable=False, error=f"unknown document {name!r}")

        path = Path(path_str)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
            tmp_path.replace(path)  # Atomic on POSIX
            return WriteResult()
        except OSError as exc:
            logger.warning("store.file_write_failed", document=name, error=str(exc))
            # Best-effort cleanup of the temp file; the write already failed and
            # is reported below, so a failure to unlink adds nothing actionable.
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            return WriteResult(ok=False, durable=False, error=str(exc))

    def update(self, name: str, change: DocumentChange) -> UpdateResult:
        """Apply ``change`` to the document on disk; a failed read writes nothing."""
        with self._update_lock:
            current = self.read(name)
            if not current.ok:
                return UpdateResult(ok=False, durable=False, error=current.error)
            payload = change(current.payload)
            written = self.write(name, payload)
        if not written.ok:
            return UpdateResult(ok=False, durable=False, error=written.error)
        return UpdateResult(durable=written.durable, payload=payload)

    def health(self) -> StoreHealth:
        return StoreHealth(
            backend=BACKEND_FILE,
            ok=True,
            host_kind=HOST_OTHER,
            checked_seconds_ago=0.0,
        )

    def ping(self, _max_age_seconds: float = 0.0) -> StoreHealth:
        """The local filesystem is always reachable; nothing to probe.

        The cache window the Postgres backend honours is meaningless here, so
        the parameter exists only to satisfy the ``DocumentStore`` protocol.
        """
        return self.health()


# ---------------------------------------------------------------------------
# Postgres backend (Supabase / production)
# ---------------------------------------------------------------------------
class PostgresDocumentStore:
    """Persists documents to a single JSONB-backed Postgres table.

    Reads fall back to the local JSON file only when Postgres answers and holds
    no row (transparent one-time migration of pre-Postgres data).  A read that
    *fails* reports the failure, and a write that fails is queued in memory and
    retried on the next write rather than being redirected to a disk the host
    may erase at any moment.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._file_fallback = FileDocumentStore()
        self._schema_ready = False
        self._lock = threading.Lock()
        self._pending = PendingWrites()
        # The version of each document as this process last read it.
        self._seen: dict[str, int] = {}
        self._last_ok: bool | None = None
        self._last_error: str | None = None
        self._last_error_id: str | None = None
        self._last_reason: str | None = None
        self._host_kind = classify_host(dsn)
        self._last_checked: float | None = None
        # Fail fast if the driver is missing so the factory can fall back.
        import psycopg  # noqa: F401

    # -- connection helpers -------------------------------------------------
    def _connect(self) -> psycopg.Connection:
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self, conn: psycopg.Connection) -> None:
        if self._schema_ready:
            return
        with self._lock:
            if self._schema_ready:
                return
            conn.execute(_SCHEMA_SQL)
            self._schema_ready = True

    def _record_outcome(self, ok: bool, error: str | None = None) -> str | None:
        """Record the outcome, minting a correlation id for a failure.

        The id is returned so the caller can log it beside the raw message, and
        is held so an unauthenticated health endpoint can name the failure
        without repeating a driver string that contains the database host.
        """
        error_id = new_error_id() if not ok else None
        with self._lock:
            self._last_ok = ok
            self._last_error = error
            self._last_error_id = error_id
            self._last_reason = classify_failure(error) if not ok else None
            self._last_checked = time.monotonic()
        return error_id

    def _remember(self, name: str, version: int | None) -> None:
        """Record the version this process last saw; ``None`` forgets it."""
        with self._lock:
            others = {key: value for key, value in self._seen.items() if key != name}
            self._seen = others if version is None else {**others, name: version}

    @staticmethod
    def _upsert(conn: psycopg.Connection, name: str, payload: dict) -> None:
        from psycopg.types.json import Jsonb

        conn.execute(
            """
            INSERT INTO app_documents (name, payload, updated_at, version)
            VALUES (%s, %s, now(), 1)
            ON CONFLICT (name)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = now(), version = app_documents.version + 1
            """,
            (name, Jsonb(payload, dumps=_dumps)),
        )

    @staticmethod
    def _swap(conn: psycopg.Connection, name: str, payload: dict, version: int | None) -> bool:
        """Store ``payload`` only while the row is still at ``version`` (``None``: still absent)."""
        from psycopg.types.json import Jsonb

        document = Jsonb(payload, dumps=_dumps)
        if version is None:
            cursor = conn.execute(
                """
                INSERT INTO app_documents (name, payload, updated_at, version)
                VALUES (%s, %s, now(), 1)
                ON CONFLICT (name) DO NOTHING
                """,
                (name, document),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE app_documents SET payload = %s, updated_at = now(), version = version + 1
                WHERE name = %s AND version = %s
                """,
                (document, name, version),
            )
        return cursor.rowcount == 1

    def _current(self, conn: psycopg.Connection, name: str) -> ReadResult:
        """The stored document and its row version."""
        row = conn.execute("SELECT payload, version FROM app_documents WHERE name = %s", (name,)).fetchone()
        version = row[1] if row else None
        self._remember(name, version)
        if row and isinstance(row[0], dict):
            return ReadResult(payload=row[0], version=version)
        # No usable row yet: surface any pre-Postgres local file so existing data
        # keeps working and is promoted to Postgres on the next write.
        return dataclasses.replace(self._file_fallback.read(name), version=version)

    def _apply(self, conn: psycopg.Connection, name: str, change: DocumentChange) -> dict:
        """Apply ``change`` to the latest document, re-reading after each lost race."""
        for attempt in range(1, MAX_UPDATE_ATTEMPTS + 1):
            current = self._current(conn, name)
            if not current.ok:
                raise DocumentUpdateError(f"cannot read {name!r} to update it: {current.error}")
            payload = change(current.payload)
            if self._swap(conn, name, payload, current.version):
                self._remember(name, (current.version or 0) + 1)
                return payload
            logger.info("store.pg_update_conflict", document=name, attempt=attempt)
        raise DocumentUpdateError(f"{name!r} changed on each of {MAX_UPDATE_ATTEMPTS} attempts (write conflict)")

    # -- the retry queue ----------------------------------------------------
    def _flush(self, conn: psycopg.Connection) -> None:
        """Replay what an outage queued, before this contact's own statement.

        Runs before every read and write, so a cache re-reading its document
        sees the changes it still holds only in memory. A database error stops
        the replay and leaves the rest queued; the caller's own statement then
        succeeds or fails on its own.
        """
        import psycopg

        documents, changes = self._pending.snapshot()
        try:
            for name, (payload, seen) in documents.items():
                self._replay_document(conn, name, payload, seen)
            for name, queued in changes.items():
                self._replay_changes(conn, name, queued)
        except psycopg.Error as exc:
            logger.warning("store.pg_pending_flush_failed", error=str(exc))

    def _replay_changes(self, conn: psycopg.Connection, name: str, queued: tuple[DocumentChange, ...]) -> None:
        """Re-apply queued changes; one that can no longer apply is dropped so it cannot block every write."""
        import psycopg

        try:
            self._apply(conn, name, compose(queued))
        except psycopg.Error:
            raise
        except Exception as exc:
            logger.exception("store.pg_pending_dropped", document=name, error=str(exc))
        else:
            logger.info("store.pg_pending_flushed", document=name)
        self._pending.drop_changes(name, len(queued))

    def _replay_document(self, conn: psycopg.Connection, name: str, payload: dict, seen: int | None) -> None:
        """Write a queued whole document unless the row moved on since this process read it."""
        if seen is None:
            # Never read here, so there is no version to check: last writer wins.
            self._upsert(conn, name, payload)
        elif not self._swap(conn, name, payload, seen):
            logger.error("store.pg_pending_stale_dropped", document=name, seen_version=seen)
        self._pending.drop_document(name)
        self._remember(name, None)
        logger.info("store.pg_pending_flushed", document=name)

    # -- DocumentStore ------------------------------------------------------
    def read(self, name: str) -> ReadResult:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                self._flush(conn)
                current = self._current(conn, name)
        except Exception as exc:
            error_id = self._record_outcome(False, str(exc))
            logger.exception("store.pg_read_failed", document=name, error=str(exc), error_id=error_id)
            return ReadResult(ok=False, error=str(exc))

        self._record_outcome(True)
        return current

    def write(self, name: str, payload: dict) -> WriteResult:
        # This write supersedes any queued copy of the same document.
        self._pending.drop_document(name)
        with self._lock:
            seen = self._seen.get(name)

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                self._flush(conn)
                self._upsert(conn, name, payload)
        except Exception as exc:
            self._pending.queue_document(name, payload, seen)
            error_id = self._record_outcome(False, str(exc))
            logger.exception(
                "store.pg_write_failed_queued_for_retry",
                document=name,
                error=str(exc),
                error_id=error_id,
            )
            return WriteResult(ok=False, durable=False, error=str(exc))

        self._remember(name, None)
        self._record_outcome(True)
        return WriteResult()

    def update(self, name: str, change: DocumentChange) -> UpdateResult:
        """Apply ``change`` to the latest stored document; see the module docstring."""
        import psycopg

        changes = (*self._pending.take_changes(name), change)

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                self._flush(conn)
                payload = self._apply(conn, name, compose(changes))
        except psycopg.Error as exc:
            self._pending.queue_changes(name, changes)
            error_id = self._record_outcome(False, str(exc))
            logger.exception(
                "store.pg_update_failed_queued_for_retry",
                document=name,
                error=str(exc),
                error_id=error_id,
            )
            return UpdateResult(ok=False, durable=False, error=str(exc))
        except Exception as exc:
            logger.exception("store.pg_update_failed", document=name, error=str(exc))
            return UpdateResult(ok=False, durable=False, error=str(exc))

        self._record_outcome(True)
        return UpdateResult(payload=payload)

    def health(self) -> StoreHealth:
        """Report the last observed outcome. Opens no connection."""
        with self._lock:
            age = time.monotonic() - self._last_checked if self._last_checked is not None else None
            return StoreHealth(
                backend=BACKEND_POSTGRES,
                ok=self._last_ok,
                error=self._last_error,
                error_id=self._last_error_id,
                reason=self._last_reason,
                host_kind=self._host_kind,
                pending_documents=self._pending.names(),
                checked_seconds_ago=age,
            )

    def ping(self, max_age_seconds: float = 0.0) -> StoreHealth:
        """Round-trip the database, refreshing health. Blocking.

        Reuses the last outcome when it is younger than ``max_age_seconds`` —
        ordinary reads and writes are themselves evidence of health, and the
        cap keeps an unauthenticated caller from opening a connection per
        request against a database with a small connection budget.
        """
        health = self.health()
        if (
            health.ok is not None
            and health.checked_seconds_ago is not None
            and health.checked_seconds_ago < max_age_seconds
        ):
            return health

        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as exc:
            error_id = self._record_outcome(False, str(exc))
            logger.exception("store.pg_ping_failed", error=str(exc), error_id=error_id)
        else:
            self._record_outcome(True)
        return self.health()


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------
def _warn_if_ipv6_only_host(dsn: str) -> None:
    """Flag Supabase's direct endpoint, which many hosts cannot reach.

    ``db.<ref>.supabase.co`` publishes no A record. Platforms with IPv4-only
    egress — Render and GitHub Actions runners included — therefore fail every
    connection, and because this store degrades onto a local file the symptom is
    not an error but data that quietly disappears at the next cold start. Saying
    so at startup costs one log line and turns a silent outage into a signpost.
    """
    host = ""
    try:
        from urllib.parse import urlparse

        host = urlparse(dsn).hostname or ""
    except ValueError:
        return

    if host.startswith("db.") and host.endswith(".supabase.co"):
        logger.warning(
            "store.direct_supabase_host_configured",
            host=host,
            hint=(
                "This endpoint is IPv6-only. On an IPv4-only host every connection "
                "will fail and predictions will be written to an ephemeral file. "
                "Use the Supavisor session pooler "
                "(aws-<n>-<region>.pooler.supabase.com:5432) instead."
            ),
        )


def _build_store() -> DocumentStore:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn:
        _warn_if_ipv6_only_host(dsn)
        try:
            store = PostgresDocumentStore(dsn)
            logger.info("store.backend_selected", backend=BACKEND_POSTGRES)
            return store
        except Exception as exc:
            logger.exception("store.postgres_unavailable_using_file", error=str(exc))
    else:
        logger.info("store.backend_selected", backend=BACKEND_FILE)
    return FileDocumentStore()


document_store: DocumentStore = _build_store()
