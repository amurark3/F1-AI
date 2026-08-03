"""Client-safe error payloads for HTTP handlers.

Raw exception text must never reach an HTTP client. Exceptions raised inside
these handlers originate from fastf1, the f1db SQLite reader and the
Postgres/pgvector store, and their string forms routinely carry database
hosts and ports, SQL table and column identifiers, and absolute server paths.
That is free reconnaissance for an attacker and it is worth nothing to a
legitimate caller. CodeQL flags the pattern as ``py/stack-trace-exposure``.

Handlers therefore log the exception with full detail and return
:data:`GENERIC_ERROR_MESSAGE` plus a short correlation id. The id is the only
thing shared across the boundary: a user can quote it in a bug report and it
can be grepped straight out of the structured logs.

Usage — spread the payload into whatever shape the endpoint already returns,
so existing clients keep seeing the keys they expect::

    except Exception as exc:
        return {"year": year, "teams": [], **client_error("api.teams.error", exc, year=year)}
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger()

GENERIC_ERROR_MESSAGE = "Something went wrong loading this data. Try again shortly."

# Length of the correlation id shown to clients. Full uuid4 hex is noisy in a
# UI toast; 12 hex chars is ample to disambiguate within a log retention window.
ERROR_ID_LENGTH = 12


def new_error_id() -> str:
    """Return a short, random correlation id for one error occurrence."""
    return uuid.uuid4().hex[:ERROR_ID_LENGTH]


def client_error(event: str, exc: BaseException, **context: Any) -> dict[str, str]:
    """Log ``exc`` under ``event`` and build the client-safe error payload.

    ``context`` is added to the log entry only — never to the response — so
    handlers can record the year, round or driver that triggered the failure.
    """
    error_id = new_error_id()
    logger.error(
        event,
        error_id=error_id,
        error=str(exc),
        error_type=type(exc).__name__,
        exc_info=exc,
        **context,
    )
    return {"error": GENERIC_ERROR_MESSAGE, "error_id": error_id}


def client_error_text(event: str, exc: BaseException, **context: Any) -> str:
    """Same contract as :func:`client_error` for plain-text/streaming responses."""
    payload = client_error(event, exc, **context)
    return f"{payload['error']} (reference: {payload['error_id']})"
