"""Tests for the durable circuit strategy reference cache.

The behaviour under test: a reference derived from a completed race edition
survives a process restart (it used to live in a module-level dict, so every
cold start reloaded the telemetry behind it), a superseded reference expires,
and a store outage is never mistaken for an empty cache — writing on top of
one would drop every reference this process failed to read.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.data import circuit_reference_cache as cache_module
from app.data.circuit_reference_cache import (
    CACHE_SCHEMA_VERSION,
    MISS_TTL_SECONDS,
    SUPERSEDED_TTL_SECONDS,
    CircuitReferenceCache,
    CircuitReferenceCacheUnavailable,
)
from app.data.store_types import ReadResult, WriteResult

pytestmark = pytest.mark.unit

CITY = "Zandvoort"
YEAR = 2026

REFERENCE = {
    "source_year": 2025,
    "sample_size": 20,
    "median_first_stop": 27,
    "pit_loss_seconds": 21.4,
    "opening_compound": "Medium",
    "finishing_compound": "Hard",
}


class FakeStore:
    """In-memory document store that can be told to fail."""

    def __init__(self, payload=None, readable=True, durable=True):
        self.payload = payload
        self.readable = readable
        self.durable = durable
        self.writes = []

    def read(self, name):
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append(payload)
        self.payload = payload
        return WriteResult(ok=True, durable=self.durable)


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(cache_module, "document_store", fake)
    return fake


@pytest.fixture
def at(monkeypatch):
    """Freeze the clock the cache reads."""

    def _at(moment: datetime):
        monkeypatch.setattr(cache_module, "_utc_now", lambda: moment)

    return _at


def test_stored_reference_is_returned_on_a_later_lookup(store):
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, REFERENCE)

    hit = cache.get(CITY, YEAR)

    assert hit is not None
    assert hit.reference == REFERENCE
    assert hit.source_year == 2025


def test_reference_survives_a_process_restart(store):
    CircuitReferenceCache().set(CITY, YEAR, REFERENCE)

    # A brand-new cache object stands in for the next container: it shares
    # nothing but the document store.
    restarted = CircuitReferenceCache()

    hit = restarted.get(CITY, YEAR)
    assert hit is not None
    assert hit.reference == REFERENCE


def test_lookup_is_case_and_whitespace_insensitive(store):
    cache = CircuitReferenceCache()
    cache.set("  Zandvoort  ", YEAR, REFERENCE)

    assert cache.get("zandvoort", YEAR) is not None


def test_unknown_circuit_is_a_miss(store):
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, REFERENCE)

    assert cache.get("Monza", YEAR) is None
    assert cache.get(CITY, YEAR + 1) is None


def test_remembered_miss_is_a_hit_carrying_no_reference(store):
    """A circuit with no usable edition must not be re-searched every request."""
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, None)

    hit = cache.get(CITY, YEAR)

    assert hit is not None
    assert hit.reference is None


def test_reference_from_the_planning_season_never_expires(store, at):
    at(datetime(2026, 1, 1, tzinfo=timezone.utc))
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, {**REFERENCE, "source_year": YEAR})

    # No newer edition of this circuit can exist, so age is irrelevant.
    at(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=SUPERSEDED_TTL_SECONDS * 10))

    hit = cache.get(CITY, YEAR)
    assert hit is not None
    assert hit.source_year == YEAR


def test_reference_from_an_earlier_season_expires_once_it_can_be_superseded(store, at):
    stored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    at(stored_at)
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, REFERENCE)

    at(stored_at + timedelta(seconds=SUPERSEDED_TTL_SECONDS - 60))
    assert cache.get(CITY, YEAR) is not None

    at(stored_at + timedelta(seconds=SUPERSEDED_TTL_SECONDS + 60))
    assert cache.get(CITY, YEAR) is None


def test_remembered_miss_is_rechecked_sooner_than_a_reference(store, at):
    stored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    at(stored_at)
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, None)

    at(stored_at + timedelta(seconds=MISS_TTL_SECONDS + 60))
    assert cache.get(CITY, YEAR) is None


def test_entry_without_a_timestamp_is_not_trusted(store):
    store.payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "entries": {f"{CITY.lower()}:{YEAR}": {"reference": REFERENCE, "source_year": 2025}},
    }

    assert CircuitReferenceCache().get(CITY, YEAR) is None


def test_unreadable_store_reports_a_miss_rather_than_an_empty_cache(store):
    store.readable = False

    assert CircuitReferenceCache().get(CITY, YEAR) is None


def test_write_is_refused_while_the_store_cannot_be_read(store):
    """Persisting on top of a failed load would drop every unread reference."""
    store.readable = False
    cache = CircuitReferenceCache()

    with pytest.raises(CircuitReferenceCacheUnavailable):
        cache.set(CITY, YEAR, REFERENCE)

    assert store.writes == []


def test_a_failed_load_is_retried_after_the_backoff(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])

    store.readable = False
    cache = CircuitReferenceCache()
    assert cache.get(CITY, YEAR) is None

    # Still inside the backoff window: the store is healthy again but not retried.
    store.readable = True
    store.payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "entries": {
            f"{CITY.lower()}:{YEAR}": {
                "reference": REFERENCE,
                "source_year": 2025,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    }
    assert cache.get(CITY, YEAR) is None

    clock[0] += cache_module.RELOAD_BACKOFF_SECONDS + 1
    assert cache.get(CITY, YEAR) is not None


def test_document_from_an_unsupported_schema_is_ignored(store):
    store.payload = {"schema_version": CACHE_SCHEMA_VERSION + 99, "entries": {"zandvoort:2026": {}}}

    assert CircuitReferenceCache().get(CITY, YEAR) is None


def test_malformed_entries_are_skipped_on_load(store):
    store.payload = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {"zandvoort:2026": "not-a-dict"}}

    assert CircuitReferenceCache().get(CITY, YEAR) is None


def test_stored_reference_is_copied_so_callers_cannot_corrupt_the_cache(store):
    cache = CircuitReferenceCache()
    source = dict(REFERENCE)
    cache.set(CITY, YEAR, source)

    source["pit_loss_seconds"] = 999
    first = cache.get(CITY, YEAR)
    assert first is not None
    first.reference["pit_loss_seconds"] = 111

    hit = cache.get(CITY, YEAR)
    assert hit is not None
    assert hit.reference["pit_loss_seconds"] == REFERENCE["pit_loss_seconds"]


def test_a_non_durable_write_is_reported_not_hidden(store):
    store.durable = False
    cache = CircuitReferenceCache()

    write = cache.set(CITY, YEAR, REFERENCE)

    assert write.durable is False
    # The reference is still usable in this process.
    assert cache.get(CITY, YEAR) is not None
