"""Tests for app.data.store_types — the result types that ended a real outage.

``read`` used to return a bare ``dict | None``, so "no such document" and "the
database is unreachable" looked identical to every caller. While the Postgres
project was paused the app therefore served empty predictions and reported no
error at all.

Two properties are pinned here, both of them the reason these types exist:

1. ``ReadResult.missing`` is true *only* when the backend answered. A failed
   read must never look like an empty document.
2. ``StoreHealth.as_dict`` is the client-safe view and must never carry the raw
   driver message, which for a connection failure names the host, port,
   database and user. ``/health`` is unauthenticated, so that payload is
   reconnaissance for anyone who asks.
"""

from __future__ import annotations

import inspect

import pytest

from app.data.store_types import DocumentStore, ReadResult, StoreHealth, WriteResult

# The exact shape psycopg produces when a Supabase project is paused. Every
# fragment below is infrastructure detail a client has no business seeing.
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
# ReadResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_read_result_defaults_to_a_successful_empty_read():
    result = ReadResult()

    assert result.ok is True
    assert result.payload is None
    assert result.error is None
    assert result.missing is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("result", "expected_missing"),
    [
        (ReadResult(payload={"a": 1}), False),
        (ReadResult(payload=None), True),
        (ReadResult(ok=False, error="backend down"), False),
        (ReadResult(ok=False, payload={"a": 1}, error="stale"), False),
    ],
    ids=["document-present", "document-absent", "backend-failed", "backend-failed-with-payload"],
)
def test_read_result_missing_is_only_true_when_the_backend_answered(result, expected_missing):
    """A failed read must not be mistaken for an empty document — the outage bug."""
    assert result.missing is expected_missing


@pytest.mark.unit
def test_failed_read_is_distinguishable_from_an_absent_document():
    absent = ReadResult()
    failed = ReadResult(ok=False, error=DRIVER_MESSAGE)

    # Both carry no payload; only `ok`/`missing` separate them.
    assert absent.payload == failed.payload
    assert (absent.ok, absent.missing) != (failed.ok, failed.missing)


@pytest.mark.unit
def test_read_result_is_immutable():
    result = ReadResult(payload={"a": 1})

    with pytest.raises(AttributeError):
        result.ok = False


# ---------------------------------------------------------------------------
# WriteResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_write_result_defaults_to_a_durable_success():
    result = WriteResult()

    assert (result.ok, result.durable, result.error) == (True, True, None)


@pytest.mark.unit
def test_write_result_can_report_success_that_is_not_durable():
    """A write that landed only on an ephemeral container disk succeeded but is not durable."""
    result = WriteResult(ok=True, durable=False)

    assert result.ok is True
    assert result.durable is False


@pytest.mark.unit
def test_write_result_is_immutable():
    result = WriteResult()

    with pytest.raises(AttributeError):
        result.durable = False


# ---------------------------------------------------------------------------
# StoreHealth
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_store_health_starts_in_the_unknown_state():
    """`ok is None` means "never probed" — reporting that as healthy hides the outage."""
    health = StoreHealth(backend="postgres")

    assert health.ok is None
    assert health.as_dict()["ok"] is None
    assert health.pending_documents == ()


@pytest.mark.unit
def test_as_dict_never_leaks_the_driver_message():
    health = StoreHealth(
        backend="postgres",
        ok=False,
        error=DRIVER_MESSAGE,
        error_id="a1b2c3d4e5f6",
        reason="auth_failed",
        host_kind="supabase_direct",
    )

    payload = health.as_dict()
    serialized = repr(payload)

    assert "error" not in payload
    assert DRIVER_MESSAGE not in serialized
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in serialized, f"{fragment!r} leaked into the client-safe view"


@pytest.mark.unit
def test_as_dict_keys_are_a_fixed_client_safe_set():
    """Pinned so a new field cannot be added to the type and reach clients unreviewed."""
    payload = StoreHealth(backend="postgres", error=DRIVER_MESSAGE).as_dict()

    assert set(payload) == {
        "backend",
        "ok",
        "error_id",
        "reason",
        "host_kind",
        "pending_documents",
        "checked_seconds_ago",
    }


@pytest.mark.unit
def test_as_dict_keeps_the_operator_facing_classification():
    """`reason` + `host_kind` are what replace the raw message: still actionable, still safe."""
    payload = StoreHealth(
        backend="postgres",
        ok=False,
        error=DRIVER_MESSAGE,
        error_id="deadbeef0000",
        reason="dns_unresolved",
        host_kind="supabase_direct",
    ).as_dict()

    assert payload["reason"] == "dns_unresolved"
    assert payload["host_kind"] == "supabase_direct"
    assert payload["error_id"] == "deadbeef0000"


@pytest.mark.unit
def test_as_dict_exposes_pending_documents_as_a_json_serializable_list():
    payload = StoreHealth(backend="postgres", pending_documents=("prediction_cache",)).as_dict()

    assert payload["pending_documents"] == ["prediction_cache"]
    assert isinstance(payload["pending_documents"], list)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("age", "expected"),
    [(None, None), (0.0, 0.0), (12.3456, 12.3), (12.35, 12.3), (99.99, 100.0)],
    ids=["never-checked", "zero", "rounded-down", "rounded", "rounded-up"],
)
def test_as_dict_rounds_the_check_age_and_preserves_never_checked(age, expected):
    payload = StoreHealth(backend="postgres", checked_seconds_ago=age).as_dict()

    assert payload["checked_seconds_ago"] == expected


@pytest.mark.unit
def test_as_log_dict_adds_the_raw_message_to_the_safe_view():
    health = StoreHealth(backend="postgres", ok=False, error=DRIVER_MESSAGE, reason="auth_failed")

    log_payload = health.as_log_dict()

    assert log_payload["error"] == DRIVER_MESSAGE
    # It is a strict superset: the safe fields are unchanged.
    assert log_payload.items() >= health.as_dict().items()
    assert set(log_payload) - set(health.as_dict()) == {"error"}


@pytest.mark.unit
def test_store_health_is_immutable():
    health = StoreHealth(backend="file")

    with pytest.raises(AttributeError):
        health.backend = "postgres"


@pytest.mark.unit
def test_pending_documents_default_is_not_shared_between_instances():
    """A mutable default would let one store's queue show up in another's health."""
    first = StoreHealth(backend="postgres")
    second = StoreHealth(backend="file")

    assert first.pending_documents == second.pending_documents == ()
    assert isinstance(first.pending_documents, tuple)


# ---------------------------------------------------------------------------
# DocumentStore protocol
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("method", ["read", "write", "health", "ping"])
def test_document_store_protocol_declares_the_full_backend_surface(method):
    """Pins the contract both backends must satisfy structurally, without inheriting it."""
    assert callable(getattr(DocumentStore, method))


@pytest.mark.unit
def test_ping_defaults_to_probing_rather_than_reusing_a_cached_result():
    """`max_age_seconds=0` means "never reuse", so a bare ping() always round-trips."""
    signature = inspect.signature(DocumentStore.ping)

    assert signature.parameters["max_age_seconds"].default == 0.0
