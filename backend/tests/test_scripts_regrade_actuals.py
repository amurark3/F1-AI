"""Tests for ``scripts.regrade_actuals``: re-recording results graded before they carried a source.

The user runs this against production's prediction history, so the properties
pinned are the ones ``repair_graded_predictions`` has: the target is explicit,
a dry run writes nothing, nothing is written before the history is backed up
nor when it changed after it was read, and a second run finds nothing to do.
On top of those, only a race recorded without a source is touched, only its
result fields change (never the graded call), and a race the feeds publish no
classification for is left as it is.

The fixture is production's R19 (Mexico City) entry from the 2026-11-11 backup,
graded on Jolpica's pre-penalty order, and the real OpenF1 capture of the final
one.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.data.race_classification import (
    NO_CLASSIFICATION,
    OPENF1_SOURCE,
    RaceClassification,
    classification_from_openf1,
)
from app.data.store import BACKEND_FILE, BACKEND_POSTGRES
from app.data.store_types import ReadResult, StoreHealth, WriteResult
from scripts import regrade_actuals as regrade, repair_graded_predictions as repair

pytestmark = pytest.mark.unit

R19 = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
HISTORY = "prediction_history"


def _r19(name: str) -> list | dict:
    return json.loads((R19 / name).read_text())


def _final() -> RaceClassification:
    codes = {row["driver_number"]: row["name_acronym"] for row in _r19("openf1_drivers.json")}
    drivers = classification_from_openf1(_r19("openf1_session_result.json"), codes)
    return RaceClassification(source=OPENF1_SOURCE, drivers=drivers)


def _history() -> dict:
    return {"(2026,19)": copy.deepcopy(_r19("prediction_history_entry.json")["entry"])}


class _FakeStore:
    def __init__(self, backend: str, history: object) -> None:
        self.backend = backend
        self.reads = [ReadResult(payload=history)]
        self.writes: list[dict] = []
        self.write_ok = True

    def health(self) -> StoreHealth:
        return StoreHealth(backend=self.backend, host_kind="supabase_pooler")

    def read(self, name: str) -> ReadResult:
        assert name == HISTORY
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def write(self, name: str, payload: dict) -> WriteResult:
        assert name == HISTORY, "the regrade writes only the history document"
        self.writes.append(payload)
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="connection reset")
        return WriteResult()


@pytest.fixture
def production(monkeypatch) -> _FakeStore:
    """A Postgres store aimed at by DATABASE_URL, holding R19 as it was graded, and OpenF1 serving the final order."""
    store = _FakeStore(BACKEND_POSTGRES, _history())
    monkeypatch.setattr(regrade, "document_store", store)
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.setattr(regrade, "race_classification", lambda year, round_num: _final())
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    return store


def _run(*args: str, backup_dir: Path | None = None) -> int:
    extra = ["--backup-dir", str(backup_dir)] if backup_dir is not None else []
    return regrade.main([*args, *extra])


def test_a_dry_run_lists_the_drivers_the_penalties_move_and_writes_nothing(production, capsys):
    assert _run() == regrade.EXIT_OK

    out = capsys.readouterr().out
    assert "R19 (2026,19)  from openf1-session-result" in out
    assert "PIA P7 Finished -> P13 Finished" in out
    assert "16 driver(s) change" in out
    assert "dry run" in out
    assert production.writes == []


def test_apply_backs_up_the_history_then_writes_only_the_results(production, tmp_path):
    before = _history()["(2026,19)"]

    assert _run("--apply", backup_dir=tmp_path) == regrade.EXIT_OK

    assert json.loads(next(tmp_path.glob("prediction_history-*.json")).read_text()) == _history()
    after = production.writes[0]["(2026,19)"]
    assert after["actual_positions"]["PIA"] == 13
    assert (after["actual_source"], after["actual_provisional"]) == (OPENF1_SOURCE, True)
    assert after["actual_statuses"]["LIN"] == "DNF"
    untouched = {key: value for key, value in after.items() if not key.startswith("actual_")}
    assert untouched == {key: value for key, value in before.items() if not key.startswith("actual_")}


def test_a_second_run_finds_nothing_to_regrade(production, tmp_path, capsys):
    _run("--apply", backup_dir=tmp_path)
    production.reads = [ReadResult(payload=production.writes[0])]

    assert _run("--apply", backup_dir=tmp_path) == regrade.EXIT_OK
    assert "nothing to regrade" in capsys.readouterr().out
    assert len(production.writes) == 1


def test_a_race_with_no_published_classification_is_left_as_it_is(production, monkeypatch, capsys):
    monkeypatch.setattr(regrade, "race_classification", lambda year, round_num: NO_CLASSIFICATION)

    assert _run("--apply") == regrade.EXIT_OK

    out = capsys.readouterr().out
    assert "no classification published; left as it is" in out
    assert "nothing changes" in out
    assert production.writes == []


def test_only_a_race_recorded_without_a_source_is_touched(production, capsys):
    legacy = _history()["(2026,19)"]
    production.reads = [
        ReadResult(
            payload={
                "(2026,19)": {**legacy, "actual_provisional": False},
                "(2026,20)": {"predicted_positions": {"VER": 1}},
                "(2026,21)": "not a record",
                "odd": legacy,
            }
        )
    ]

    assert _run("--apply") == regrade.EXIT_OK
    assert "nothing to regrade" in capsys.readouterr().out
    assert production.writes == []


def test_a_history_that_is_not_a_document_has_nothing_to_regrade(production, capsys):
    production.reads = [ReadResult(payload=["not", "a", "document"])]

    assert _run() == regrade.EXIT_OK
    assert "nothing to regrade" in capsys.readouterr().out


def test_a_run_without_database_url_is_refused(monkeypatch, capsys):
    store = _FakeStore(BACKEND_FILE, _history())
    monkeypatch.setattr(regrade, "document_store", store)
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _run("--apply") == repair.EXIT_NO_DATABASE
    assert "never reads backend/.env" in capsys.readouterr().out


def test_an_unreadable_history_stops_the_run(production, capsys):
    production.reads = [ReadResult(ok=False, error="boom")]

    assert _run("--apply") == regrade.EXIT_STORE_ERROR
    assert "ERROR reading the prediction history: boom" in capsys.readouterr().out


def test_a_failed_backup_writes_nothing(production, tmp_path, capsys):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")

    assert _run("--apply", backup_dir=blocked) == regrade.EXIT_STORE_ERROR
    assert "backup failed" in capsys.readouterr().out
    assert production.writes == []


@pytest.mark.parametrize("again", [ReadResult(payload={}), ReadResult(ok=False, error="gone")])
def test_a_history_that_changed_or_cannot_be_read_again_is_not_overwritten(production, tmp_path, capsys, again):
    production.reads = [ReadResult(payload=_history()), again]

    assert _run("--apply", backup_dir=tmp_path) == regrade.EXIT_STORE_ERROR
    assert "changed while" in capsys.readouterr().out
    assert production.writes == []


def test_a_failed_write_names_the_backup(production, tmp_path, capsys):
    production.write_ok = False

    assert _run("--apply", backup_dir=tmp_path) == regrade.EXIT_WRITE_FAILED
    out = capsys.readouterr().out
    assert "connection reset" in out
    assert "prediction_history-" in out
