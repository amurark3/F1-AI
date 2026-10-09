"""Tests for ``scripts.backfill_logic_version`` — stamping legacy snapshots.

The script edits stored predictions in place, so the tests here are mostly
about restraint. Three properties matter:

* **It never writes on a failed read.** The store returns ``ok=False`` for an
  outage; rebuilding the document from that would replace every stored
  snapshot with nothing.
* **It only touches the snapshot the cache actually serves.** Superseded
  revisions are the record of what was predicted at the time; rewriting them
  would falsify history for no benefit.
* **It is honest about provenance.** A stamped snapshot was produced by older
  logic, so it must carry ``logic_version_backfilled`` and the version it came
  from — the stamp is a decision to serve it, not a claim it was recomputed.

Dry run is the default, and a second ``--apply`` must find nothing left to do.
"""

from __future__ import annotations

import sys

import pytest

from app.data.predictions import PREDICTION_LOGIC_VERSION
from app.data.store_types import ReadResult, WriteResult
from scripts import backfill_logic_version as backfill

OLD_VERSION = PREDICTION_LOGIC_VERSION - 1


class _FakeStore:
    """Document store whose read/write outcomes each test dictates."""

    def __init__(self, read_result: ReadResult, write_result: WriteResult | None = None) -> None:
        self.read_result = read_result
        self.write_result = write_result or WriteResult()
        self.writes: list[tuple[str, dict]] = []

    def read(self, name: str) -> ReadResult:
        return self.read_result

    def write(self, name: str, payload: dict) -> WriteResult:
        self.writes.append((name, payload))
        if self.write_result.ok:
            # Later reads see the written document, so a second run is a real re-run.
            self.read_result = ReadResult(payload=payload)
        return self.write_result


def _snapshot(snap_id: str, version: int | None = None, **fields) -> dict:
    result: dict = {"predictions": [{"driver": "VER"}]}
    if version is not None:
        result["logic_version"] = version
    return {"id": snap_id, "result": result, **fields}


def _entry(*snapshots: dict, **fields) -> dict:
    return {"snapshots": list(snapshots), **fields}


def _install(monkeypatch, store: _FakeStore, *argv: str) -> None:
    monkeypatch.setattr(backfill, "document_store", store)
    monkeypatch.setattr(sys, "argv", ["backfill_logic_version", *argv])


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({"result": {"logic_version": 7}}, 7),
        ({"result": {}}, 0),
        ({"result": {"logic_version": None}}, 0),
        ({"result": None}, 0),
        ({}, 0),
    ],
    ids=["numbered", "unversioned", "null-version", "null-result", "no-result"],
)
def test_snapshot_version_reads_a_missing_version_as_zero(snapshot, expected):
    assert backfill._snapshot_version(snapshot) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("version", "include_old", "expected"),
    [
        (PREDICTION_LOGIC_VERSION, False, False),
        (PREDICTION_LOGIC_VERSION, True, False),
        (0, False, True),
        (0, True, True),
        (OLD_VERSION, False, False),
        (OLD_VERSION, True, True),
    ],
    ids=["current", "current-include-old", "unversioned", "unversioned-include-old", "old", "old-include-old"],
)
def test_should_stamp_leaves_deliberately_versioned_snapshots_alone(version, include_old, expected):
    snapshot = _snapshot("s1", version=version)

    assert backfill._should_stamp(snapshot, include_old) is expected


@pytest.mark.unit
def test_stamp_records_the_version_it_came_from_without_mutating_the_original():
    original = _snapshot("s1", version=OLD_VERSION)

    stamped = backfill._stamp(original)

    assert stamped["result"]["logic_version"] == PREDICTION_LOGIC_VERSION
    assert stamped["result"][backfill.BACKFILL_MARKER] is True
    assert stamped["result"]["logic_version_backfilled_from"] == OLD_VERSION
    assert original["result"]["logic_version"] == OLD_VERSION, "the input snapshot must not be mutated"


@pytest.mark.unit
def test_stamp_leaves_a_snapshot_with_no_result_object_untouched():
    stamped = backfill._stamp({"id": "s1", "result": "not-a-dict"})

    assert stamped == {"id": "s1", "result": "not-a-dict"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (_entry(), None),
        (_entry(_snapshot("a"), _snapshot("b")), 1),
        (_entry(_snapshot("a"), _snapshot("b"), active_snapshot_id="a"), 0),
        (_entry(_snapshot("a"), _snapshot("b"), active_snapshot_id="missing"), 1),
        ({"snapshots": ["not-a-dict", _snapshot("b")], "active_snapshot_id": "b"}, 1),
    ],
    ids=["empty", "no-active-id", "matched", "unmatched-id", "non-dict-snapshot"],
)
def test_active_index_falls_back_to_the_newest_snapshot(entry, expected):
    assert backfill._active_index(entry) == expected


@pytest.mark.unit
def test_plan_stamps_only_the_active_snapshot():
    entries = {"2026:1": _entry(_snapshot("old"), _snapshot("live"), active_snapshot_id="live")}

    updated, changes = backfill._plan(entries, include_old=False)

    snapshots = updated["2026:1"]["snapshots"]
    assert snapshots[0]["result"] == {"predictions": [{"driver": "VER"}]}, "superseded revisions stay as recorded"
    assert snapshots[1]["result"]["logic_version"] == PREDICTION_LOGIC_VERSION
    assert changes == [f"2026:1: active snapshot live (v0 -> v{PREDICTION_LOGIC_VERSION})"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "entry"),
    [
        ("not-a-dict", "garbage"),
        ("no-snapshots", _entry()),
        ("already-current", _entry(_snapshot("a", version=PREDICTION_LOGIC_VERSION))),
        ("active-not-a-dict", {"snapshots": ["garbage"]}),
    ],
    ids=["non-dict-entry", "empty-entry", "current-version", "non-dict-active"],
)
def test_plan_passes_through_entries_it_cannot_or_should_not_stamp(key, entry):
    updated, changes = backfill._plan({key: entry}, include_old=False)

    assert changes == []
    assert updated == {key: entry}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_main_refuses_to_write_when_the_read_failed(monkeypatch, capsys):
    store = _FakeStore(ReadResult(ok=False, error="connection refused"))
    _install(monkeypatch, store, "--apply")

    exit_code = backfill.main()

    assert exit_code == 1
    assert store.writes == [], "an outage must not be rebuilt into an empty cache document"
    assert "ERROR reading prediction cache: connection refused" in capsys.readouterr().out


@pytest.mark.unit
def test_main_reports_an_absent_document_as_nothing_to_do(monkeypatch, capsys):
    store = _FakeStore(ReadResult(payload=None))
    _install(monkeypatch, store, "--apply")

    exit_code = backfill.main()

    assert exit_code == 0
    assert store.writes == []
    assert "No prediction cache document stored" in capsys.readouterr().out


@pytest.mark.unit
def test_main_stops_before_writing_when_every_snapshot_is_current(monkeypatch, capsys):
    entries = {"2026:1": _entry(_snapshot("a", version=PREDICTION_LOGIC_VERSION))}
    store = _FakeStore(ReadResult(payload={"entries": entries}))
    _install(monkeypatch, store, "--apply")

    exit_code = backfill.main()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert store.writes == []
    assert "entries scanned:      1" in out
    assert "nothing to backfill." in out


@pytest.mark.unit
def test_main_defaults_to_a_dry_run(monkeypatch, capsys):
    entries = {"2026:1": _entry(_snapshot("a"))}
    store = _FakeStore(ReadResult(payload={"entries": entries}))
    _install(monkeypatch, store)

    exit_code = backfill.main()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert store.writes == [], "no --apply means no write"
    assert "entries to stamp:     1" in out
    assert "dry run — re-run with --apply to write." in out


@pytest.mark.unit
def test_main_apply_writes_the_stamped_document_and_is_idempotent(monkeypatch, capsys):
    entries = {"2026:1": _entry(_snapshot("a")), "2026:2": "garbage"}
    store = _FakeStore(ReadResult(payload={"schema_version": 2, "entries": entries}))
    _install(monkeypatch, store, "--apply")

    assert backfill.main() == 0
    assert backfill.main() == 0

    name, payload = store.writes[0]
    stamped = payload["entries"]["2026:1"]["snapshots"][0]["result"]
    assert name == "prediction_cache"
    assert payload["schema_version"] == 2, "unrelated top-level fields survive the rewrite"
    assert stamped["logic_version"] == PREDICTION_LOGIC_VERSION
    assert stamped[backfill.BACKFILL_MARKER] is True
    assert len(store.writes) == 1, "the second run finds nothing left to stamp"
    assert "nothing to backfill." in capsys.readouterr().out


@pytest.mark.unit
def test_main_include_old_stamps_a_previously_numbered_version(monkeypatch, capsys):
    entries = {"2026:1": _entry(_snapshot("a", version=OLD_VERSION))}
    store = _FakeStore(ReadResult(payload={"entries": entries}))
    _install(monkeypatch, store, "--apply", "--include-old")

    exit_code = backfill.main()

    stamped = store.writes[0][1]["entries"]["2026:1"]["snapshots"][0]["result"]
    assert exit_code == 0
    assert stamped["logic_version_backfilled_from"] == OLD_VERSION
    assert f"(v{OLD_VERSION} -> v{PREDICTION_LOGIC_VERSION})" in capsys.readouterr().out


@pytest.mark.unit
def test_main_reports_a_failed_write_as_a_nonzero_exit(monkeypatch, capsys):
    entries = {"2026:1": _entry(_snapshot("a"))}
    store = _FakeStore(
        ReadResult(payload={"entries": entries}),
        WriteResult(ok=False, durable=False, error="write timeout"),
    )
    _install(monkeypatch, store, "--apply")

    exit_code = backfill.main()

    assert exit_code == 1
    assert "ERROR writing prediction cache: write timeout" in capsys.readouterr().out
