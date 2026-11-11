"""Tests for ``scripts.repair_graded_predictions`` — resetting each race's graded call.

The user runs this against production's prediction history, so the properties
pinned are about writing exactly the repair and nothing else, and only where it
was aimed:

* **The target is explicit.** ``DATABASE_URL`` comes from the environment only
  (the script never reads ``backend/.env``), a run without it is refused, and a
  store that fell back to the local file is refused rather than "repaired".
  ``--local`` is the only way to aim it at a file, and only with no database.
* **A dry run writes nothing** and lists every race whose graded call changes,
  with its phase before and after and the drivers that move.
* **Nothing is written before a backup exists**, nor when the document changed
  after it was read; a failed write names the backup.

The fixture is production's R19 and R20 entries from the 2026-11-11 backup:
R20 changes (pre-qualifying VER P2 -> post-qualifying VER P8), R19 does not.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.data.store import BACKEND_FILE, BACKEND_POSTGRES
from app.data.store_types import ReadResult, StoreHealth, WriteResult
from scripts import repair_graded_predictions as repair

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"


def _entry(edition: str) -> dict:
    return json.loads((FIXTURES / edition / "prediction_history_entry.json").read_text(encoding="utf-8"))["entry"]


def _history() -> dict:
    return {"(2026,19)": _entry("mexico_2026_r19"), "(2026,20)": _entry("sao_paulo_2026_r20")}


class _FakeStore:
    """A history store scripted per test; ``reads`` serves successive reads."""

    def __init__(self, backend: str, document: dict | None) -> None:
        self.backend = backend
        self.reads: list[ReadResult] = [ReadResult(payload=document)]
        self.writes: list[dict] = []
        self.write_ok = True

    def health(self) -> StoreHealth:
        return StoreHealth(backend=self.backend, host_kind="supabase_pooler")

    def read(self, name: str) -> ReadResult:
        assert name == "prediction_history"
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def write(self, name: str, payload: dict) -> WriteResult:
        assert name == "prediction_history"
        self.writes.append(payload)
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="connection reset")
        return WriteResult()


@pytest.fixture
def production(monkeypatch) -> _FakeStore:
    """A Postgres store aimed at by DATABASE_URL, holding the R19 and R20 entries."""
    store = _FakeStore(BACKEND_POSTGRES, _history())
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    return store


def _run(*args: str, backup_dir: Path | None = None) -> int:
    extra = ["--backup-dir", str(backup_dir)] if backup_dir is not None else []
    return repair.main([*args, *extra])


# ---------------------------------------------------------------------------
# Planning the repair
# ---------------------------------------------------------------------------


def test_the_plan_changes_r20_and_leaves_r19_alone():
    history = _history()

    repaired, changes = repair.plan(history)

    assert [change.key for change in changes] == ["(2026,20)"]
    [r20] = changes
    assert (r20.before["prediction_phase"], r20.after["prediction_phase"]) == ("pre_qualifying", "post_qualifying")
    assert repaired["(2026,20)"]["predicted_positions"]["VER"] == 8
    assert repaired["(2026,19)"] == history["(2026,19)"]
    assert history == _history(), "the document handed in is never mutated"


def test_races_are_listed_in_calendar_order_and_odd_keys_last():
    def stale(ver: int) -> dict:
        return {
            "predicted_positions": {"VER": 1},
            "snapshots": [{"prediction_phase": "post_qualifying", "predicted_positions": {"VER": ver}}],
        }

    history = {"bogus": stale(4), "(2026,10)": stale(3), "(2025,24)": stale(2), "(2026,9)": stale(5)}

    _, changes = repair.plan(history)

    assert [change.key for change in changes] == ["(2025,24)", "(2026,9)", "(2026,10)", "bogus"]


def test_an_entry_that_is_not_a_record_is_carried_over_untouched():
    repaired, changes = repair.plan({"(2026,1)": "corrupt"})

    assert repaired == {"(2026,1)": "corrupt"}
    assert changes == []


def test_a_change_names_the_drivers_that_move_and_how_many():
    _, [r20] = repair.plan(_history())

    lines = repair.describe(r20)

    assert lines[0] == (
        "  R20 (2026,20)  pre_qualifying 2026-11-11T01:34:47.136982+00:00"
        " -> post_qualifying 2026-11-08T00:45:43.688379+00:00"
    )
    assert "VER P2 -> P8" in lines[1]
    assert lines[1].count(" -> ") == repair.DRIVERS_SHOWN
    assert lines[1].endswith(" of 22 drivers move)")


def test_a_driver_on_only_one_side_is_shown_without_a_position():
    change = repair.RaceChange(
        key="(2026,3)",
        before={"prediction_phase": None, "generated_at": None, "predicted_positions": {"HUL": 4}},
        after={"prediction_phase": "pre_qualifying", "generated_at": "t", "predicted_positions": {"VER": 1}},
    )

    lines = repair.describe(change)

    assert lines[0] == "  R3 (2026,3)  - - -> pre_qualifying t"
    assert lines[1] == "      VER P- -> P1  (1 of 1 drivers move)"


def test_a_race_whose_positions_do_not_move_says_so():
    call = {"prediction_phase": "post_qualifying", "generated_at": "t2", "predicted_positions": {"VER": 1}}
    change = repair.RaceChange(key="odd", before={**call, "generated_at": "t1"}, after=call)

    assert repair.describe(change) == ["  odd  post_qualifying t1 -> post_qualifying t2", "      no driver moves"]


# ---------------------------------------------------------------------------
# Aiming the run
# ---------------------------------------------------------------------------


def test_a_run_without_database_url_is_refused(monkeypatch, capsys):
    store = _FakeStore(BACKEND_FILE, _history())
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _run("--apply") == repair.EXIT_NO_DATABASE
    assert "never reads backend/.env" in capsys.readouterr().out
    assert store.writes == []


def test_a_store_that_fell_back_to_the_local_file_is_refused(production, capsys):
    production.backend = BACKEND_FILE

    assert _run("--apply") == repair.EXIT_WRONG_STORE
    assert "local file" in capsys.readouterr().out
    assert production.writes == []


def test_local_is_refused_while_a_database_is_configured(production):
    assert _run("--local", "--apply") == repair.EXIT_WRONG_STORE
    assert production.writes == []


def test_local_repairs_the_file_store_with_no_database(monkeypatch, tmp_path, capsys):
    store = _FakeStore(BACKEND_FILE, _history())
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.setenv("DATABASE_URL", "  ")

    assert _run("--local", "--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "store: file" in capsys.readouterr().out
    assert store.writes[0]["(2026,20)"]["prediction_phase"] == "post_qualifying"


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_a_dry_run_lists_r20_and_writes_nothing(production, tmp_path, capsys):
    assert _run(backup_dir=tmp_path) == repair.EXIT_OK

    out = capsys.readouterr().out
    assert "store: postgres (supabase_pooler)" in out
    assert "1 of 2 race(s) change their graded call" in out
    assert "R20 (2026,20)  pre_qualifying" in out
    assert "R19" not in out
    assert "dry run" in out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == [], "a dry run makes no backup either"


def test_a_history_with_nothing_to_repair_writes_nothing(production, tmp_path, capsys):
    production.reads = [ReadResult(payload={"(2026,19)": _entry("mexico_2026_r19")})]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "nothing to repair" in capsys.readouterr().out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == []


def test_an_empty_store_has_nothing_to_repair(production, tmp_path, capsys):
    production.reads = [ReadResult(payload=None)]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "no prediction history" in capsys.readouterr().out
    assert production.writes == []


def test_an_unreadable_history_stops_the_run(production, capsys):
    production.reads = [ReadResult(ok=False, error="timeout expired")]

    assert _run("--apply") == repair.EXIT_STORE_ERROR
    assert "timeout expired" in capsys.readouterr().out
    assert production.writes == []


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def test_apply_backs_up_the_document_then_writes_the_repair(production, tmp_path, capsys):
    original = _history()

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK

    [backup] = list(tmp_path.iterdir())
    assert backup.name.startswith("prediction_history-")
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    [written] = production.writes
    assert written["(2026,20)"]["prediction_phase"] == "post_qualifying"
    assert written["(2026,20)"]["predicted_positions"]["VER"] == 8
    assert written["(2026,19)"] == original["(2026,19)"]
    assert f"repaired 1 race(s); backup: {backup}" in capsys.readouterr().out


def test_a_failed_backup_writes_nothing(production, tmp_path, capsys):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")

    assert _run("--apply", backup_dir=blocked) == repair.EXIT_STORE_ERROR
    assert "backup failed" in capsys.readouterr().out
    assert production.writes == []


def test_a_history_that_changed_after_it_was_read_is_not_overwritten(production, tmp_path, capsys):
    newer = copy.deepcopy(_history())
    newer["(2026,21)"] = {"predicted_positions": {"VER": 2}}
    production.reads = [ReadResult(payload=_history()), ReadResult(payload=newer)]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert "changed while" in capsys.readouterr().out
    assert production.writes == []


def test_a_history_that_cannot_be_read_again_is_not_overwritten(production, tmp_path):
    production.reads = [ReadResult(payload=_history()), ReadResult(ok=False, error="gone")]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert production.writes == []


def test_a_failed_write_names_the_backup(production, tmp_path, capsys):
    production.write_ok = False

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_WRITE_FAILED

    out = capsys.readouterr().out
    [backup] = list(tmp_path.iterdir())
    assert "connection reset" in out
    assert str(backup) in out
