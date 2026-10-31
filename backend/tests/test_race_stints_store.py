"""Tests for app.data.race_stints_store: resolved stints kept across restarts.

The store exists because both stint sources can be out of reach when someone
asks: OpenF1 refuses unauthenticated clients for the whole of every live
session, and FastF1 has no lap data on Render's always-cold cache. The risks:

* **A write after a failed read destroys data.** It would upload a document
  holding only this process's races. Writes are refused until a read succeeds.
* **A document from an older schema is not trusted.** Stint semantics have
  changed before (FastF1's tyre age was one lap high), and a stale document must
  not resurrect them.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
import structlog

from app.data import race_stints_store as module
from app.data.race_stints_store import RaceStintsStore
from app.data.stint_model import Stint
from app.data.store_types import ReadResult, WriteResult

STINT = Stint(
    driver_code="LEC",
    team="Ferrari",
    stint=1,
    compound="MEDIUM",
    start_lap=1,
    end_lap=20,
    laps=20,
    tyre_life_start=0,
    fresh=True,
    ended_under_red_flag=False,
)


class FakeStore:
    """In-memory document store that can be told to fail."""

    def __init__(self, payload=None, readable=True, writable=True):
        self.payload = payload
        self.readable = readable
        self.writable = writable
        self.reads = 0
        self.writes: list[dict] = []

    def read(self, name):
        self.reads += 1
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload=self.payload)

    def write(self, name, payload):
        self.writes.append(payload)
        if not self.writable:
            return WriteResult(ok=False, durable=False, error="read-only")
        self.payload = payload
        return WriteResult()


@pytest.fixture
def store(monkeypatch):
    def install(**kwargs) -> FakeStore:
        fake = FakeStore(**kwargs)
        monkeypatch.setattr(module, "document_store", fake)
        return fake

    return install


def _document(races: dict, version: int = module.SCHEMA_VERSION) -> dict:
    return {"version": version, "races": races}


@pytest.mark.unit
def test_a_stored_race_round_trips(store):
    fake = store(payload=None)

    RaceStintsStore().put(2026, 13, (STINT,))

    assert fake.writes == [_document({"2026-13": [asdict(STINT)]})]
    assert RaceStintsStore().get(2026, 13) == (STINT,), "a fresh process reads it back"


@pytest.mark.unit
def test_a_new_race_is_added_beside_the_ones_already_stored(store):
    fake = store(payload=_document({"2026-12": [asdict(STINT)]}))

    RaceStintsStore().put(2026, 13, (STINT,))

    assert set(fake.payload["races"]) == {"2026-12", "2026-13"}


@pytest.mark.unit
def test_an_unknown_race_is_a_miss(store):
    store(payload=_document({"2026-12": [asdict(STINT)]}))

    assert RaceStintsStore().get(2026, 13) is None


@pytest.mark.unit
def test_the_document_is_read_once_per_process(store):
    fake = store(payload=_document({"2026-13": [asdict(STINT)]}))
    cache = RaceStintsStore()

    cache.get(2026, 13)
    cache.get(2026, 12)

    assert fake.reads == 1


@pytest.mark.unit
def test_a_document_from_another_schema_version_is_ignored(store):
    fake = store(payload=_document({"2026-13": [asdict(STINT)]}, version=0))
    cache = RaceStintsStore()

    assert cache.get(2026, 13) is None
    cache.put(2026, 12, (STINT,))
    assert fake.payload == _document({"2026-12": [asdict(STINT)]})


@pytest.mark.unit
def test_a_row_of_the_wrong_shape_is_a_miss_not_a_crash(store):
    store(payload=_document({"2026-13": [{"driver_code": "LEC"}]}))

    with structlog.testing.capture_logs() as logs:
        assert RaceStintsStore().get(2026, 13) is None

    assert [entry["event"] for entry in logs] == ["race_stints_store.bad_row"]


@pytest.mark.unit
def test_an_empty_answer_is_never_stored(store):
    fake = store(payload=None)

    RaceStintsStore().put(2026, 13, ())

    assert fake.writes == []
    assert fake.reads == 0


@pytest.mark.unit
def test_nothing_is_written_after_a_failed_read(store):
    fake = store(readable=False)
    cache = RaceStintsStore()

    assert cache.get(2026, 13) is None
    cache.put(2026, 13, (STINT,))

    assert fake.writes == [], "writing now would upload only this race and drop every other"


@pytest.mark.unit
def test_a_failed_read_is_retried_after_a_backoff(store, monkeypatch):
    clock = iter([100.0, 110.0, 200.0])
    monkeypatch.setattr(module, "_clock", lambda: next(clock))
    fake = store(readable=False)
    cache = RaceStintsStore()

    cache.get(2026, 13)  # reads, fails, backs off until 130
    cache.get(2026, 13)  # 110: still backing off, no read
    fake.readable = True
    fake.payload = _document({"2026-13": [asdict(STINT)]})

    assert cache.get(2026, 13) == (STINT,)  # 200: tries again
    assert fake.reads == 2


@pytest.mark.unit
def test_a_failed_write_is_logged_and_kept_in_memory(store):
    fake = store(payload=None, writable=False)
    cache = RaceStintsStore()

    with structlog.testing.capture_logs() as logs:
        cache.put(2026, 13, (STINT,))

    assert [entry["event"] for entry in logs] == ["race_stints_store.write_failed"]
    assert cache.get(2026, 13) == (STINT,)
    assert fake.reads == 1
