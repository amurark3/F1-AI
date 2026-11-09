"""Tests for the durable circuit strategy reference cache.

The behaviour under test: a reference derived from a completed race edition
survives a process restart (it used to live in a module-level dict, so every
cold start reloaded the telemetry behind it), a superseded reference expires,
and a store outage is never mistaken for an empty cache — writing on top of
one would drop every reference this process failed to read.

The document is held in memory, so a write applies to the latest stored
document rather than to that copy: a reference another process stored since is
kept, and for the same circuit the newer ``stored_at`` wins. The held copy is
read again once ``REFRESH_SECONDS`` have passed, so another process's references
are served without a restart.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.data import circuit_reference_cache as cache_module
from app.data.circuit_reference_cache import (
    CACHE_SCHEMA_VERSION,
    MISS_TTL_SECONDS,
    SUPERSEDED_TTL_SECONDS,
    CircuitReferenceCache,
    CircuitReferenceCacheUnavailableError,
)
from app.data.store import DOCUMENT_CIRCUIT_REFERENCE, PostgresDocumentStore
from app.data.store_types import ReadResult, UpdateResult
from tests.document_table_support import DocumentTable, install_document_table

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

    def update(self, name, change):
        self.payload = change(self.payload)
        self.writes.append(self.payload)
        return UpdateResult(ok=True, durable=self.durable, payload=self.payload)


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
    at(datetime(2026, 1, 1, tzinfo=UTC))
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, {**REFERENCE, "source_year": YEAR})

    # No newer edition of this circuit can exist, so age is irrelevant.
    at(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=SUPERSEDED_TTL_SECONDS * 10))

    hit = cache.get(CITY, YEAR)
    assert hit is not None
    assert hit.source_year == YEAR


def test_reference_from_an_earlier_season_expires_once_it_can_be_superseded(store, at):
    stored_at = datetime(2026, 1, 1, tzinfo=UTC)
    at(stored_at)
    cache = CircuitReferenceCache()
    cache.set(CITY, YEAR, REFERENCE)

    at(stored_at + timedelta(seconds=SUPERSEDED_TTL_SECONDS - 60))
    assert cache.get(CITY, YEAR) is not None

    at(stored_at + timedelta(seconds=SUPERSEDED_TTL_SECONDS + 60))
    assert cache.get(CITY, YEAR) is None


def test_remembered_miss_is_rechecked_sooner_than_a_reference(store, at):
    stored_at = datetime(2026, 1, 1, tzinfo=UTC)
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

    with pytest.raises(CircuitReferenceCacheUnavailableError):
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
                "stored_at": datetime.now(UTC).isoformat(),
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


def test_an_entry_with_an_unreadable_timestamp_is_treated_as_expired(store):
    """An undatable entry cannot prove it is fresh, so it is not trusted forever."""
    store.payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "entries": {
            f"{CITY.lower()}:{YEAR}": {"reference": REFERENCE, "source_year": 2025, "stored_at": "last tuesday"},
        },
    }

    assert CircuitReferenceCache().get(CITY, YEAR) is None


# ---------------------------------------------------------------------------
# Two processes sharing one stored document
# ---------------------------------------------------------------------------

MONZA = {**REFERENCE, "median_first_stop": 21, "pit_loss_seconds": 24.0}


@pytest.fixture
def table(monkeypatch, tmp_path) -> DocumentTable:
    """One fake ``app_documents`` table behind the real Postgres store."""
    shared = install_document_table(monkeypatch, tmp_path)
    monkeypatch.setattr(cache_module, "document_store", PostgresDocumentStore("postgresql://u:p@postgres:5432/f1ai"))
    return shared


def _stored(table: DocumentTable) -> dict:
    return table.payload(DOCUMENT_CIRCUIT_REFERENCE)["entries"]


def test_a_reference_another_process_stored_after_this_one_read_is_kept(table):
    running = CircuitReferenceCache()
    assert running.get(CITY, YEAR) is None  # this process reads the document now

    CircuitReferenceCache().set("Monza", YEAR, MONZA)  # another process
    running.set(CITY, YEAR, REFERENCE)

    assert set(_stored(table)) == {"zandvoort:2026", "monza:2026"}
    hit = running.get("Monza", YEAR)
    assert hit is not None, "the running process now serves it too"
    assert hit.reference == MONZA


def test_a_reference_stored_between_the_read_and_the_write_is_kept(table):
    running = CircuitReferenceCache()
    running.get(CITY, YEAR)
    table.before_next_write(lambda: CircuitReferenceCache().set("Monza", YEAR, MONZA))

    running.set(CITY, YEAR, REFERENCE)

    assert set(_stored(table)) == {"zandvoort:2026", "monza:2026"}


def test_for_the_same_circuit_the_newer_reference_wins_over_a_later_write(table, at):
    """The other process minted its entry after this one did, so its entry is the newer one."""
    minted = datetime(2026, 1, 1, tzinfo=UTC)
    at(minted)
    running = CircuitReferenceCache()
    running.get(CITY, YEAR)

    def other_process_stores_a_newer_one() -> None:
        at(minted + timedelta(hours=1))
        CircuitReferenceCache().set(CITY, YEAR, MONZA)

    table.before_next_write(other_process_stores_a_newer_one)
    running.set(CITY, YEAR, REFERENCE)

    assert _stored(table)["zandvoort:2026"]["reference"] == MONZA
    hit = running.get(CITY, YEAR)
    assert hit is not None
    assert hit.reference == MONZA


def test_for_the_same_circuit_this_process_wins_with_the_newer_entry(table, at):
    minted = datetime(2026, 1, 1, tzinfo=UTC)
    at(minted)
    running = CircuitReferenceCache()
    running.get(CITY, YEAR)
    CircuitReferenceCache().set(CITY, YEAR, MONZA)

    at(minted + timedelta(hours=1))
    running.set(CITY, YEAR, REFERENCE)

    assert _stored(table)["zandvoort:2026"]["reference"] == REFERENCE


def test_an_undated_stored_entry_loses_to_a_dated_one(table):
    table.put(
        DOCUMENT_CIRCUIT_REFERENCE,
        {"schema_version": CACHE_SCHEMA_VERSION, "entries": {"zandvoort:2026": {"reference": MONZA}}},
    )

    CircuitReferenceCache().set(CITY, YEAR, REFERENCE)

    assert _stored(table)["zandvoort:2026"]["reference"] == REFERENCE


def test_a_reference_another_process_stored_is_served_after_the_refresh_interval(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])
    running = CircuitReferenceCache()
    assert running.get(CITY, YEAR) is None

    CircuitReferenceCache().set(CITY, YEAR, REFERENCE)  # another process
    assert running.get(CITY, YEAR) is None, "inside the interval the held copy is served"

    clock[0] += cache_module.REFRESH_SECONDS
    hit = running.get(CITY, YEAR)
    assert hit is not None
    assert hit.reference == REFERENCE


def test_a_failed_refresh_keeps_serving_the_held_references(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])
    running = CircuitReferenceCache()
    running.set(CITY, YEAR, REFERENCE)

    store.readable = False
    clock[0] += cache_module.REFRESH_SECONDS

    assert running.get(CITY, YEAR) is not None
