"""Tests for ``scripts.migrate_json_to_db`` — local JSON files into the store.

The risk this file covers is one-directional data loss. The script is run once,
by hand, against a deployment that has just been given a ``DATABASE_URL``; it
copies the prediction snapshot cache and the accuracy history out of local JSON
and into Postgres. Two failure modes would be silent and unrecoverable:

* treating an unreadable or malformed local file as "nothing to migrate", and
* reporting success when the store rejected the write.

Both are asserted here, along with re-runnability: the script is documented as
safe to re-run, so a second pass must produce the same stored bytes rather than
appending or clearing anything.
"""

from __future__ import annotations

import json

import pytest

from app.data.store_types import WriteResult
from scripts import migrate_json_to_db as migrate


class _RecordingStore:
    """Stand-in for ``document_store`` that records writes and can fail them."""

    def __init__(self, error: str | None = None) -> None:
        self.writes: list[tuple[str, dict]] = []
        self.error = error

    def write(self, name: str, payload: dict) -> WriteResult:
        self.writes.append((name, payload))
        if self.error is not None:
            return WriteResult(ok=False, durable=False, error=self.error)
        return WriteResult(ok=True, durable=True)


@pytest.fixture
def store(monkeypatch):
    fake = _RecordingStore()
    monkeypatch.setattr(migrate, "document_store", fake)
    return fake


@pytest.fixture
def local_files(tmp_path, monkeypatch):
    """Redirect the two source paths the script reads at module scope."""
    cache = tmp_path / "prediction_cache.json"
    history = tmp_path / "prediction_history.json"
    monkeypatch.setattr(migrate, "PREDICTION_CACHE_PATH", str(cache))
    monkeypatch.setattr(migrate, "PREDICTION_HISTORY_PATH", str(history))
    return cache, history


CACHE_DOC = {"schema_version": 2, "entries": {"2026:1": {"snapshots": []}}}
HISTORY_DOC = {"records": [{"year": 2026, "round": 1, "hit_rate": 0.6}]}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, None),
        ("", None),
        ("   \n  ", None),
        ("[1, 2, 3]", None),
        ('"a string"', None),
        ('{"a": 1}', {"a": 1}),
    ],
    ids=["missing", "empty", "whitespace", "list", "scalar", "object"],
)
def test_load_returns_a_document_only_for_a_json_object(tmp_path, content, expected):
    path = tmp_path / "doc.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert migrate._load(str(path)) == expected


@pytest.mark.integration
def test_main_skips_documents_with_no_local_file(store, local_files, capsys):
    migrate.main()

    out = capsys.readouterr().out
    assert store.writes == [], "nothing on disk must never reach the store"
    assert out.count("skip ") == 2
    assert "done. 0 document(s) migrated." in out


@pytest.mark.integration
def test_main_writes_both_documents_verbatim(store, local_files, capsys):
    cache, history = local_files
    cache.write_text(json.dumps(CACHE_DOC), encoding="utf-8")
    history.write_text(json.dumps(HISTORY_DOC), encoding="utf-8")

    migrate.main()

    assert store.writes == [
        ("prediction_cache", CACHE_DOC),
        ("prediction_history", HISTORY_DOC),
    ]
    assert "done. 2 document(s) migrated." in capsys.readouterr().out


@pytest.mark.integration
def test_main_is_idempotent_across_repeated_runs(store, local_files, capsys):
    cache, _history = local_files
    cache.write_text(json.dumps(CACHE_DOC), encoding="utf-8")

    migrate.main()
    migrate.main()

    # Re-running must upsert the same bytes, never accumulate or truncate.
    assert [payload for _name, payload in store.writes] == [CACHE_DOC, CACHE_DOC]
    assert capsys.readouterr().out.count("done. 1 document(s) migrated.") == 2


@pytest.mark.integration
def test_main_reports_a_rejected_write_and_does_not_count_it(local_files, monkeypatch, capsys):
    cache, history = local_files
    cache.write_text(json.dumps(CACHE_DOC), encoding="utf-8")
    history.write_text(json.dumps(HISTORY_DOC), encoding="utf-8")
    monkeypatch.setattr(migrate, "document_store", _RecordingStore(error="store unreachable"))

    migrate.main()

    out = capsys.readouterr().out
    assert "FAIL  prediction_cache: store unreachable" in out
    # A failed first document must not abort the second one.
    assert "FAIL  prediction_history: store unreachable" in out
    assert "done. 0 document(s) migrated." in out


@pytest.mark.integration
def test_main_refuses_a_malformed_local_file_rather_than_writing_an_empty_document(store, local_files, capsys):
    cache, _history = local_files
    cache.write_text("[]", encoding="utf-8")

    migrate.main()

    assert store.writes == [], "a JSON array is not a document — migrating {} would erase the round"
    assert "skip  prediction_cache" in capsys.readouterr().out


@pytest.mark.integration
def test_main_propagates_unparseable_json_instead_of_silently_skipping(local_files, store):
    cache, _history = local_files
    cache.write_text("{not json", encoding="utf-8")

    # Corrupt input is not "no data": it must stop the operator, not be swallowed.
    with pytest.raises(json.JSONDecodeError):
        migrate.main()

    assert store.writes == []
