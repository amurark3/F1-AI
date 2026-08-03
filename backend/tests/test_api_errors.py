"""Tests for the client-safe error boundary (app.api.errors).

The security property under test: no attribute of the original exception may
appear in the payload handed to an HTTP client.
"""

import re

import pytest

from app.api.errors import (
    ERROR_ID_LENGTH,
    GENERIC_ERROR_MESSAGE,
    client_error,
    client_error_text,
    new_error_id,
)

# Stand-ins for the exception text this codebase actually produces: a psycopg
# connection failure, a SQLite schema error and a filesystem path.
LEAKY_EXCEPTIONS = [
    ConnectionError(
        'connection to server at "db.abcdefgh.supabase.co" (11.22.33.44), '
        "port 5432 failed: FATAL: password authentication failed for user "
        '"postgres"'
    ),
    ValueError('no such column: driver.race_points in "SELECT * FROM driver"'),
    FileNotFoundError("/opt/render/project/src/backend/f1_cache/2026/qual.ff1"),
]

SECRET_FRAGMENTS = [
    "supabase.co",
    "5432",
    "password",
    "postgres",
    "no such column",
    "SELECT",
    "/opt/render",
]


@pytest.mark.unit
@pytest.mark.parametrize("exc", LEAKY_EXCEPTIONS, ids=["postgres", "sql", "path"])
def test_client_error_never_echoes_exception_text(exc):
    payload = client_error("test.event", exc)
    serialized = repr(payload)

    assert payload["error"] == GENERIC_ERROR_MESSAGE
    assert str(exc) not in serialized
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in serialized


@pytest.mark.unit
@pytest.mark.parametrize("exc", LEAKY_EXCEPTIONS, ids=["postgres", "sql", "path"])
def test_client_error_text_never_echoes_exception_text(exc):
    message = client_error_text("test.event", exc)

    assert GENERIC_ERROR_MESSAGE in message
    assert str(exc) not in message
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in message


@pytest.mark.unit
def test_payload_has_only_error_and_correlation_id():
    payload = client_error("test.event", ValueError("boom"), year=2026, round=3)

    # Log-only context must not widen the response.
    assert set(payload) == {"error", "error_id"}


@pytest.mark.unit
def test_error_id_is_random_and_well_formed():
    ids = {new_error_id() for _ in range(200)}

    assert len(ids) == 200, "correlation ids must not collide"
    assert all(re.fullmatch(rf"[0-9a-f]{{{ERROR_ID_LENGTH}}}", i) for i in ids)


@pytest.mark.unit
def test_correlation_id_links_response_to_log(capsys):
    exc = LEAKY_EXCEPTIONS[0]

    payload = client_error("test.linked", exc, year=2026)

    # structlog is configured with its own stdout writer rather than the
    # stdlib logging bridge, so the log lands in captured stdout, not caplog.
    logged = capsys.readouterr().out

    # The full detail must survive server-side, keyed by the id the client got.
    assert payload["error_id"] in logged
    assert "db.abcdefgh.supabase.co" in logged
    assert "test.linked" in logged
    assert "year=2026" in logged
