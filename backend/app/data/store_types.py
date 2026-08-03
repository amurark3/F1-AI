"""Result types for the document store.

The store used to return a bare ``dict | None`` from ``read``, which made
"there is no such document" and "the backend is unreachable" indistinguishable.
That ambiguity caused a production outage: while the Postgres project was
paused every read failed, callers read the failure as "no data yet", and the app
served empty predictions with no error anywhere in the response.

These types make the distinction explicit, so a caller can hold its existing
state and retry instead of treating an outage as an empty database — and, just
as importantly, refuse to write a truncated document built on top of a failed
read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ReadResult:
    """Outcome of a document read.

    ``ok`` means the backend answered. ``payload`` is then the document, or
    ``None`` when the document genuinely does not exist yet. When ``ok`` is
    false the payload carries no information at all — the backend failed, and
    the absence of data must not be mistaken for an empty document.
    """

    payload: dict | None = None
    ok: bool = True
    error: str | None = None

    @property
    def missing(self) -> bool:
        """True when the backend answered and holds no such document."""
        return self.ok and self.payload is None


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a document write.

    ``durable`` is the one that matters operationally: it is true only when the
    bytes reached the backend the deployment actually relies on. A write that
    lands on an ephemeral container disk is not durable, and saying so is the
    difference between a visible failure and silent data loss.
    """

    ok: bool = True
    durable: bool = True
    error: str | None = None


@dataclass(frozen=True)
class StoreHealth:
    """What the store knows about its own backend.

    ``ok`` is ``None`` before any operation has been attempted — unknown is a
    distinct state from healthy, and reporting it as healthy would hide exactly
    the failure this type exists to surface.

    ``error`` holds the raw driver message, which for a connection failure names
    the database host and port. It is for logs only; ``error_id`` correlates a
    client response to the log entry carrying that detail.
    """

    backend: str
    ok: bool | None = None
    error: str | None = None
    error_id: str | None = None
    pending_documents: tuple[str, ...] = field(default_factory=tuple)
    checked_seconds_ago: float | None = None

    def as_dict(self) -> dict:
        """Client-safe view. Never includes the raw driver message.

        Health endpoints are unauthenticated, so this is the default rather than
        an opt-in: a handler that reaches for the obvious method gets the safe
        one. Use :meth:`as_log_dict` for the full detail.
        """
        return {
            "backend": self.backend,
            "ok": self.ok,
            "error_id": self.error_id,
            "pending_documents": list(self.pending_documents),
            "checked_seconds_ago": (
                round(self.checked_seconds_ago, 1)
                if self.checked_seconds_ago is not None
                else None
            ),
        }

    def as_log_dict(self) -> dict:
        """Full detail for server-side logging. Never return this to a client."""
        return {**self.as_dict(), "error": self.error}


class DocumentStore(Protocol):
    """A named-document key/value store of JSON-compatible dicts."""

    def read(self, name: str) -> ReadResult: ...

    def write(self, name: str, payload: dict) -> WriteResult: ...

    def health(self) -> StoreHealth: ...

    def ping(self, max_age_seconds: float = 0.0) -> StoreHealth: ...
