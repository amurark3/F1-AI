"""Tests for ``scripts.repair_graded_predictions``: each race's graded call, and the calls never stored.

The user runs this against production's prediction history, so the properties
pinned are about writing exactly the repair and nothing else, and only where it
was aimed:

* **The target is explicit.** ``DATABASE_URL`` comes from the environment only
  (the script never reads ``backend/.env``), a run without it is refused, and a
  store that fell back to the local file is refused rather than "repaired".
  ``--local`` is the only way to aim it at a file, and only with no database.
* **A call is dropped only when the cache proves it was never stored**: it
  matches no stored snapshot (timestamps compared as instants, whatever their
  spelling) and is newer than the race's oldest kept snapshot. Older unmatched
  calls, races the cache keeps nothing for and unreadable timestamps are kept.
  A drop that would change a graded call refuses the whole run.
* **A dry run writes nothing** and lists every race whose graded call changes,
  every call it drops and every unmatched call it keeps, each with its reason.
* **Nothing is written before both documents are backed up**, nor when either
  changed after it was read. Only the history is written; a failed write names
  its backup.

The fixture is production's R19 and R20 history entries from the 2026-11-11
backup. The cache beside them is built from their timestamps: every R19 call
stored, and R20 without the two calls P0b.9 found missing from production's
cache (11-07 23:44:33 and 11-11 01:34:47).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.data.predictions.graded import graded_call, with_graded_fields
from app.data.predictions.phases import SNAPSHOT_HISTORY_LIMIT
from app.data.store import BACKEND_FILE, BACKEND_POSTGRES
from app.data.store_types import ReadResult, StoreHealth, WriteResult
from scripts import repair_graded_predictions as repair

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
HISTORY = "prediction_history"
CACHE = "prediction_cache"

R20_NEVER_STORED = ("2026-11-07T23:44:33.875453+00:00", "2026-11-11T01:34:47.136982+00:00")

# Timestamps for a race shaped like production's R17: two pre-qualifying calls
# stored, a later pre-qualifying call that never was (LATE), then the stored
# post-qualifying call (POST). OLD predates them all.
OLD = "2026-10-01T12:00:00+00:00"
FIRST = "2026-10-04T21:30:44.724802+00:00"
SECOND = "2026-10-05T05:31:55.276997+00:00"
LATE = "2026-10-10T17:42:35.526863+00:00"
POST = "2026-10-10T18:05:12.726366+00:00"


def _entry(edition: str) -> dict:
    return json.loads((FIXTURES / edition / "prediction_history_entry.json").read_text(encoding="utf-8"))["entry"]


def _history() -> dict:
    return {"(2026,19)": _entry("mexico_2026_r19"), "(2026,20)": _entry("sao_paulo_2026_r20")}


def _stamps(edition: str) -> list[str]:
    return [call["generated_at"] for call in _entry(edition)["snapshots"]]


def _cache_entry(*stamps: object) -> dict:
    """A cache entry keeping one snapshot per ``generated_at``, oldest stored first."""
    return {
        "schema_version": 2,
        "snapshots": [
            {"id": f"v{number}", "stored_at": "s", "reason": "manual_compute", "result": {"generated_at": stamp}}
            for number, stamp in enumerate(stamps, start=1)
        ],
    }


def _cache(entries: dict) -> dict:
    return {"schema_version": 2, "entries": entries}


def _production_cache() -> dict:
    r20 = [stamp for stamp in _stamps("sao_paulo_2026_r20") if stamp not in R20_NEVER_STORED]
    return _cache({"2026:19": _cache_entry(*_stamps("mexico_2026_r19")), "2026:20": _cache_entry(*r20)})


def _call(stamp: object, phase: str = "pre_qualifying", ver: int = 1) -> dict:
    return {
        "generated_at": stamp,
        "prediction_phase": phase,
        "data_sources": [],
        "predicted_positions": {"VER": ver},
        "risk_predictions": {},
    }


def _race(*calls: dict) -> dict:
    """A history entry holding ``calls``, its top-level fields already its graded call's."""
    return with_graded_fields({"snapshots": list(calls)})


def _r17_shaped() -> dict:
    return {"(2026,17)": _race(_call(FIRST), _call(SECOND), _call(LATE), _call(POST, "post_qualifying"))}


class _FakeStore:
    """The history and cache documents, scripted per test; ``reads`` serves successive reads of each."""

    def __init__(self, backend: str, history: dict | None, cache: dict | None = None) -> None:
        self.backend = backend
        self.reads: dict[str, list[ReadResult]] = {
            HISTORY: [ReadResult(payload=history)],
            CACHE: [ReadResult(payload=cache)],
        }
        self.writes: list[dict] = []
        self.write_ok = True

    def health(self) -> StoreHealth:
        return StoreHealth(backend=self.backend, host_kind="supabase_pooler")

    def read(self, name: str) -> ReadResult:
        queue = self.reads[name]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def write(self, name: str, payload: dict) -> WriteResult:
        assert name == HISTORY, "the repair writes only the history document"
        self.writes.append(payload)
        if not self.write_ok:
            return WriteResult(ok=False, durable=False, error="connection reset")
        return WriteResult()


@pytest.fixture
def production(monkeypatch) -> _FakeStore:
    """A Postgres store aimed at by DATABASE_URL, holding the R19 and R20 entries and their cache."""
    store = _FakeStore(BACKEND_POSTGRES, _history(), _production_cache())
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    return store


def _script(store: _FakeStore, history: dict, cache: dict | None) -> None:
    store.reads = {HISTORY: [ReadResult(payload=history)], CACHE: [ReadResult(payload=cache)]}


def _run(*args: str, backup_dir: Path | None = None) -> int:
    extra = ["--backup-dir", str(backup_dir)] if backup_dir is not None else []
    return repair.main([*args, *extra])


# ---------------------------------------------------------------------------
# Planning the graded call
# ---------------------------------------------------------------------------


def test_the_plan_changes_r20_and_leaves_r19_alone():
    history = _history()

    result = repair.plan(history, _production_cache())

    assert [change.key for change in result.changes] == ["(2026,20)"]
    [r20] = result.changes
    assert (r20.before["prediction_phase"], r20.after["prediction_phase"]) == ("pre_qualifying", "post_qualifying")
    assert result.repaired["(2026,20)"]["predicted_positions"]["VER"] == 8
    assert result.repaired["(2026,19)"] == history["(2026,19)"]
    assert history == _history(), "the document handed in is never mutated"


def test_races_are_listed_in_calendar_order_and_odd_keys_last():
    def stale(ver: int) -> dict:
        return {
            "predicted_positions": {"VER": 1},
            "snapshots": [{"prediction_phase": "post_qualifying", "predicted_positions": {"VER": ver}}],
        }

    history = {"bogus": stale(4), "(2026,10)": stale(3), "(2025,24)": stale(2), "(2026,9)": stale(5)}

    result = repair.plan(history, None)

    assert [change.key for change in result.changes] == ["(2025,24)", "(2026,9)", "(2026,10)", "bogus"]
    assert [key for key, _ in result.uncached] == ["(2025,24)", "(2026,9)", "(2026,10)", "bogus"]


def test_an_entry_that_is_not_a_record_is_carried_over_untouched():
    result = repair.plan({"(2026,1)": "corrupt"}, None)

    assert result.repaired == {"(2026,1)": "corrupt"}
    assert (result.changes, result.dropped, result.kept, result.uncached) == ([], [], [], [])


def test_a_change_names_the_drivers_that_move_and_how_many():
    [r20] = repair.plan(_history(), _production_cache()).changes

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
# Planning the drops: which calls the cache proves were never stored
# ---------------------------------------------------------------------------


def test_the_plan_drops_r20s_two_never_stored_calls_and_keeps_its_graded_call():
    history = _history()

    result = repair.plan(history, _production_cache())

    assert [(item.key, item.call["generated_at"]) for item in result.dropped] == [
        ("(2026,20)", stamp) for stamp in R20_NEVER_STORED
    ]
    assert {item.reason for item in result.dropped} == {
        "newer than the oldest kept snapshot (2026-11-01T23:39:20.767132+00:00) and matches none of the 6 stored"
    }
    r20 = result.repaired["(2026,20)"]
    assert [call["generated_at"] for call in r20["snapshots"]] == [
        stamp for stamp in _stamps("sao_paulo_2026_r20") if stamp not in R20_NEVER_STORED
    ]
    assert graded_call(r20) == graded_call(history["(2026,20)"])
    assert (r20["prediction_phase"], r20["generated_at"]) == ("post_qualifying", "2026-11-08T00:45:43.688379+00:00")
    assert (result.kept, result.refused, result.uncached) == ([], [], [])


def test_a_second_plan_on_the_repaired_history_finds_nothing():
    cache = _production_cache()
    first = repair.plan(_history(), cache)

    second = repair.plan(first.repaired, cache)

    assert (second.changes, second.dropped, second.kept, second.refused) == ([], [], [], [])
    assert second.repaired == first.repaired


def test_a_newer_call_that_matches_no_stored_snapshot_is_dropped():
    history = _r17_shaped()

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, POST)}))

    [dropped] = result.dropped
    assert (dropped.key, dropped.call["generated_at"]) == ("(2026,17)", LATE)
    assert dropped.reason == f"newer than the oldest kept snapshot ({FIRST}) and matches none of the 3 stored"
    assert [call["generated_at"] for call in result.repaired["(2026,17)"]["snapshots"]] == [FIRST, SECOND, POST]
    assert result.repaired["(2026,17)"]["generated_at"] == POST
    assert (result.changes, result.kept, result.refused) == ([], [], [])


def test_an_older_unmatched_call_is_kept_because_it_may_have_been_trimmed():
    history = {"(2026,17)": _race(_call(OLD), _call(FIRST), _call(POST, "post_qualifying"))}

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, POST)}))

    [kept] = result.kept
    assert (kept.key, kept.call["generated_at"]) == ("(2026,17)", OLD)
    assert kept.reason == f"predates the oldest kept snapshot ({FIRST}); it may have been shown and trimmed since"
    assert result.dropped == []
    assert result.repaired == history


def test_calls_that_match_stored_snapshots_are_kept_and_not_listed():
    history = _r17_shaped()

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, LATE, POST)}))

    assert (result.dropped, result.kept, result.uncached) == ([], [], [])
    assert result.repaired == history


@pytest.mark.parametrize(
    "stored",
    [
        "2026-10-10T17:42:35.526863Z",
        "2026-10-10T17:42:35.526863",
        "2026-10-10T10:42:35.526863-07:00",
        "2026-10-10 17:42:35.526863+00:00",
    ],
    ids=["zulu", "naive-utc", "other-offset", "space-separator"],
)
def test_a_stored_snapshot_matches_its_call_whatever_the_timestamp_spelling(stored):
    history = _r17_shaped()

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, stored, POST)}))

    assert (result.dropped, result.kept) == ([], [])


def test_a_stamp_one_microsecond_apart_is_a_different_call():
    history = _r17_shaped()

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, "2026-10-10T17:42:35.526864Z", POST)}))

    assert [item.call["generated_at"] for item in result.dropped] == [LATE]


def test_the_oldest_kept_snapshot_is_read_from_the_cache_window_not_a_pinned_call():
    """A newest-of-its-phase call kept from before the trim window says nothing about what was trimmed after it."""
    pinned = "2026-09-01T00:00:00+00:00"
    trimmed = "2026-09-02T00:00:00+00:00"
    window = [f"2026-09-{day:02d}T00:00:00+00:00" for day in range(3, 3 + SNAPSHOT_HISTORY_LIMIT)]
    history = {"(2026,5)": _race(_call(pinned, "post_qualifying"), _call(trimmed), *(_call(stamp) for stamp in window))}

    result = repair.plan(history, _cache({"2026:5": _cache_entry(pinned, *window)}))

    assert result.dropped == []
    [kept] = result.kept
    assert kept.call["generated_at"] == trimmed
    assert kept.reason.startswith(f"predates the oldest kept snapshot ({window[0]})")


@pytest.mark.parametrize(
    "cache",
    [
        None,
        _cache({}),
        _cache({"2026:3": {"schema_version": 2, "snapshots": []}}),
        _cache({"2026:3": {"schema_version": 2, "snapshots": ["junk", {"result": "junk"}]}}),
        _cache({"2026:3": "corrupt"}),
        {"schema_version": 2},
        ["not", "a", "document"],
    ],
    ids=[
        "no-document",
        "no-entries",
        "no-snapshots",
        "junk-snapshots",
        "junk-entry",
        "no-entries-key",
        "junk-document",
    ],
)
def test_a_race_the_cache_keeps_nothing_for_keeps_every_call_and_is_reported(cache):
    history = {"(2026,3)": _race(_call(FIRST), _call(LATE)), "(2026,4)": {"predicted_positions": {"VER": 1}}}

    result = repair.plan(history, cache)

    assert result.uncached == [("(2026,3)", 2)], "a race with no calls has nothing to report"
    assert (result.dropped, result.kept) == ([], [])
    assert result.repaired == history


def test_a_call_whose_generated_at_cannot_be_read_is_kept():
    history = {"(2026,3)": _race(_call(FIRST), _call("not a time"), _call(None), _call(POST, "post_qualifying"))}

    result = repair.plan(history, _cache({"2026:3": _cache_entry(FIRST, POST)}))

    assert [item.reason for item in result.kept] == [repair.UNREADABLE_CALL, repair.UNREADABLE_CALL]
    assert result.dropped == []


def test_a_stored_snapshot_with_an_unreadable_generated_at_keeps_every_unmatched_call():
    history = _r17_shaped()

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, None, POST)}))

    [kept] = result.kept
    assert (kept.call["generated_at"], kept.reason) == (LATE, repair.UNREADABLE_STORED)
    assert result.dropped == []


def test_a_history_item_that_is_not_a_call_is_carried_over():
    history = {"(2026,17)": {**_r17_shaped()["(2026,17)"]}}
    history["(2026,17)"]["snapshots"] = ["junk", *history["(2026,17)"]["snapshots"]]

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND, POST)}))

    assert [item.call["generated_at"] for item in result.dropped] == [LATE]
    assert result.repaired["(2026,17)"]["snapshots"][0] == "junk"


def test_a_drop_that_would_change_the_graded_call_is_refused():
    late_post = "2026-10-10T18:05:12.726366+00:00"
    history = {
        "(2026,17)": _race(_call(FIRST), _call(SECOND, "post_qualifying", 2), _call(late_post, "post_qualifying", 3))
    }

    result = repair.plan(history, _cache({"2026:17": _cache_entry(FIRST, SECOND)}))

    [refused] = result.refused
    assert (refused.key, refused.call["generated_at"]) == ("(2026,17)", late_post)
    assert refused.reason == (
        f"never stored, but dropping it changes the race's graded call (post_qualifying {late_post})"
    )
    assert result.dropped == []
    assert result.repaired == history, "the race keeps every call"


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
    store = _FakeStore(BACKEND_FILE, _history(), _production_cache())
    monkeypatch.setattr(repair, "document_store", store)
    monkeypatch.setenv("DATABASE_URL", "  ")

    assert _run("--local", "--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "store: file" in capsys.readouterr().out
    assert store.writes[0]["(2026,20)"]["prediction_phase"] == "post_qualifying"


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_a_dry_run_lists_r20s_change_and_drops_and_writes_nothing(production, tmp_path, capsys):
    assert _run(backup_dir=tmp_path) == repair.EXIT_OK

    out = capsys.readouterr().out
    assert "store: postgres (supabase_pooler)" in out
    assert "1 of 2 race(s) change their graded call" in out
    assert "R20 (2026,20)  pre_qualifying" in out
    assert "2 call(s) never reached the snapshot cache and are dropped:" in out
    for stamp in R20_NEVER_STORED:
        assert f"  R20 (2026,20)  pre_qualifying {stamp}  newer than the oldest kept snapshot" in out
    assert "R19" not in out
    assert "dry run" in out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == [], "a dry run makes no backup either"


def test_a_dry_run_lists_the_unmatched_calls_it_keeps_and_the_races_the_cache_lacks(production, tmp_path, capsys):
    history = {
        "(2026,1)": _race(_call(OLD), _call(FIRST), _call(POST, "post_qualifying")),
        "(2026,2)": _race(_call(FIRST)),
    }
    _script(production, history, _cache({"2026:1": _cache_entry(FIRST, POST)}))

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK

    out = capsys.readouterr().out
    assert "1 call(s) match no stored snapshot but are kept:" in out
    assert f"  R1 (2026,1)  pre_qualifying {OLD}  predates the oldest kept snapshot ({FIRST})" in out
    assert "1 race(s) have no snapshot in the cache, so every call is kept:" in out
    assert "  R2 (2026,2)  1 call(s)" in out
    assert "nothing to repair" in out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == []


def test_a_history_with_nothing_to_repair_writes_nothing(production, tmp_path, capsys):
    _script(production, {"(2026,19)": _entry("mexico_2026_r19")}, _production_cache())

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "nothing to repair" in capsys.readouterr().out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == []


def test_an_empty_store_has_nothing_to_repair(production, tmp_path, capsys):
    production.reads[HISTORY] = [ReadResult(payload=None)]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK
    assert "no prediction history" in capsys.readouterr().out
    assert production.writes == []


def test_an_unreadable_history_stops_the_run(production, capsys):
    production.reads[HISTORY] = [ReadResult(ok=False, error="timeout expired")]

    assert _run("--apply") == repair.EXIT_STORE_ERROR
    assert "timeout expired" in capsys.readouterr().out
    assert production.writes == []


def test_an_unreadable_cache_stops_the_run(production, tmp_path, capsys):
    production.reads[CACHE] = [ReadResult(ok=False, error="cache timeout")]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert "cache timeout" in capsys.readouterr().out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == []


def test_a_run_whose_drops_would_change_a_graded_call_is_refused(production, tmp_path, capsys):
    history = {"(2026,17)": _race(_call(FIRST), _call(POST, "post_qualifying"))}
    _script(production, history, _cache({"2026:17": _cache_entry(FIRST)}))

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_GRADED_CALL_WOULD_CHANGE

    out = capsys.readouterr().out
    assert "1 call(s) never reached the snapshot cache, but dropping them changes a graded call:" in out
    assert f"  R17 (2026,17)  post_qualifying {POST}  never stored, but dropping it" in out
    assert "REFUSED" in out
    assert production.writes == []
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def test_apply_backs_up_both_documents_then_writes_only_the_history(production, tmp_path, capsys):
    original, cache = _history(), _production_cache()

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_OK

    cache_backup, history_backup = sorted(tmp_path.iterdir())
    assert cache_backup.name.startswith("prediction_cache-")
    assert json.loads(cache_backup.read_text(encoding="utf-8")) == cache
    assert history_backup.name.startswith("prediction_history-")
    assert json.loads(history_backup.read_text(encoding="utf-8")) == original
    [written] = production.writes
    r20 = written["(2026,20)"]
    assert (r20["prediction_phase"], r20["predicted_positions"]["VER"]) == ("post_qualifying", 8)
    assert len(r20["snapshots"]) == 6
    assert written["(2026,19)"] == original["(2026,19)"]
    assert (
        f"repaired 1 race(s) and dropped 2 call(s); backups: {history_backup}, {cache_backup}"
        in capsys.readouterr().out
    )


def test_a_second_run_after_apply_finds_nothing_to_repair(production, tmp_path, capsys):
    assert _run("--apply", backup_dir=tmp_path / "first") == repair.EXIT_OK
    production.reads[HISTORY] = [ReadResult(payload=production.writes[0])]

    assert _run("--apply", backup_dir=tmp_path / "second") == repair.EXIT_OK

    assert "nothing to repair" in capsys.readouterr().out
    assert len(production.writes) == 1


def test_a_failed_backup_writes_nothing(production, tmp_path, capsys):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")

    assert _run("--apply", backup_dir=blocked) == repair.EXIT_STORE_ERROR
    assert "backup failed" in capsys.readouterr().out
    assert production.writes == []


def test_a_history_that_changed_after_it_was_read_is_not_overwritten(production, tmp_path, capsys):
    newer = copy.deepcopy(_history())
    newer["(2026,21)"] = {"predicted_positions": {"VER": 2}}
    production.reads[HISTORY] = [ReadResult(payload=_history()), ReadResult(payload=newer)]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert "prediction_history changed while" in capsys.readouterr().out
    assert production.writes == []


def test_a_cache_that_changed_after_it_was_read_is_not_trusted(production, tmp_path, capsys):
    newer = _production_cache()
    newer["entries"]["2026:20"] = _cache_entry(*_stamps("sao_paulo_2026_r20"))
    production.reads[CACHE] = [ReadResult(payload=_production_cache()), ReadResult(payload=newer)]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert "prediction_cache changed while" in capsys.readouterr().out
    assert production.writes == []


def test_a_history_that_cannot_be_read_again_is_not_overwritten(production, tmp_path):
    production.reads[HISTORY] = [ReadResult(payload=_history()), ReadResult(ok=False, error="gone")]

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_STORE_ERROR
    assert production.writes == []


def test_a_failed_write_names_the_backup(production, tmp_path, capsys):
    production.write_ok = False

    assert _run("--apply", backup_dir=tmp_path) == repair.EXIT_WRITE_FAILED

    out = capsys.readouterr().out
    history_backup = next(path for path in tmp_path.iterdir() if path.name.startswith("prediction_history-"))
    assert "connection reset" in out
    assert str(history_backup) in out
