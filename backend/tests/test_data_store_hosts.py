"""Tests for app.data.store_hosts — the client-safe host and failure labels.

``/api/ready`` and ``/api/health/deep`` are unauthenticated, so the store
reports *what shape* of host it was given and *why* a connection failed as
codes, never the driver message (which names the host, port and user). Each
code has to point an operator at a distinct fix.
"""

from __future__ import annotations

import pytest

from app.data.store_hosts import (
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
    classify_failure,
    classify_host,
    warn_if_ipv6_only_host,
)

POOLER_DSN = "postgresql://postgres.abcdefgh:pw@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"
DIRECT_DSN = "postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres"


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
# Startup: the IPv6-only host warning
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_direct_supabase_host_is_flagged_at_startup(capsys):
    """IPv6-only endpoint + IPv4-only host = every write silently landing on scratch disk."""
    warn_if_ipv6_only_host(DIRECT_DSN)

    logged = capsys.readouterr().out
    assert "store.direct_supabase_host_configured" in logged
    # The session pooler on 5432, not the transaction pooler on 6543, is the fix.
    assert "aws-<n>-<region>.pooler.supabase.com:5432" in logged, "the warning must name the fix"


@pytest.mark.unit
@pytest.mark.parametrize(
    "dsn",
    [POOLER_DSN, "postgresql://u:p@localhost:5432/postgres", "postgresql://u:p@[::1/postgres", ""],
    ids=["pooler", "localhost", "unparseable", "empty"],
)
def test_no_ipv6_warning_for_other_hosts(capsys, dsn):
    warn_if_ipv6_only_host(dsn)

    assert "store.direct_supabase_host_configured" not in capsys.readouterr().out
