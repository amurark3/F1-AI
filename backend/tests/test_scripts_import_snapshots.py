"""Tests for ``scripts.import_snapshots`` — recovering snapshots from a server
that could not persist them.

The script exists to salvage work, so the risk it carries is destroying the
thing it is salvaging. Three properties are asserted here:

* **It never writes on a failed read.** ``read.ok == False`` is an outage, not
  an empty cache; merging into ``{}`` and writing would replace every stored
  round with only the harvested ones.
* **It never drops an existing snapshot.** A round that gains an imported
  revision keeps every earlier one, and the prior ``stored_at``/``policy``
  survive untouched.
* **Dry run is the default.** Nothing reaches the store without ``--apply``.

The re-run behaviour is pinned too, because it is *not* idempotent: the dedupe
key embeds the snapshot's position in the list, so importing the same harvest
twice appends the same result under a fresh id. See
``test_reimporting_the_same_harvest_appends_a_duplicate_snapshot``.
"""

from __future__ import annotations

import json

import pytest

from app.data.store_types import ReadResult, WriteResult
from app.services.prediction_cache import CACHE_POLICY, CACHE_SCHEMA_VERSION
from scripts import import_snapshots

STORED_AT = "2026-03-08T14:30:00+00:00"


def _payload(**fields) -> dict:
    """One ``/snapshot`` response body, overridable field by field."""
    return {
        "year": 2026,
        "round": 1,
        "predictions": [{"driver": "VER", "position": 1}],
        "cache": {"stored_at": STORED_AT, "reason": "scheduled"},
        **fields,
    }


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
        return self.write_result


@pytest.fixture
def run_script(tmp_path, monkeypatch):
    """Invoke ``main()`` against a harvest file and a store, returning its code."""

    def _run(harvest, store, *flags) -> int:
        source = tmp_path / "harvest.json"
        source.write_text(json.dumps(harvest) if not isinstance(harvest, str) else harvest, encoding="utf-8")
        monkeypatch.setattr(import_snapshots, "document_store", store)
        monkeypatch.setattr("sys.argv", ["import_snapshots", str(source), *flags])
        return import_snapshots.main()

    return _run


@pytest.mark.unit
def test_strip_derived_keeps_only_what_the_model_produced():
    payload = _payload(model_summary="…", model_inputs={}, model_limitations=[], prediction_review={})

    stripped = import_snapshots._strip_derived(payload)

    # Everything in DERIVED_KEYS is recomputed on read; storing it bloats the document.
    assert set(stripped) == {"year", "round", "predictions"}


@pytest.mark.unit
def test_snapshot_carries_the_cache_metadata_and_import_provenance():
    snapshot = import_snapshots._snapshot_from(_payload(), position=3)

    assert snapshot["id"] == f"v3-{STORED_AT}"
    assert snapshot["stored_at"] == STORED_AT
    assert snapshot["reason"] == "scheduled"
    # Provenance matters: this was recovered, not written by the store.
    assert snapshot["imported_from"] == "ephemeral_runtime"
    assert snapshot["result"] == {"year": 2026, "round": 1, "predictions": [{"driver": "VER", "position": 1}]}


@pytest.mark.unit
@pytest.mark.parametrize("cache", [None, {}], ids=["absent", "empty"])
def test_snapshot_without_cache_metadata_is_stamped_now_as_a_manual_compute(cache):
    snapshot = import_snapshots._snapshot_from(_payload(cache=cache), position=1)

    assert snapshot["reason"] == "manual_compute"
    assert snapshot["id"] == f"v1-{snapshot['stored_at']}"
    assert snapshot["stored_at"].endswith("+00:00"), "an unstamped snapshot must still be timezone-explicit"


@pytest.mark.unit
def test_merge_ignores_rounds_that_carry_no_predictions():
    updated, changes = import_snapshots._merge({}, {"2026:1": _payload(predictions=[])})

    assert updated == {}
    assert changes == []


@pytest.mark.unit
def test_merge_creates_a_new_round_with_the_current_schema_and_policy():
    updated, changes = import_snapshots._merge({}, {"2026:1": _payload()})

    entry = updated["2026:1"]
    assert entry["schema_version"] == CACHE_SCHEMA_VERSION
    assert entry["policy"] == CACHE_POLICY
    assert entry["stored_at"] == STORED_AT
    assert entry["updated_at"] == STORED_AT
    assert entry["active_snapshot_id"] == f"v1-{STORED_AT}"
    assert changes == [f"2026:1: +1 snapshot (new round) -> active v1-{STORED_AT}"]


@pytest.mark.unit
def test_merge_appends_to_an_existing_round_without_losing_earlier_revisions():
    existing = {
        "2026:1": {
            "schema_version": 1,
            "stored_at": "2026-01-01T00:00:00+00:00",
            "policy": "legacy-policy",
            "active_snapshot_id": "old-1",
            "snapshots": [{"id": "old-1", "result": {"predictions": ["kept"]}}],
        }
    }

    updated, changes = import_snapshots._merge(existing, {"2026:1": _payload()})

    entry = updated["2026:1"]
    assert [s["id"] for s in entry["snapshots"]] == ["old-1", f"v2-{STORED_AT}"]
    # The original creation time and policy are history, not something to overwrite.
    assert entry["stored_at"] == "2026-01-01T00:00:00+00:00"
    assert entry["policy"] == "legacy-policy"
    assert entry["updated_at"] == STORED_AT
    assert entry["active_snapshot_id"] == f"v2-{STORED_AT}"
    assert changes == [f"2026:1: +1 snapshot (1 kept) -> active v2-{STORED_AT}"]


@pytest.mark.unit
def test_merge_skips_when_the_generated_id_collides_with_a_stored_one():
    existing = {"2026:1": {"snapshots": [{"id": f"v2-{STORED_AT}"}]}}

    updated, changes = import_snapshots._merge(existing, {"2026:1": _payload()})

    assert changes == ["2026:1: already imported, skipping"]
    assert updated == existing, "a collision must leave the round exactly as it was"


@pytest.mark.unit
def test_merge_does_not_mutate_the_entries_it_was_given():
    existing = {"2026:1": {"snapshots": [{"id": "old-1"}]}}

    import_snapshots._merge(existing, {"2026:1": _payload()})

    assert existing == {"2026:1": {"snapshots": [{"id": "old-1"}]}}


@pytest.mark.integration
def test_a_source_that_is_not_a_json_object_is_rejected_before_any_read(run_script, capsys):
    store = _FakeStore(ReadResult(payload={"entries": {}}))

    code = run_script([{"year": 2026}], store)

    assert code == 1
    assert "ERROR: source must be a JSON object" in capsys.readouterr().out
    assert store.writes == []


@pytest.mark.integration
def test_a_failed_read_stops_the_import_instead_of_merging_into_nothing(run_script, capsys):
    store = _FakeStore(ReadResult(ok=False, error="connection refused"))

    code = run_script({"2026:1": _payload()}, store, "--apply")

    assert code == 1
    assert "ERROR reading prediction cache: connection refused" in capsys.readouterr().out
    assert store.writes == [], "an outage read as an empty cache would erase every stored round"


@pytest.mark.integration
def test_a_dry_run_reports_the_plan_and_writes_nothing(run_script, capsys):
    store = _FakeStore(ReadResult(payload={"schema_version": CACHE_SCHEMA_VERSION, "entries": {"2025:9": {}}}))

    code = run_script({"2026:1": _payload(), "2026:2": _payload(predictions=[])}, store)

    out = capsys.readouterr().out
    assert code == 0
    assert store.writes == []
    assert "harvested rounds: 2" in out
    assert "stored before:    1" in out
    assert "stored after:     2" in out
    assert "dry run — re-run with --apply to write." in out


@pytest.mark.integration
def test_apply_writes_the_merged_cache_and_preserves_untouched_rounds(run_script, capsys):
    stored = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {"2025:9": {"snapshots": [{"id": "keep"}]}}}
    store = _FakeStore(ReadResult(payload=stored))

    code = run_script({"2026:1": _payload()}, store, "--apply")

    assert code == 0
    name, written = store.writes[0]
    assert name == import_snapshots.DOCUMENT_PREDICTION_CACHE
    assert written["schema_version"] == CACHE_SCHEMA_VERSION
    assert set(written["entries"]) == {"2025:9", "2026:1"}
    assert written["entries"]["2025:9"] == {"snapshots": [{"id": "keep"}]}
    assert "applied. 1 round(s) updated." in capsys.readouterr().out


@pytest.mark.integration
def test_apply_against_a_store_with_no_cache_document_starts_a_fresh_one(run_script):
    store = _FakeStore(ReadResult(payload=None))

    code = run_script({"2026:1": _payload()}, store, "--apply")

    assert code == 0
    _name, written = store.writes[0]
    assert written["schema_version"] == CACHE_SCHEMA_VERSION
    assert list(written["entries"]) == ["2026:1"]


@pytest.mark.integration
def test_a_rejected_write_is_reported_as_a_failure_not_a_success(run_script, capsys):
    store = _FakeStore(
        ReadResult(payload={"entries": {}}),
        WriteResult(ok=False, durable=False, error="read-only transaction"),
    )

    code = run_script({"2026:1": _payload()}, store, "--apply")

    assert code == 1
    assert "ERROR writing prediction cache: read-only transaction" in capsys.readouterr().out


@pytest.mark.integration
def test_reimporting_the_same_harvest_appends_a_duplicate_snapshot(run_script):
    """Live bug: re-running an import is not idempotent.

    ``_merge`` dedupes on ``f"v{len(snapshots) + 1}-{stored_at}"``, so once a
    snapshot has been appended the next run computes a *different* id for
    identical content and stores it again. Nothing is lost, but the round grows
    a redundant revision on every re-run. Pinned so the fix is a visible change.
    """
    store = _FakeStore(ReadResult(payload={"entries": {}}))
    run_script({"2026:1": _payload()}, store, "--apply")

    _name, first = store.writes[0]
    store.read_result = ReadResult(payload=first)
    run_script({"2026:1": _payload()}, store, "--apply")

    _name, second = store.writes[1]
    snapshots = second["entries"]["2026:1"]["snapshots"]
    assert [s["id"] for s in snapshots] == [f"v1-{STORED_AT}", f"v2-{STORED_AT}"]
    assert snapshots[0]["result"] == snapshots[1]["result"]
