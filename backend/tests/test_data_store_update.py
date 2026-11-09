"""Tests for ``DocumentStore.update``: whole documents shared between processes.

Three caches (prediction snapshots, circuit references, race stints) hold a whole
document in memory for the life of the process. They used to write that copy
back whole, so a write another process made in between (a backfill script, a
scheduled job) was silently overwritten. Render's restarts hid it; a server that
never restarts would keep the stale copy for good.

``update`` takes a *change*, not a document. It reads the latest document,
applies the change to it, and writes only if the document is still at the
version it read (``UPDATE … WHERE version = seen``); otherwise it re-reads,
re-applies and tries again, a bounded number of times. The properties pinned:

* another process's write that lands between the read and the write survives;
* a change queued during an outage is replayed against the latest document,
  never as the stale whole document it would have produced at the time;
* a queued whole document from ``write`` is dropped, not replayed, once another
  process has written the document since this process last read it;
* the local-file backend applies the change to what is on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from app.data import store as store_module
from app.data.store import (
    DOCUMENT_CIRCUIT_REFERENCE,
    DOCUMENT_PREDICTION_CACHE,
    DOCUMENT_PREDICTION_HISTORY,
    MAX_UPDATE_ATTEMPTS,
    FileDocumentStore,
    PostgresDocumentStore,
)
from app.data.store_types import WriteResult
from tests.document_table_support import DocumentTable, install_document_table

DSN = "postgresql://user:pw@postgres:5432/f1ai"
DOC = DOCUMENT_PREDICTION_CACHE


def _add(key: str, value: object):
    """A change that sets one key of a map document, keeping every other key."""

    def change(current: dict | None) -> dict:
        return {**(current or {}), key: value}

    return change


@pytest.fixture
def table(monkeypatch, tmp_path) -> DocumentTable:
    return install_document_table(monkeypatch, tmp_path)


@pytest.fixture
def pg(table) -> PostgresDocumentStore:
    return PostgresDocumentStore(DSN)


@pytest.fixture(autouse=True)
def fallback_files(monkeypatch, tmp_path) -> dict[str, Path]:
    """Every test's local fallback files live in a throwaway directory, never the repo's ``data/``."""
    mapping = {
        DOCUMENT_PREDICTION_CACHE: str(tmp_path / "cache.json"),
        DOCUMENT_PREDICTION_HISTORY: str(tmp_path / "history.json"),
        DOCUMENT_CIRCUIT_REFERENCE: str(tmp_path / "circuit_reference.json"),
    }
    monkeypatch.setattr(store_module, "_FALLBACK_FILES", mapping)
    return {name: Path(path) for name, path in mapping.items()}


# ---------------------------------------------------------------------------
# Schema and versions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_schema_adds_the_version_column_idempotently():
    """An existing production table gains the column on the next boot, and a second boot is a no-op."""
    assert "ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0" in store_module._SCHEMA_SQL


@pytest.mark.unit
def test_a_postgres_read_reports_the_version_it_saw(table, pg):
    table.put(DOC, {"a": 1})
    table.put(DOC, {"a": 2})

    read = pg.read(DOC)

    assert (read.payload, read.version) == ({"a": 2}, 2)


@pytest.mark.unit
def test_a_plain_write_moves_the_version_on(table, pg):
    """``write`` callers must be visible to ``update`` callers, or their writes would be lost."""
    pg.write(DOC, {"a": 1})
    pg.write(DOC, {"a": 2})

    assert table.version(DOC) == 2


@pytest.mark.unit
def test_a_file_read_carries_no_version(fallback_files):
    fallback_files[DOC].write_text('{"a": 1}', encoding="utf-8")

    assert FileDocumentStore().read(DOC).version is None


# ---------------------------------------------------------------------------
# Postgres update: the conditional write
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_update_creates_a_missing_document(table, pg):
    result = pg.update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.durable, result.payload) == (True, True, {"2026:1": "ours"})
    assert table.rows[DOC] == ({"2026:1": "ours"}, 1)


@pytest.mark.unit
def test_update_applies_the_change_to_the_latest_document_not_to_a_held_copy(table, pg):
    """The other process wrote after this one last read; its entry is kept."""
    pg.read(DOC)  # this process's view: no document
    table.put(DOC, {"2026:2": "theirs"})

    result = pg.update(DOC, _add("2026:1", "ours"))

    assert result.payload == {"2026:1": "ours", "2026:2": "theirs"}
    assert table.payload(DOC) == {"2026:1": "ours", "2026:2": "theirs"}


@pytest.mark.unit
def test_a_write_between_the_read_and_the_write_is_merged_not_overwritten(table, pg):
    """The race itself: the conditional write misses, so the change is re-applied to the new document."""
    table.put(DOC, {"2026:1": "base"})
    table.before_next_write(lambda: table.put(DOC, {"2026:1": "base", "2026:2": "theirs"}))

    with structlog.testing.capture_logs() as logs:
        result = pg.update(DOC, _add("2026:3", "ours"))

    assert result.ok is True
    assert table.payload(DOC) == {"2026:1": "base", "2026:2": "theirs", "2026:3": "ours"}
    assert table.version(DOC) == 3
    assert [entry["event"] for entry in logs] == ["store.pg_update_conflict"]


@pytest.mark.unit
def test_a_concurrent_first_write_is_merged_too(table, pg):
    """Two processes creating the document: the losing insert re-reads and merges."""
    table.before_next_write(lambda: table.put(DOC, {"2026:2": "theirs"}))

    pg.update(DOC, _add("2026:1", "ours"))

    assert table.payload(DOC) == {"2026:1": "ours", "2026:2": "theirs"}


@pytest.mark.unit
def test_update_gives_up_after_a_bounded_number_of_conflicts(table, pg):
    """Not an outage, so not queued: a retry would only lose the same race again."""
    table.put(DOC, {})

    def keep_writing() -> None:
        table.put(DOC, {"busy": table.version(DOC)})
        table.before_next_write(keep_writing)

    table.before_next_write(keep_writing)

    result = pg.update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.durable, result.payload) == (False, False, None)
    assert "conflict" in (result.error or "")
    assert pg.health().pending_documents == ()
    assert sum("UPDATE app_documents" in sql for sql in table.statements) == MAX_UPDATE_ATTEMPTS


@pytest.mark.unit
def test_a_change_that_raises_is_reported_and_never_queued(table, pg):
    """Queued, it would fail again on every retry and block every later write."""

    def broken(_current: dict | None) -> dict:
        raise KeyError("entries")

    result = pg.update(DOC, broken)
    later = pg.update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.durable, result.payload) == (False, False, None)
    assert pg.health().pending_documents == ()
    assert later.payload == {"2026:1": "ours"}


@pytest.mark.unit
def test_a_queued_change_that_can_no_longer_apply_is_dropped_not_retried_forever(table, pg, fallback_files):
    table.fail_on = "SELECT payload"
    pg.update(DOC, _add("2026:1", "ours"))
    table.fail_on = None
    fallback_files[DOC].write_text("{not json", encoding="utf-8")

    with structlog.testing.capture_logs() as logs:
        written = pg.write(DOCUMENT_PREDICTION_HISTORY, {"unrelated": True})

    assert written.ok is True, "one bad queued change must not block other documents"
    assert pg.health().pending_documents == ()
    assert "store.pg_pending_dropped" in [entry["event"] for entry in logs]
    assert DOC not in table.rows


@pytest.mark.unit
def test_update_promotes_a_pre_postgres_local_file(table, pg, fallback_files):
    """With no row yet, the change applies to the local file a read would have served."""
    fallback_files[DOC].write_text('{"legacy": true}', encoding="utf-8")

    pg.update(DOC, _add("2026:1", "ours"))

    assert table.payload(DOC) == {"legacy": True, "2026:1": "ours"}


@pytest.mark.unit
def test_update_never_writes_on_top_of_an_unreadable_local_file(table, pg, fallback_files):
    fallback_files[DOC].write_text("{not json", encoding="utf-8")

    result = pg.update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.payload) == (False, None)
    assert DOC not in table.rows


@pytest.mark.unit
def test_update_over_a_row_that_is_not_an_object_replaces_it(table, pg):
    """The row's version still guards the write, so a corrupt row cannot wedge every update."""
    table.rows = {DOC: (["not", "an", "object"], 4)}

    result = pg.update(DOC, _add("2026:1", "ours"))

    assert result.ok is True
    assert table.rows[DOC] == ({"2026:1": "ours"}, 5)


# ---------------------------------------------------------------------------
# Postgres update: the retry queue replays changes, not stale documents
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_failed_update_is_queued_and_reported(table, pg):
    table.fail_on = "SELECT payload"

    result = pg.update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.durable, result.payload) == (False, False, None)
    assert pg.health().ok is False
    assert pg.health().pending_documents == (DOC,)


@pytest.mark.unit
def test_a_queued_change_is_replayed_against_the_latest_document(table, pg):
    """Replaying the whole document this process held would erase the other process's entry."""
    table.fail_on = "SELECT payload"
    pg.update(DOC, _add("2026:1", "ours"))
    table.fail_on = None
    table.put(DOC, {"2026:2": "theirs"})

    pg.write(DOCUMENT_PREDICTION_HISTORY, {"unrelated": True})  # any successful contact flushes

    assert table.payload(DOC) == {"2026:1": "ours", "2026:2": "theirs"}
    assert pg.health().pending_documents == ()


@pytest.mark.unit
def test_queued_changes_apply_in_order_before_the_next_change_to_the_same_document(table, pg):
    table.fail_on = "SELECT payload"
    pg.update(DOC, _add("2026:1", "first"))
    pg.update(DOC, _add("2026:1", "second"))
    table.fail_on = None

    result = pg.update(DOC, _add("2026:2", "third"))

    assert result.payload == {"2026:1": "second", "2026:2": "third"}
    assert pg.health().pending_documents == ()


@pytest.mark.unit
def test_a_queued_change_is_replayed_by_the_next_update_of_another_document(table, pg):
    table.fail_on = "SELECT payload"
    pg.update(DOC, _add("2026:1", "ours"))
    table.fail_on = None

    pg.update(DOCUMENT_CIRCUIT_REFERENCE, _add("monza:2026", "ref"))

    assert table.payload(DOC) == {"2026:1": "ours"}


@pytest.mark.unit
def test_a_queued_whole_document_is_dropped_once_another_process_has_written(table, pg):
    """``write`` hands over a whole document built from this process's last read; replaying it later would erase newer writes."""
    table.put(DOCUMENT_PREDICTION_HISTORY, {"2026:1": "seen"})
    seen = pg.read(DOCUMENT_PREDICTION_HISTORY).payload
    table.fail_on = "ON CONFLICT (name)"
    pg.write(DOCUMENT_PREDICTION_HISTORY, {**seen, "2026:2": "ours"})
    table.fail_on = None
    table.put(DOCUMENT_PREDICTION_HISTORY, {"2026:1": "seen", "2026:3": "theirs"})

    with structlog.testing.capture_logs() as logs:
        pg.write(DOC, {"unrelated": True})

    assert table.payload(DOCUMENT_PREDICTION_HISTORY) == {"2026:1": "seen", "2026:3": "theirs"}
    assert pg.health().pending_documents == ()
    assert "store.pg_pending_stale_dropped" in [entry["event"] for entry in logs]


@pytest.mark.unit
def test_a_queued_whole_document_is_replayed_while_the_document_is_unchanged(table, pg):
    table.put(DOCUMENT_PREDICTION_HISTORY, {"2026:1": "seen"})
    pg.read(DOCUMENT_PREDICTION_HISTORY)
    table.fail_on = "ON CONFLICT (name)"
    pg.write(DOCUMENT_PREDICTION_HISTORY, {"2026:1": "seen", "2026:2": "ours"})
    table.fail_on = None

    pg.write(DOC, {"unrelated": True})

    assert table.payload(DOCUMENT_PREDICTION_HISTORY) == {"2026:1": "seen", "2026:2": "ours"}


@pytest.mark.unit
def test_a_queued_whole_document_this_process_never_read_is_replayed_as_before(table, pg):
    """A blind write carries no version to check, so it keeps its old last-writer-wins replay."""
    table.fail_on = "ON CONFLICT (name)"
    pg.write(DOCUMENT_PREDICTION_HISTORY, {"blind": True})
    table.fail_on = None
    table.put(DOCUMENT_PREDICTION_HISTORY, {"theirs": True})

    pg.write(DOC, {"unrelated": True})

    assert table.payload(DOCUMENT_PREDICTION_HISTORY) == {"blind": True}


@pytest.mark.unit
def test_a_queued_change_survives_a_second_outage(table, pg):
    table.fail_on = "SELECT payload"
    pg.update(DOC, _add("2026:1", "ours"))
    table.fail_on = "ON CONFLICT (name)"

    pg.write(DOCUMENT_PREDICTION_HISTORY, {"unrelated": True})

    assert set(pg.health().pending_documents) == {DOC, DOCUMENT_PREDICTION_HISTORY}


# ---------------------------------------------------------------------------
# File backend: one process, so the change applies to what is on disk
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_file_update_applies_the_change_to_the_file_on_disk(fallback_files):
    FileDocumentStore().write(DOC, {"2026:2": "theirs"})

    result = FileDocumentStore().update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.payload) == (True, {"2026:1": "ours", "2026:2": "theirs"})
    assert FileDocumentStore().read(DOC).payload == {"2026:1": "ours", "2026:2": "theirs"}


@pytest.mark.unit
def test_file_update_of_a_missing_document_starts_from_nothing(fallback_files):
    result = FileDocumentStore().update(DOC, _add("2026:1", "ours"))

    assert result.payload == {"2026:1": "ours"}


@pytest.mark.unit
def test_file_update_never_writes_on_top_of_a_corrupt_file(fallback_files):
    fallback_files[DOC].write_text("{not json", encoding="utf-8")

    result = FileDocumentStore().update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.payload) == (False, None)
    assert fallback_files[DOC].read_text(encoding="utf-8") == "{not json"


@pytest.mark.unit
def test_file_update_reports_a_failed_write(fallback_files, monkeypatch):
    monkeypatch.setattr(
        FileDocumentStore,
        "write",
        lambda _self, _name, _payload: WriteResult(ok=False, durable=False, error="disk full"),
    )

    result = FileDocumentStore().update(DOC, _add("2026:1", "ours"))

    assert (result.ok, result.durable, result.error, result.payload) == (False, False, "disk full", None)
