"""Durable cache for pre-race circuit strategy references.

A circuit strategy reference summarises one *completed* race edition — pit
loss, tyre windows, stint compounds — derived from that edition's lap
telemetry.  Producing one costs a full FastF1 session load (~10s on a laptop,
several times that on a small shared instance), and the answer never changes
once the edition is in the books.

Before this module those summaries lived in a process-local dict, so every
deploy, restart, or cold start on an ephemeral host paid the load again on the
first request that touched the command centre.  Persisting them through the
document store (Supabase in production, a JSON file locally) keeps them across
restarts, which is the whole point: the data is historical and immutable.

Entries record the edition they came from so a superseded reference can expire
without a schedule lookup — see ``SUPERSEDED_TTL_SECONDS``.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.data.store import DOCUMENT_CIRCUIT_REFERENCE, document_store
from app.data.store_types import WriteResult

logger = structlog.get_logger()

CACHE_SCHEMA_VERSION = 1

# A reference derived from the planning season's own edition cannot be
# superseded — no newer running of that circuit exists — so it never expires.
# Any other entry can be overtaken once this year's edition is run, and this
# bounds how long that goes unnoticed.  A circuit is raced once a season, so a
# week of lag costs nothing while still sparing every cold start the reload.
SUPERSEDED_TTL_SECONDS = 7 * 24 * 60 * 60

# "This circuit has no usable telemetry in any season we searched" is worth
# remembering too — the search that established it walks a decade of schedules.
# It is re-checked sooner than a positive result because a missing edition is
# more often a transient data outage than a permanent fact.
MISS_TTL_SECONDS = 24 * 60 * 60

# How long to wait before retrying a failed document read.  Without it, one
# failed read (a paused database, a network blip) would pin an empty cache for
# the whole process lifetime.
RELOAD_BACKOFF_SECONDS = 30.0


class CircuitReferenceCacheUnavailable(RuntimeError):
    """Raised when the store cannot be read, so writing would destroy entries.

    Persisting on top of a failed load would upload a document holding only
    what this process happens to have computed, silently dropping every
    reference it failed to read.
    """


@dataclass(frozen=True)
class CachedReference:
    """A cache hit.  ``reference`` is ``None`` for a remembered miss."""

    reference: dict | None
    source_year: int | None
    stored_at: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class CircuitReferenceCache:
    """Circuit references keyed by planning city and season, held durably."""

    def __init__(self) -> None:
        self._loaded = False
        self._entries: dict[str, dict[str, Any]] = {}
        self._next_load_attempt = 0.0
        self._lock = threading.RLock()

    # -- reads --------------------------------------------------------------
    def get(self, city: str, year: int) -> CachedReference | None:
        """Return the cached reference, or ``None`` when there is no live entry.

        A hit whose ``reference`` is ``None`` is a remembered miss — the caller
        should honour it rather than repeat the search.
        """
        if not self._ensure_loaded():
            return None

        key = self._key(city, year)
        with self._lock:
            entry = self._entries.get(key)

        if not isinstance(entry, dict):
            return None
        if self._is_expired(entry, year, _utc_now()):
            logger.info("circuit_reference_cache.expired", city=city, year=year)
            return None

        reference = entry.get("reference")
        logger.info(
            "circuit_reference_cache.hit",
            city=city,
            year=year,
            source_year=entry.get("source_year"),
            remembered_miss=reference is None,
        )
        return CachedReference(
            reference=copy.deepcopy(reference) if isinstance(reference, dict) else None,
            source_year=entry.get("source_year"),
            stored_at=entry.get("stored_at"),
        )

    def _is_expired(self, entry: dict[str, Any], year: int, now: datetime) -> bool:
        reference = entry.get("reference")
        source_year = entry.get("source_year")
        if isinstance(reference, dict) and source_year == year:
            # Sourced from the planning season itself — nothing can supersede it.
            return False

        stored_at = _parse_iso(entry.get("stored_at"))
        if stored_at is None:
            # Undatable entry: treat as expired rather than trust it forever.
            return True

        ttl = MISS_TTL_SECONDS if reference is None else SUPERSEDED_TTL_SECONDS
        return now - stored_at > timedelta(seconds=ttl)

    # -- writes -------------------------------------------------------------
    def set(self, city: str, year: int, reference: dict | None) -> WriteResult:
        """Store a reference (or a remembered miss) for this city and season."""
        if not self._ensure_loaded():
            raise CircuitReferenceCacheUnavailable(
                "Circuit reference store is unreachable; refusing to overwrite "
                "stored references with an incomplete set. Try again shortly."
            )

        entry = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "stored_at": _iso(_utc_now()),
            "source_year": (reference or {}).get("source_year"),
            "reference": copy.deepcopy(reference) if isinstance(reference, dict) else None,
        }

        with self._lock:
            self._entries = {**self._entries, self._key(city, year): entry}
            write = self._save()

        logger.info(
            "circuit_reference_cache.stored",
            city=city,
            year=year,
            source_year=entry["source_year"],
            durable=write.durable,
        )
        return write

    # -- persistence --------------------------------------------------------
    def load(self) -> bool:
        """Read the document from the store.  Returns whether it succeeded.

        A failure leaves the cache unloaded so a later call retries; it is
        never recorded as "loaded and empty".
        """
        with self._lock:
            self._next_load_attempt = time.monotonic() + RELOAD_BACKOFF_SECONDS
            read = document_store.read(DOCUMENT_CIRCUIT_REFERENCE)

            if not read.ok:
                logger.error("circuit_reference_cache.load_failed", error=read.error)
                return False

            payload = read.payload
            if payload is None:
                self._entries = {}
                self._loaded = True
                return True

            if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
                logger.warning(
                    "circuit_reference_cache.unsupported_schema",
                    schema_version=payload.get("schema_version"),
                )
                self._entries = {}
                self._loaded = True
                return True

            self._entries = {
                str(key): value
                for key, value in (payload.get("entries") or {}).items()
                if isinstance(value, dict)
            }
            self._loaded = True
            logger.info("circuit_reference_cache.loaded", entries=len(self._entries))
            return True

    def _ensure_loaded(self) -> bool:
        """Load on first use, retrying a previous failure after a backoff."""
        with self._lock:
            if self._loaded:
                return True
            if time.monotonic() < self._next_load_attempt:
                return False
            return self.load()

    def _save(self) -> WriteResult:
        return document_store.write(
            DOCUMENT_CIRCUIT_REFERENCE,
            {"schema_version": CACHE_SCHEMA_VERSION, "entries": self._entries},
        )

    @staticmethod
    def _key(city: str, year: int) -> str:
        return f"{city.strip().lower()}:{year}"


circuit_reference_cache = CircuitReferenceCache()
