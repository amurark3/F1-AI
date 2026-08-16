"""Tests for app.data.store — the durable document store and its failure modes.

This module is the fix for a production outage. Small JSON documents (the
prediction cache, the accuracy history, race post-mortems) used to live only on
the container's disk, which Render erases on every deploy; and once Postgres
arrived, a *failed* read was indistinguishable from an empty database, so a
paused Supabase project turned into empty predictions with no error anywhere.

The behaviours pinned here are therefore the ones that outage taught:

  * a failed read reports ``ok=False`` and never masquerades as an absent
    document — including for a corrupt local file;
  * a failed Postgres write is **not** diverted to the local disk. It is queued
    in memory and retried, because on an ephemeral host that redirection turns
    a visible outage into silent data loss;
  * ``durable`` distinguishes "reached the backend the deployment relies on"
    from "reached a disk that may vanish";
  * health is reported in two views, and the client-safe one never carries the
    driver message that names the host, port and user.

``DATABASE_URL`` is cleared by conftest, so the file backend is the default.
The Postgres path is exercised by faking ``psycopg.connect`` — the autouse
socket blocker means no real connection is possible.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import psycopg
import pytest

from app.config import PREDICTION_CACHE_PATH, PREDICTION_HISTORY_PATH
from app.data import store as store_module
from app.data.store import (
    BACKEND_FILE,
    BACKEND_POSTGRES,
    DOCUMENT_PREDICTION_CACHE,
    DOCUMENT_PREDICTION_HISTORY,
    DOCUMENT_PREDICTION_POSTMORTEMS,
    HOST_OTHER,
    HOST_SUPABASE_DIRECT,
    HOST_SUPABASE_POOLER,
    REASON_AUTH,
    REASON_DNS,
    REASON_POOLER_USER,
    REASON_REFUSED,
    REASON_TIMEOUT,
    REASON_TLS,
    REASON_UNKNOWN,
    FileDocumentStore,
    PostgresDocumentStore,
    classify_failure,
    classify_host,
)

POOLER_DSN = "postgresql://postgres.abcdefgh:pw@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"
DIRECT_DSN = "postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres"

# What psycopg actually says when a Supabase project is paused. Every fragment
# of it is infrastructure detail no client may see.
DRIVER_MESSAGE = (
    'connection to server at "db.abcdefgh.supabase.co" (11.22.33.44), port 5432 '
    'failed: FATAL: password authentication failed for user "postgres"'
)
# Note: the bare word "postgres" is NOT a secret here — `backend` is a
# deliberate part of the client-safe view, and it is literally "postgres". What
# must not escape is the connection detail: host, address, port, and the fact
# that it was the *user* named postgres whose password failed.
SECRET_FRAGMENTS = ("db.abcdefgh", "supabase.co", "11.22.33.44", "5432", "password", 'user "postgres"')


# ---------------------------------------------------------------------------
# psycopg fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, row: tuple | None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    """Context-managed stand-in for ``psycopg.Connection``."""

    def __init__(self, row: tuple | None = None, fail_on: str | None = None) -> None:
        self._row = row
        self._fail_on = fail_on
        self.statements: list[tuple[str, object]] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self._fail_on is not None and self._fail_on in sql:
            raise psycopg.OperationalError(DRIVER_MESSAGE)
        return _FakeCursor(self._row)


def _install_connect(monkeypatch, connection=None, error=None):
    """Replace the psycopg entry point ``PostgresDocumentStore._connect`` reaches for."""
    calls: list[tuple] = []

    def fake_connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        if error is not None:
            raise error
        return connection

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    return calls


@pytest.fixture
def fallback_files(monkeypatch, tmp_path):
    """Point every document's fallback file at a throwaway directory."""
    mapping = {
        DOCUMENT_PREDICTION_CACHE: str(tmp_path / "cache.json"),
        DOCUMENT_PREDICTION_HISTORY: str(tmp_path / "history.json"),
        DOCUMENT_PREDICTION_POSTMORTEMS: str(tmp_path / "nested" / "postmortems.json"),
    }
    monkeypatch.setattr(store_module, "_FALLBACK_FILES", mapping)
    return {name: Path(path) for name, path in mapping.items()}


@pytest.fixture
def pg_store(monkeypatch):
    """A Postgres store whose driver never opens a socket."""
    _install_connect(monkeypatch, connection=_FakeConnection())
    return PostgresDocumentStore(POOLER_DSN)


# ---------------------------------------------------------------------------
# classify_failure — each code maps to a distinct operator action
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('could not translate host name "db.x.supabase.co" to address', REASON_DNS),
        ("Name or service not known", REASON_DNS),
        ("nodename nor servname provided, or not known", REASON_DNS),
        ("Failed to resolve host db.x.supabase.co", REASON_DNS),
        ("Temporary failure in name resolution", REASON_DNS),
        ("ENOIDENTIFIER", REASON_POOLER_USER),
        ("No tenant identifier found in the connection", REASON_POOLER_USER),
        ("ENOTFOUND", REASON_POOLER_USER),
        ("Tenant/User not recognised", REASON_POOLER_USER),
        ("Tenant or user not found", REASON_POOLER_USER),
        ('FATAL: password authentication failed for user "postgres"', REASON_AUTH),
        ("SCRAM authentication failed", REASON_AUTH),
        ("no pg_hba.conf entry for host", REASON_AUTH),
        ('role "postgres" does not exist', REASON_AUTH),
        ("Connection refused", REASON_REFUSED),
        ("timeout expired", REASON_TIMEOUT),
        ("connection attempt timed out", REASON_TIMEOUT),
        ("SSL SYSCALL error: EOF detected", REASON_TLS),
        ("something nobody has seen before", REASON_UNKNOWN),
        ("", REASON_UNKNOWN),
    ],
)
def test_classify_failure_maps_driver_messages_to_client_safe_codes(message, expected):
    assert classify_failure(message) == expected


@pytest.mark.unit
def test_classify_failure_tolerates_a_missing_message():
    assert classify_failure(None) == REASON_UNKNOWN


@pytest.mark.unit
def test_classify_failure_prefers_the_pooler_signature_over_the_generic_one():
    """Supavisor's ENOTFOUND is a tenant problem, not DNS — the two need different fixes."""
    assert classify_failure("Tenant or user not found: ENOTFOUND") == REASON_POOLER_USER


# ---------------------------------------------------------------------------
# classify_host — "did my connection string change take effect?" without naming it
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        (POOLER_DSN, HOST_SUPABASE_POOLER),
        (DIRECT_DSN, HOST_SUPABASE_DIRECT),
        ("postgresql://u:p@DB.ABCDEFGH.SUPABASE.CO:5432/postgres", HOST_SUPABASE_DIRECT),
        ("postgresql://u:p@localhost:5432/postgres", HOST_OTHER),
        ("postgresql://u:p@rds.amazonaws.com:5432/postgres", HOST_OTHER),
        ("", HOST_OTHER),
        # Looks Supabase-ish but is neither endpoint shape.
        ("postgresql://u:p@abcdefgh.supabase.co:5432/postgres", HOST_OTHER),
    ],
)
def test_classify_host_labels_the_endpoint_shape(dsn, expected):
    assert classify_host(dsn) == expected


@pytest.mark.unit
def test_classify_host_never_returns_the_host_itself():
    assert "abcdefgh" not in classify_host(DIRECT_DSN)


@pytest.mark.unit
def test_classify_host_falls_back_to_other_on_an_unparseable_dsn():
    """An unbracketed IPv6 literal makes urlparse raise; that must not crash startup."""
    assert classify_host("postgresql://u:p@[::1/postgres") == HOST_OTHER


# ---------------------------------------------------------------------------
# FileDocumentStore — reads
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_file_read_returns_the_stored_document(fallback_files):
    fallback_files[DOCUMENT_PREDICTION_CACHE].write_text('{"2026": {"round": 1}}', encoding="utf-8")

    result = FileDocumentStore().read(DOCUMENT_PREDICTION_CACHE)

    assert result.ok is True
    assert result.payload == {"2026": {"round": 1}}


@pytest.mark.unit
def test_file_read_of_an_unknown_document_is_a_failure_not_an_empty_document(fallback_files):
    result = FileDocumentStore().read("not_a_document")

    assert result.ok is False
    assert result.missing is False
    assert "not_a_document" in result.error


@pytest.mark.integration
def test_file_read_reports_a_missing_file_as_an_absent_document(fallback_files):
    result = FileDocumentStore().read(DOCUMENT_PREDICTION_HISTORY)

    assert result.ok is True
    assert result.missing is True


@pytest.mark.integration
@pytest.mark.parametrize("content", ["", "   \n  "], ids=["empty", "whitespace"])
def test_file_read_treats_an_empty_file_as_an_absent_document(fallback_files, content):
    fallback_files[DOCUMENT_PREDICTION_CACHE].write_text(content, encoding="utf-8")

    assert FileDocumentStore().read(DOCUMENT_PREDICTION_CACHE).missing is True


@pytest.mark.integration
def test_file_read_reports_a_corrupt_file_as_a_failure(fallback_files):
    """Calling a truncated file "empty" invites the caller to overwrite the survivors."""
    fallback_files[DOCUMENT_PREDICTION_HISTORY].write_text('{"2026": {"rou', encoding="utf-8")

    result = FileDocumentStore().read(DOCUMENT_PREDICTION_HISTORY)

    assert result.ok is False
    assert result.missing is False
    assert result.payload is None


@pytest.mark.integration
@pytest.mark.parametrize("content", ["[1, 2, 3]", '"a string"', "42", "null"])
def test_file_read_rejects_json_that_is_not_an_object(fallback_files, content):
    fallback_files[DOCUMENT_PREDICTION_CACHE].write_text(content, encoding="utf-8")

    result = FileDocumentStore().read(DOCUMENT_PREDICTION_CACHE)

    assert result.ok is False
    assert result.error == "document is not a JSON object"


@pytest.mark.integration
def test_file_read_reports_an_unreadable_file_as_a_failure(fallback_files, monkeypatch):
    """A permission or IO error is an outage, not an empty database."""
    path = fallback_files[DOCUMENT_PREDICTION_CACHE]
    path.write_text("{}", encoding="utf-8")

    def refuse(self, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", refuse)

    result = FileDocumentStore().read(DOCUMENT_PREDICTION_CACHE)

    assert result.ok is False
    assert result.missing is False


# ---------------------------------------------------------------------------
# FileDocumentStore — writes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_file_write_round_trips_and_leaves_no_temp_file(fallback_files):
    path = fallback_files[DOCUMENT_PREDICTION_CACHE]

    result = FileDocumentStore().write(DOCUMENT_PREDICTION_CACHE, {"2026": [1, 2]})

    assert (result.ok, result.durable) == (True, True)
    assert json.loads(path.read_text(encoding="utf-8")) == {"2026": [1, 2]}
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.integration
def test_file_write_creates_missing_parent_directories(fallback_files):
    path = fallback_files[DOCUMENT_PREDICTION_POSTMORTEMS]
    assert not path.parent.exists()

    assert FileDocumentStore().write(DOCUMENT_PREDICTION_POSTMORTEMS, {"a": 1}).ok is True
    assert path.exists()


@pytest.mark.integration
def test_file_write_serializes_values_json_cannot_encode(fallback_files):
    """Prediction payloads carry datetimes; they must not blow up the write."""
    from datetime import datetime

    moment = datetime(2026, 3, 15, 14, 0, 0)

    FileDocumentStore().write(DOCUMENT_PREDICTION_CACHE, {"generated_at": moment})

    stored = json.loads(fallback_files[DOCUMENT_PREDICTION_CACHE].read_text(encoding="utf-8"))
    assert stored == {"generated_at": str(moment)}


@pytest.mark.unit
def test_file_write_of_an_unknown_document_fails_without_touching_disk(fallback_files, tmp_path):
    result = FileDocumentStore().write("not_a_document", {"a": 1})

    assert (result.ok, result.durable) == (False, False)
    assert "not_a_document" in result.error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_file_write_failure_is_reported_and_the_temp_file_cleaned_up(fallback_files, monkeypatch):
    written: list[Path] = []

    def refuse(self, _text, **_kwargs):
        written.append(self)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_text", refuse)

    result = FileDocumentStore().write(DOCUMENT_PREDICTION_CACHE, {"a": 1})

    assert (result.ok, result.durable) == (False, False)
    assert "No space left" in result.error
    assert not written[0].exists(), "the half-written temp file must not survive"


@pytest.mark.integration
def test_file_write_survives_a_failed_temp_file_cleanup(fallback_files, monkeypatch):
    """A read-only volume fails the unlink too; that adds nothing and must not raise."""
    monkeypatch.setattr(Path, "write_text", lambda *_a, **_k: (_ for _ in ()).throw(OSError("full")))
    monkeypatch.setattr(Path, "unlink", lambda *_a, **_k: (_ for _ in ()).throw(OSError("read-only")))

    result = FileDocumentStore().write(DOCUMENT_PREDICTION_CACHE, {"a": 1})

    assert result.ok is False


# ---------------------------------------------------------------------------
# FileDocumentStore — health
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_file_health_reports_the_local_filesystem_as_reachable():
    health = FileDocumentStore().health()

    assert (health.backend, health.ok, health.host_kind) == (BACKEND_FILE, True, HOST_OTHER)
    assert health.checked_seconds_ago == 0.0
    assert health.pending_documents == ()


@pytest.mark.unit
def test_file_ping_ignores_the_cache_window_and_matches_health():
    """There is no connection to cache a verdict for, so the window is inert.

    Called positionally, which is how `routers/readiness.py` invokes it. The
    keyword form the `DocumentStore` protocol advertises does NOT work here —
    `FileDocumentStore.ping` names the parameter `_max_age_seconds`. See
    `test_file_ping_does_not_honour_the_protocol_keyword` below.
    """
    store = FileDocumentStore()

    assert store.ping(3600).as_dict() == store.health().as_dict()


@pytest.mark.unit
def test_file_ping_does_not_honour_the_protocol_keyword():
    """Documents a real signature mismatch against the DocumentStore protocol.

    `store_types.DocumentStore.ping` declares `max_age_seconds`, and
    `PostgresDocumentStore.ping` uses that name — but `FileDocumentStore.ping`
    names it `_max_age_seconds`, so the keyword form raises. Today every caller
    passes positionally, so this is latent rather than broken in production;
    the first caller to use the documented keyword against the JSON fallback
    gets a TypeError. This test exists so that fact is recorded rather than
    discovered in an incident.
    """
    store = FileDocumentStore()

    with pytest.raises(TypeError, match="max_age_seconds"):
        store.ping(max_age_seconds=3600)


@pytest.mark.unit
def test_file_health_never_reports_an_error():
    assert FileDocumentStore().health().as_log_dict()["error"] is None


# ---------------------------------------------------------------------------
# PostgresDocumentStore — construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_postgres_store_starts_in_the_unknown_health_state(pg_store):
    health = pg_store.health()

    assert health.backend == BACKEND_POSTGRES
    assert health.ok is None, "no operation attempted yet — unknown is not healthy"
    assert health.checked_seconds_ago is None
    assert health.host_kind == HOST_SUPABASE_POOLER


@pytest.mark.unit
def test_postgres_store_refuses_to_construct_without_the_driver(monkeypatch):
    """The factory relies on this failing fast so it can pick the file backend."""
    monkeypatch.setitem(sys.modules, "psycopg", None)

    with pytest.raises(ImportError):
        PostgresDocumentStore(POOLER_DSN)


@pytest.mark.unit
def test_postgres_connect_passes_the_dsn_with_autocommit(monkeypatch, pg_store):
    calls = _install_connect(monkeypatch, connection=_FakeConnection())

    pg_store._connect()

    assert calls == [(POOLER_DSN, {"autocommit": True})]


# ---------------------------------------------------------------------------
# PostgresDocumentStore — schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_schema_is_created_once_and_not_repeated(pg_store):
    conn = _FakeConnection()

    pg_store._ensure_schema(conn)
    pg_store._ensure_schema(conn)

    assert len(conn.statements) == 1
    assert "CREATE TABLE IF NOT EXISTS app_documents" in conn.statements[0][0]


@pytest.mark.unit
def test_schema_creation_is_skipped_when_another_thread_won_the_lock(pg_store):
    """The inner half of the double-checked lock: the winner already ran the DDL."""

    class _RaceLock:
        def __enter__(self):
            pg_store._schema_ready = True
            return self

        def __exit__(self, *_exc):
            return False

    pg_store._lock = _RaceLock()
    conn = _FakeConnection()

    pg_store._ensure_schema(conn)

    assert conn.statements == []


# ---------------------------------------------------------------------------
# PostgresDocumentStore — reads
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_postgres_read_returns_the_stored_row(monkeypatch, pg_store):
    conn = _FakeConnection(row=({"2026": {"round": 1}},))
    _install_connect(monkeypatch, connection=conn)

    result = pg_store.read(DOCUMENT_PREDICTION_CACHE)

    assert result.payload == {"2026": {"round": 1}}
    assert pg_store.health().ok is True
    assert conn.statements[-1][1] == (DOCUMENT_PREDICTION_CACHE,)


@pytest.mark.integration
def test_postgres_read_promotes_a_pre_postgres_local_file_when_no_row_exists(monkeypatch, pg_store, fallback_files):
    """Existing on-disk data keeps working and is promoted on the next write."""
    fallback_files[DOCUMENT_PREDICTION_HISTORY].write_text('{"legacy": true}', encoding="utf-8")
    _install_connect(monkeypatch, connection=_FakeConnection(row=None))

    result = pg_store.read(DOCUMENT_PREDICTION_HISTORY)

    assert result.payload == {"legacy": True}
    assert pg_store.health().ok is True, "an empty table is a healthy answer"


@pytest.mark.unit
def test_postgres_read_falls_back_when_the_row_payload_is_not_an_object(monkeypatch, pg_store, fallback_files):
    _install_connect(monkeypatch, connection=_FakeConnection(row=("not a dict",)))

    assert pg_store.read(DOCUMENT_PREDICTION_CACHE).missing is True


@pytest.mark.unit
def test_postgres_read_failure_is_not_reported_as_an_empty_document(monkeypatch, pg_store):
    """The outage itself: a paused project must not read as "no data yet"."""
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    result = pg_store.read(DOCUMENT_PREDICTION_CACHE)

    assert result.ok is False
    assert result.missing is False
    assert result.payload is None


@pytest.mark.integration
def test_postgres_read_failure_does_not_silently_serve_the_local_file(monkeypatch, pg_store, fallback_files):
    """A stale ephemeral copy presented as live data is how the outage stayed invisible."""
    fallback_files[DOCUMENT_PREDICTION_CACHE].write_text('{"stale": true}', encoding="utf-8")
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    result = pg_store.read(DOCUMENT_PREDICTION_CACHE)

    assert result.ok is False
    assert result.payload is None


@pytest.mark.unit
def test_postgres_read_failure_records_a_classified_health_state(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    pg_store.read(DOCUMENT_PREDICTION_CACHE)
    health = pg_store.health()

    assert health.ok is False
    assert health.reason == REASON_AUTH
    assert health.error_id is not None
    assert health.checked_seconds_ago is not None


@pytest.mark.unit
def test_postgres_read_failure_health_never_leaks_the_driver_message(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    pg_store.read(DOCUMENT_PREDICTION_CACHE)
    serialized = repr(pg_store.health().as_dict())

    for fragment in SECRET_FRAGMENTS:
        assert fragment not in serialized, f"{fragment!r} reached the unauthenticated health view"
    assert pg_store.health().as_log_dict()["error"] == DRIVER_MESSAGE


@pytest.mark.unit
def test_a_successful_read_clears_a_previous_failure(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))
    pg_store.read(DOCUMENT_PREDICTION_CACHE)

    _install_connect(monkeypatch, connection=_FakeConnection(row=({"a": 1},)))
    pg_store.read(DOCUMENT_PREDICTION_CACHE)

    health = pg_store.health()
    assert (health.ok, health.error, health.error_id, health.reason) == (True, None, None, None)


# ---------------------------------------------------------------------------
# PostgresDocumentStore — writes and the retry queue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_postgres_write_upserts_the_payload(monkeypatch, pg_store):
    conn = _FakeConnection()
    _install_connect(monkeypatch, connection=conn)

    result = pg_store.write(DOCUMENT_PREDICTION_CACHE, {"a": 1})

    assert (result.ok, result.durable) == (True, True)
    sql, params = conn.statements[-1]
    assert "ON CONFLICT (name)" in sql
    assert params[0] == DOCUMENT_PREDICTION_CACHE
    assert params[1].obj == {"a": 1}


@pytest.mark.unit
def test_postgres_write_serializes_values_json_cannot_encode(monkeypatch, pg_store):
    from datetime import datetime

    conn = _FakeConnection()
    _install_connect(monkeypatch, connection=conn)
    moment = datetime(2026, 3, 15, 14, 0, 0)

    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"generated_at": moment})

    jsonb = conn.statements[-1][1][1]
    # Jsonb defers serialization, so exercise the dumps hook the store installed.
    assert json.loads(jsonb.dumps(jsonb.obj)) == {"generated_at": str(moment)}


@pytest.mark.unit
def test_failed_postgres_write_is_queued_rather_than_diverted_to_disk(monkeypatch, pg_store, fallback_files):
    """Writing to an ephemeral disk instead would turn a visible outage into data loss."""
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    result = pg_store.write(DOCUMENT_PREDICTION_CACHE, {"a": 1})

    assert (result.ok, result.durable) == (False, False)
    assert not fallback_files[DOCUMENT_PREDICTION_CACHE].exists()
    assert pg_store.health().pending_documents == (DOCUMENT_PREDICTION_CACHE,)


@pytest.mark.unit
def test_a_queued_write_is_flushed_on_the_next_successful_write(monkeypatch, pg_store):
    """A transient outage self-heals: nothing is lost and nothing needs an operator."""
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))
    pg_store.write(DOCUMENT_PREDICTION_HISTORY, {"queued": True})

    conn = _FakeConnection()
    _install_connect(monkeypatch, connection=conn)
    result = pg_store.write(DOCUMENT_PREDICTION_CACHE, {"fresh": True})

    assert result.durable is True
    upserted = [params[0] for sql, params in conn.statements if params is not None]
    assert upserted == [DOCUMENT_PREDICTION_HISTORY, DOCUMENT_PREDICTION_CACHE]
    assert pg_store.health().pending_documents == ()


@pytest.mark.unit
def test_a_newer_write_supersedes_the_queued_copy_of_the_same_document(monkeypatch, pg_store):
    """Replaying the stale copy after the fresh one would resurrect old data."""
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))
    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"version": "old"})

    conn = _FakeConnection()
    _install_connect(monkeypatch, connection=conn)
    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"version": "new"})

    payloads = [params[1].obj for sql, params in conn.statements if params is not None]
    assert payloads == [{"version": "new"}]


@pytest.mark.unit
def test_a_repeated_failure_keeps_only_the_latest_payload_queued(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))

    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"version": "old"})
    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"version": "new"})

    assert pg_store._pending == {DOCUMENT_PREDICTION_CACHE: {"version": "new"}}


@pytest.mark.unit
def test_write_failure_health_reports_the_pending_backlog_without_the_driver_message(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError(DRIVER_MESSAGE))
    pg_store.write(DOCUMENT_PREDICTION_CACHE, {"a": 1})
    pg_store.write(DOCUMENT_PREDICTION_HISTORY, {"b": 2})

    payload = pg_store.health().as_dict()

    assert payload["pending_documents"] == sorted([DOCUMENT_PREDICTION_CACHE, DOCUMENT_PREDICTION_HISTORY])
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in repr(payload)


# ---------------------------------------------------------------------------
# PostgresDocumentStore — ping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ping_round_trips_the_database_when_no_health_is_known(monkeypatch, pg_store):
    conn = _FakeConnection(row=(1,))
    _install_connect(monkeypatch, connection=conn)

    health = pg_store.ping()

    assert health.ok is True
    assert conn.statements == [("SELECT 1", None)]


@pytest.mark.unit
def test_ping_reports_a_connection_failure_with_a_classified_reason(monkeypatch, pg_store):
    _install_connect(monkeypatch, error=psycopg.OperationalError("could not translate host name to address"))

    health = pg_store.ping()

    assert health.ok is False
    assert health.reason == REASON_DNS
    assert "could not translate" not in repr(health.as_dict())


@pytest.mark.unit
def test_ping_reuses_a_recent_result_instead_of_opening_a_connection(monkeypatch, pg_store):
    """An unauthenticated endpoint must not burn a connection per request."""
    _install_connect(monkeypatch, connection=_FakeConnection(row=({"a": 1},)))
    pg_store.read(DOCUMENT_PREDICTION_CACHE)

    calls = _install_connect(monkeypatch, error=AssertionError("ping must not reconnect"))
    health = pg_store.ping(max_age_seconds=60.0)

    assert calls == []
    assert health.ok is True


@pytest.mark.unit
def test_ping_reprobes_once_the_cached_result_is_too_old(monkeypatch, pg_store):
    _install_connect(monkeypatch, connection=_FakeConnection(row=({"a": 1},)))
    pg_store.read(DOCUMENT_PREDICTION_CACHE)

    conn = _FakeConnection(row=(1,))
    calls = _install_connect(monkeypatch, connection=conn)
    pg_store.ping(max_age_seconds=0.0)

    assert len(calls) == 1


@pytest.mark.unit
def test_ping_probes_when_health_is_unknown_even_within_the_cache_window(monkeypatch, pg_store):
    """`ok is None` is not a result to reuse — that is the state the outage hid behind."""
    calls = _install_connect(monkeypatch, connection=_FakeConnection(row=(1,)))

    assert pg_store.ping(max_age_seconds=3600.0).ok is True
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Startup: IPv6-only host warning and backend selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_direct_supabase_host_is_flagged_at_startup(capsys):
    """IPv6-only endpoint + IPv4-only host = every write silently landing on scratch disk."""
    store_module._warn_if_ipv6_only_host(DIRECT_DSN)

    logged = capsys.readouterr().out
    assert "store.direct_supabase_host_configured" in logged
    assert "pooler.supabase.com" in logged, "the warning must name the fix"


@pytest.mark.unit
@pytest.mark.parametrize(
    "dsn",
    [POOLER_DSN, "postgresql://u:p@localhost:5432/postgres", "postgresql://u:p@[::1/postgres", ""],
    ids=["pooler", "localhost", "unparseable", "empty"],
)
def test_no_ipv6_warning_for_other_hosts(capsys, dsn):
    store_module._warn_if_ipv6_only_host(dsn)

    assert "store.direct_supabase_host_configured" not in capsys.readouterr().out


@pytest.mark.unit
def test_no_database_url_selects_the_file_backend(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert isinstance(store_module._build_store(), FileDocumentStore)


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "whitespace"])
def test_a_blank_database_url_selects_the_file_backend(monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)

    assert isinstance(store_module._build_store(), FileDocumentStore)


@pytest.mark.unit
def test_a_configured_database_url_selects_the_postgres_backend(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"  {POOLER_DSN}  ")
    _install_connect(monkeypatch, connection=_FakeConnection())

    store = store_module._build_store()

    assert isinstance(store, PostgresDocumentStore)
    assert store._dsn == POOLER_DSN, "surrounding whitespace must be stripped"


@pytest.mark.unit
def test_a_missing_driver_degrades_to_the_file_backend_instead_of_crashing_boot(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", POOLER_DSN)
    monkeypatch.setitem(sys.modules, "psycopg", None)

    store = store_module._build_store()

    assert isinstance(store, FileDocumentStore)
    assert "store.postgres_unavailable_using_file" in capsys.readouterr().out


@pytest.mark.unit
def test_the_module_singleton_uses_the_file_backend_under_the_test_environment():
    """conftest clears DATABASE_URL, so the fallback path is what the suite runs against."""
    assert isinstance(store_module.document_store, FileDocumentStore)
    assert store_module.document_store.health().backend == BACKEND_FILE


@pytest.mark.unit
def test_fallback_files_are_wired_to_the_configured_paths():
    mapping = store_module._FALLBACK_FILES

    assert mapping[DOCUMENT_PREDICTION_CACHE] == PREDICTION_CACHE_PATH
    assert mapping[DOCUMENT_PREDICTION_HISTORY] == PREDICTION_HISTORY_PATH
    assert mapping[DOCUMENT_PREDICTION_POSTMORTEMS].endswith("prediction_postmortems.json")
