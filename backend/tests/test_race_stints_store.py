"""Tests for app.data.race_stints_store: resolved stints kept across restarts.

The store exists because both stint sources can be out of reach when someone
asks: OpenF1 refuses unauthenticated clients for the whole of every live
session, and FastF1 has no lap data on Render's always-cold cache. The risks:

* **A write after a failed read destroys data.** It would upload a document
  holding only this process's races. Writes are refused until a read succeeds.
* **A document from an older schema is not trusted.** Stint semantics have
  changed before (FastF1's tyre age was one lap high), and a stale document must
  not resurrect them.
* **Another process's races survive this one's writes.** The document is held
  in memory, so a write must apply to the latest stored document, not to that
  copy: a race another process stored since is kept beside this one's.
* **Another process's races are served without a restart.** The held copy is
  read again once ``REFRESH_SECONDS`` have passed; a failed re-read keeps
  serving it.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
import structlog

from app.data import race_stints_store as module
from app.data.race_stints_store import RaceStintsStore
from app.data.stint_model import Stint
from app.data.store import DOCUMENT_RACE_STINTS, PostgresDocumentStore
from app.data.store_types import ReadResult, UpdateResult
from tests.document_table_support import DocumentTable, install_document_table

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
OTHER = Stint(**{**asdict(STINT), "driver_code": "HAM", "compound": "HARD"})


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

    def update(self, name, change):
        if not self.writable:
            return UpdateResult(ok=False, durable=False, error="read-only")
        self.payload = change(self.payload)
        self.writes.append(self.payload)
        return UpdateResult(payload=self.payload)


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
def test_the_document_is_not_read_again_within_the_refresh_interval(store):
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
def test_a_dropped_race_is_gone_and_the_others_are_kept(store):
    fake = store(payload=_document({"2026-12": [asdict(STINT)], "2026-19": [asdict(STINT)]}))
    cache = RaceStintsStore()

    cache.drop(2026, 19)

    assert fake.payload == _document({"2026-12": [asdict(STINT)]})
    assert cache.get(2026, 19) is None
    assert RaceStintsStore().get(2026, 19) is None, "a fresh process does not read it back"


@pytest.mark.unit
def test_dropping_a_race_that_is_not_stored_writes_nothing(store):
    fake = store(payload=_document({"2026-12": [asdict(STINT)]}))

    RaceStintsStore().drop(2026, 19)

    assert fake.writes == []


@pytest.mark.unit
def test_nothing_is_dropped_after_a_failed_read(store):
    fake = store(readable=False)

    RaceStintsStore().drop(2026, 19)

    assert fake.writes == [], "writing now would upload an empty document over every race"


@pytest.mark.unit
def test_a_failed_drop_is_logged_and_kept_in_memory(store):
    store(payload=_document({"2026-19": [asdict(STINT)]}), writable=False)
    cache = RaceStintsStore()

    with structlog.testing.capture_logs() as logs:
        cache.drop(2026, 19)

    assert [entry["event"] for entry in logs] == ["race_stints_store.dropped", "race_stints_store.write_failed"]
    assert cache.get(2026, 19) is None


@pytest.mark.unit
def test_a_failed_write_is_logged_and_kept_in_memory(store):
    fake = store(payload=None, writable=False)
    cache = RaceStintsStore()

    with structlog.testing.capture_logs() as logs:
        cache.put(2026, 13, (STINT,))

    assert [entry["event"] for entry in logs] == ["race_stints_store.write_failed"]
    assert cache.get(2026, 13) == (STINT,)
    assert fake.reads == 1


# ---------------------------------------------------------------------------
# Two processes sharing one stored document
# ---------------------------------------------------------------------------


@pytest.fixture
def table(monkeypatch, tmp_path) -> DocumentTable:
    """One fake ``app_documents`` table behind the real Postgres store."""
    shared = install_document_table(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "document_store", PostgresDocumentStore("postgresql://u:p@postgres:5432/f1ai"))
    return shared


def _stored_races(table: DocumentTable) -> dict:
    return table.payload(DOCUMENT_RACE_STINTS)["races"]


@pytest.mark.unit
def test_a_race_another_process_stored_after_this_one_read_is_kept(table):
    running = RaceStintsStore()
    assert running.get(2026, 12) is None  # this process reads the document now

    RaceStintsStore().put(2026, 12, (STINT,))  # another process, e.g. a job container
    running.put(2026, 13, (OTHER,))

    assert _stored_races(table) == {"2026-12": [asdict(STINT)], "2026-13": [asdict(OTHER)]}
    assert running.get(2026, 12) == (STINT,), "the running process now serves it too"


@pytest.mark.unit
def test_a_race_stored_between_the_read_and_the_write_is_kept(table):
    running = RaceStintsStore()
    running.get(2026, 12)
    table.before_next_write(lambda: RaceStintsStore().put(2026, 12, (STINT,)))

    running.put(2026, 13, (OTHER,))

    assert set(_stored_races(table)) == {"2026-12", "2026-13"}


@pytest.mark.unit
def test_for_a_race_both_processes_stored_the_later_write_wins(table):
    """Stint rows carry no timestamp, so the race this process writes is the one it keeps."""
    running = RaceStintsStore()
    running.get(2026, 13)
    RaceStintsStore().put(2026, 13, (STINT,))

    running.put(2026, 13, (OTHER,))

    assert _stored_races(table) == {"2026-13": [asdict(OTHER)]}
    assert RaceStintsStore().get(2026, 13) == (OTHER,)


@pytest.mark.unit
def test_dropping_a_race_keeps_the_races_another_process_stored_since(table):
    table.put(DOCUMENT_RACE_STINTS, _document({"2026-19": [asdict(STINT)]}))
    running = RaceStintsStore()
    running.get(2026, 19)
    RaceStintsStore().put(2026, 12, (OTHER,))

    running.drop(2026, 19)

    assert _stored_races(table) == {"2026-12": [asdict(OTHER)]}


@pytest.mark.unit
def test_a_race_another_process_stored_is_served_after_the_refresh_interval(store, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(module, "_clock", lambda: now[0])
    fake = store(payload=None)
    running = RaceStintsStore()
    assert running.get(2026, 13) is None

    fake.payload = _document({"2026-13": [asdict(STINT)]})  # another process stored it
    assert running.get(2026, 13) is None, "inside the interval the held copy is served"

    now[0] += module.REFRESH_SECONDS
    assert running.get(2026, 13) == (STINT,)
    assert fake.reads == 2


@pytest.mark.unit
def test_a_failed_refresh_keeps_serving_the_held_races(store, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(module, "_clock", lambda: now[0])
    fake = store(payload=_document({"2026-13": [asdict(STINT)]}))
    running = RaceStintsStore()
    running.get(2026, 13)

    fake.readable = False
    now[0] += module.REFRESH_SECONDS
    assert running.get(2026, 13) == (STINT,)
    running.put(2026, 12, (OTHER,))

    assert set(fake.payload["races"]) == {"2026-12", "2026-13"}, "writes still go through"
    assert fake.reads == 2, "the failed re-read backs off rather than retrying per call"
