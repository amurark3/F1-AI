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
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import structlog

from app.api.errors import new_error_id
from app.config import PREDICTION_CACHE_PATH, PREDICTION_HISTORY_PATH
from app.data.store_types import DocumentStore, ReadResult, StoreHealth, WriteResult

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

BACKEND_POSTGRES = "postgres"
BACKEND_FILE = "file"

# Client-safe classification of a configured host. Answers "did my connection
# string change take effect?" without naming the host or project.
HOST_SUPABASE_DIRECT = "supabase_direct"  # db.<ref>.supabase.co — IPv6-only
HOST_SUPABASE_POOLER = "supabase_pooler"  # <region>.pooler.supabase.com
HOST_OTHER = "other"

# Client-safe classification of a connection failure. Each maps to a distinct
# operator action, which is the whole point of separating them.
REASON_DNS = "dns_unresolved"          # host does not resolve — wrong name, or
                                       # IPv6-only host on an IPv4-only network
REASON_REFUSED = "connection_refused"  # resolved, nothing listening — wrong port
REASON_AUTH = "auth_failed"            # reached it, credentials rejected
REASON_TIMEOUT = "timeout"             # no answer — firewall or egress block
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
"""


def _json_default(value: object) -> str:
    """Fallback serializer for non-native types (datetimes, etc.)."""
    return str(value)


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=_json_default)


# ---------------------------------------------------------------------------
# File backend (local dev / fallback)
# ---------------------------------------------------------------------------
class FileDocumentStore:
    """Reads/writes each document to its configured JSON file (atomic writes)."""

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
            tmp_path.write_text(
                json.dumps(payload, indent=2, default=_json_default), encoding="utf-8"
            )
            tmp_path.replace(path)  # Atomic on POSIX
            return WriteResult()
        except OSError as exc:
            logger.warning("store.file_write_failed", document=name, error=str(exc))
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return WriteResult(ok=False, durable=False, error=str(exc))

    def health(self) -> StoreHealth:
        return StoreHealth(
            backend=BACKEND_FILE,
            ok=True,
            host_kind=HOST_OTHER,
            checked_seconds_ago=0.0,
        )

    def ping(self, max_age_seconds: float = 0.0) -> StoreHealth:
        """The local filesystem is always reachable; nothing to probe."""
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
        self._pending: dict[str, dict] = {}
        self._last_ok: bool | None = None
        self._last_error: str | None = None
        self._last_error_id: str | None = None
        self._last_reason: str | None = None
        self._host_kind = classify_host(dsn)
        self._last_checked: float | None = None
        # Fail fast if the driver is missing so the factory can fall back.
        import psycopg  # noqa: F401

    # -- connection helpers -------------------------------------------------
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

    @staticmethod
    def _upsert(conn, name: str, payload: dict) -> None:
        from psycopg.types.json import Jsonb

        conn.execute(
            """
            INSERT INTO app_documents (name, payload, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (name)
            DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
            """,
            (name, Jsonb(payload, dumps=_dumps)),
        )

    # -- DocumentStore ------------------------------------------------------
    def read(self, name: str) -> ReadResult:
        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT payload FROM app_documents WHERE name = %s", (name,)
                ).fetchone()
        except Exception as exc:
            error_id = self._record_outcome(False, str(exc))
            logger.error(
                "store.pg_read_failed", document=name, error=str(exc), error_id=error_id
            )
            return ReadResult(ok=False, error=str(exc))

        self._record_outcome(True)
        if row and isinstance(row[0], dict):
            return ReadResult(payload=row[0])

        # No row yet — surface any pre-Postgres local file so existing data keeps
        # working and is promoted to Postgres on the next write.
        return self._file_fallback.read(name)

    def write(self, name: str, payload: dict) -> WriteResult:
        with self._lock:
            # This write supersedes any queued copy of the same document.
            self._pending.pop(name, None)
            queued = dict(self._pending)

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                for queued_name, queued_payload in queued.items():
                    self._upsert(conn, queued_name, queued_payload)
                    with self._lock:
                        self._pending.pop(queued_name, None)
                    logger.info("store.pg_pending_flushed", document=queued_name)
                self._upsert(conn, name, payload)
        except Exception as exc:
            with self._lock:
                self._pending[name] = payload
            error_id = self._record_outcome(False, str(exc))
            logger.error(
                "store.pg_write_failed_queued_for_retry",
                document=name,
                error=str(exc),
                error_id=error_id,
            )
            return WriteResult(ok=False, durable=False, error=str(exc))

        self._record_outcome(True)
        return WriteResult()

    def health(self) -> StoreHealth:
        """Report the last observed outcome. Opens no connection."""
        with self._lock:
            age = (
                time.monotonic() - self._last_checked
                if self._last_checked is not None
                else None
            )
            return StoreHealth(
                backend=BACKEND_POSTGRES,
                ok=self._last_ok,
                error=self._last_error,
                error_id=self._last_error_id,
                reason=self._last_reason,
                host_kind=self._host_kind,
                pending_documents=tuple(sorted(self._pending)),
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
            logger.error("store.pg_ping_failed", error=str(exc), error_id=error_id)
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
            logger.error("store.postgres_unavailable_using_file", error=str(exc))
    else:
        logger.info("store.backend_selected", backend=BACKEND_FILE)
    return FileDocumentStore()


document_store: DocumentStore = _build_store()
