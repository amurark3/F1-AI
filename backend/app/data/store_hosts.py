"""What kind of database host the store is configured for, and why it failed.

Both answers are client-safe: ``/api/ready`` and ``/api/health/deep`` are
unauthenticated, so they report a *shape* of host and a *reason* code rather
than the driver message, which names the host, port and user.
"""

from __future__ import annotations

from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

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
        host = (urlparse(dsn).hostname or "").lower()
    except ValueError:
        return HOST_OTHER

    if host.endswith(".pooler.supabase.com"):
        return HOST_SUPABASE_POOLER
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return HOST_SUPABASE_DIRECT
    return HOST_OTHER


def warn_if_ipv6_only_host(dsn: str) -> None:
    """Flag Supabase's direct endpoint, which many hosts cannot reach.

    ``db.<ref>.supabase.co`` publishes no A record. Platforms with IPv4-only
    egress — Render and GitHub Actions runners included — therefore fail every
    connection, and because this store degrades onto a local file the symptom is
    not an error but data that quietly disappears at the next cold start. Saying
    so at startup costs one log line and turns a silent outage into a signpost.
    """
    host = ""
    try:
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
