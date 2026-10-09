"""Tests for ``scripts.backfill_predictions`` — recomputing a season's calls.

The script writes predictions production serves, so the properties pinned are
about doing exactly the planned work and nothing more:

* **The plan matches what was live.** Every round up to the current race gets a
  pre-qualifying call, and a post-qualifying call only once qualifying has run
  — oldest first, so each race learns from the backfilled ones before it.
* **It resumes rather than repeats.** A phase that already holds a current
  snapshot is skipped unless ``--recompute`` asks for it.
* **Nothing is written before a backup exists**, and an unreachable store or a
  failed backup stops the run with a non-zero exit.
* **A call that did not land is a failure.** No predictions, or a write that is
  not durable, counts against the exit code.

FastF1, the snapshot cache, the document store and the compute are all faked
at the script's own module attributes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sys

import pandas as pd
import pytest

from app.data.predictions import PHASE_POST_QUALIFYING, PHASE_PRE_QUALIFYING
from app.data.store_types import ReadResult
from scripts import backfill_predictions as backfill

pytestmark = pytest.mark.unit

YEAR = 2026


def _naive(offset: timedelta) -> pd.Timestamp:
    return pd.Timestamp((datetime.now(timezone.utc) + offset).replace(tzinfo=None))


def _round(number: int, name: str, fp1: timedelta, quali: timedelta) -> dict:
    return {
        "RoundNumber": number,
        "EventName": name,
        "EventDate": _naive(quali + timedelta(days=1)),
        "Session1": "Practice 1",
        "Session1DateUtc": _naive(fp1),
        "Session4": "Qualifying",
        "Session4DateUtc": _naive(quali),
    }


def _season() -> pd.DataFrame:
    """Two completed weekends, one under way before qualifying, one ahead."""
    return pd.DataFrame(
        [
            _round(4, "Future GP", fp1=timedelta(days=20), quali=timedelta(days=21)),
            _round(1, "Opening GP", fp1=timedelta(days=-30), quali=timedelta(days=-29)),
            _round(3, "Current GP", fp1=timedelta(hours=-3), quali=timedelta(hours=20)),
            _round(2, "Second GP", fp1=timedelta(days=-15), quali=timedelta(days=-14)),
        ]
    )


class _Cache:
    def __init__(self, loaded: bool = True, existing: set[tuple[int, str]] | None = None) -> None:
        self.loaded = loaded
        self.existing = existing or set()

    def load(self) -> bool:
        return self.loaded

    def get(self, year: int, round_num: int, phase: str | None = None) -> dict | None:
        return {"predictions": [1]} if (round_num, phase) in self.existing else None


class _Store:
    def __init__(self, readable: bool = True) -> None:
        self.readable = readable

    def read(self, name: str) -> ReadResult:
        if not self.readable:
            return ReadResult(ok=False, error="connection refused")
        return ReadResult(payload={"document": name})


def _stored(code: str = "VER", *, sources=("qualifying", "trained_ml_model"), durable: bool = True) -> dict:
    return {
        "predictions": [{"driver_code": code}, {"driver_code": "NOR"}],
        "data_sources": list(sources),
        "cache": {"durable": durable},
    }


@pytest.fixture
def season(monkeypatch):
    monkeypatch.setattr(backfill.fastf1, "get_event_schedule", lambda year, include_testing: _season())


@pytest.fixture
def cache(monkeypatch) -> _Cache:
    fake = _Cache()
    monkeypatch.setattr(backfill, "prediction_snapshot_cache", fake)
    return fake


@pytest.fixture
def computed(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    def _compute(year, round_num, *, reason, phase):
        calls.append((year, round_num, reason, phase))
        return _stored()

    monkeypatch.setattr(backfill, "compute_and_store_race_prediction", _compute)
    return calls


def _plan_shape(calls: list[backfill.PlannedCall]) -> list[tuple[int, str]]:
    return [(call.round_num, call.phase) for call in calls]


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


def test_the_first_session_is_the_earliest_dated_slot_in_utc():
    row = pd.Series(
        {
            "Session1DateUtc": pd.NaT,
            "Session2DateUtc": pd.Timestamp("2026-08-21 10:30"),
            "Session3DateUtc": pd.Timestamp("2026-08-22 14:00"),
        }
    )

    assert backfill._first_session(row) == datetime(2026, 8, 21, 10, 30, tzinfo=timezone.utc)


def test_an_aware_first_session_keeps_its_timezone():
    stamp = pd.Timestamp("2026-08-21 10:30", tz="UTC")

    assert backfill._first_session(pd.Series({"Session1DateUtc": stamp})) == stamp.to_pydatetime()


def test_an_undated_weekend_has_no_first_session():
    assert backfill._first_session(pd.Series({"EventName": "TBC"})) is None


def test_the_current_round_is_the_latest_weekend_that_has_started():
    assert backfill._current_round(_season()) == 3


def test_before_the_season_starts_there_is_no_current_round():
    future_only = pd.DataFrame([_round(1, "Opening GP", fp1=timedelta(days=5), quali=timedelta(days=6))])

    assert backfill._current_round(future_only) == 0


# ---------------------------------------------------------------------------
# _plan
# ---------------------------------------------------------------------------


def test_the_plan_runs_oldest_first_with_post_qualifying_only_once_it_has_run(season, cache):
    plan = backfill._plan(YEAR, None, recompute=False)

    assert _plan_shape(plan) == [
        (1, PHASE_PRE_QUALIFYING),
        (1, PHASE_POST_QUALIFYING),
        (2, PHASE_PRE_QUALIFYING),
        (2, PHASE_POST_QUALIFYING),
        (3, PHASE_PRE_QUALIFYING),
    ]
    assert plan[0].grand_prix == "Opening GP"


def test_the_plan_can_stop_at_an_earlier_round(season, cache):
    assert _plan_shape(backfill._plan(YEAR, 1, recompute=False)) == [
        (1, PHASE_PRE_QUALIFYING),
        (1, PHASE_POST_QUALIFYING),
    ]


def test_a_phase_with_a_current_snapshot_is_skipped_so_a_run_resumes(season, cache):
    cache.existing = {(1, PHASE_PRE_QUALIFYING), (1, PHASE_POST_QUALIFYING)}

    assert _plan_shape(backfill._plan(YEAR, 2, recompute=False)) == [
        (2, PHASE_PRE_QUALIFYING),
        (2, PHASE_POST_QUALIFYING),
    ]


def test_recompute_redoes_existing_phases_and_says_so(season, cache):
    cache.existing = {(1, PHASE_PRE_QUALIFYING)}

    plan = backfill._plan(YEAR, 1, recompute=True)

    assert [(call.phase, call.existing) for call in plan] == [
        (PHASE_PRE_QUALIFYING, True),
        (PHASE_POST_QUALIFYING, False),
    ]


# ---------------------------------------------------------------------------
# _backup
# ---------------------------------------------------------------------------


def test_the_backup_holds_both_prediction_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(backfill, "document_store", _Store())

    path = backfill._backup(tmp_path / "backups")

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert set(saved) == {backfill.DOCUMENT_PREDICTION_CACHE, backfill.DOCUMENT_PREDICTION_HISTORY}
    assert path.name.startswith("predictions-")


def test_an_unreadable_document_means_no_backup(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(backfill, "document_store", _Store(readable=False))

    assert backfill._backup(tmp_path / "backups") is None
    assert "ERROR reading" in capsys.readouterr().out
    assert not (tmp_path / "backups").exists()


# ---------------------------------------------------------------------------
# _describe and _run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "summary"),
    [
        (_stored(), "P1 VER, 2 drivers, grid from qualifying, model"),
        (_stored(sources=("practice",)), "P1 VER, 2 drivers, grid from practice, NO MODEL (heuristic only)"),
        (_stored(sources=()), "P1 VER, 2 drivers, grid from history, NO MODEL (heuristic only)"),
        (_stored(durable=False), "P1 VER, 2 drivers, grid from qualifying, model, NOT DURABLE"),
        ({"predictions": [], "error": "Qualifying has not run yet"}, "FAILED — Qualifying has not run yet"),
        ({}, "FAILED — no predictions"),
    ],
    ids=["qualifying", "practice", "history", "not-durable", "refused", "empty"],
)
def test_each_result_is_summarised_with_its_grid_and_model(result, summary):
    assert backfill._describe(result) == summary


def test_a_run_counts_every_call_that_did_not_land(monkeypatch, capsys):
    results = iter([_stored(), {"predictions": []}, _stored(durable=False)])
    seen: list[tuple] = []

    def _compute(year, round_num, *, reason, phase):
        seen.append((round_num, reason, phase))
        return next(results)

    monkeypatch.setattr(backfill, "compute_and_store_race_prediction", _compute)
    calls = [
        backfill.PlannedCall(1, "Opening GP", PHASE_PRE_QUALIFYING, existing=False),
        backfill.PlannedCall(1, "Opening GP", PHASE_POST_QUALIFYING, existing=False),
        backfill.PlannedCall(2, "Second GP", PHASE_PRE_QUALIFYING, existing=False),
    ]

    assert backfill._run(YEAR, calls) == 2
    assert seen == [
        (1, "backfill", PHASE_PRE_QUALIFYING),
        (1, "backfill", PHASE_POST_QUALIFYING),
        (2, "backfill", PHASE_PRE_QUALIFYING),
    ]
    assert "R 1 pre_qualifying" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


@pytest.fixture
def cli(monkeypatch, tmp_path, season, cache, computed):
    monkeypatch.setattr(backfill, "enable_fastf1_cache", lambda: None)
    monkeypatch.setattr(backfill, "document_store", _Store())

    def _main(*argv: str) -> int:
        monkeypatch.setattr(
            sys, "argv", ["backfill_predictions", "--year", str(YEAR), "--backup-dir", str(tmp_path), *argv]
        )
        return backfill.main()

    return _main


def test_an_unreachable_store_stops_before_planning(cli, cache, computed, capsys):
    cache.loaded = False

    assert cli("--apply") == 1
    assert "refusing to write" in capsys.readouterr().out
    assert computed == []


def test_a_dry_run_prints_the_plan_and_writes_nothing(cli, computed, tmp_path, capsys):
    assert cli() == 0

    out = capsys.readouterr().out
    assert "5 call(s) to compute" in out
    assert "dry run" in out
    assert computed == []
    assert list(tmp_path.iterdir()) == [], "no backup is taken for a dry run"


def test_a_recomputed_phase_is_flagged_in_the_plan(cli, cache, capsys):
    cache.existing = {(1, PHASE_PRE_QUALIFYING)}

    cli("--through-round", "1", "--recompute")

    assert "replaces a current-version snapshot" in capsys.readouterr().out


def test_nothing_to_do_exits_cleanly(cli, cache, computed):
    cache.existing = {(1, PHASE_PRE_QUALIFYING), (1, PHASE_POST_QUALIFYING)}

    assert cli("--apply", "--through-round", "1") == 0
    assert computed == []


def test_apply_backs_up_then_computes_every_planned_call(cli, computed, tmp_path, capsys):
    assert cli("--apply") == 0

    assert len(list(tmp_path.glob("predictions-*.json"))) == 1
    assert [(rnd, phase) for _, rnd, _, phase in computed] == [
        (1, PHASE_PRE_QUALIFYING),
        (1, PHASE_POST_QUALIFYING),
        (2, PHASE_PRE_QUALIFYING),
        (2, PHASE_POST_QUALIFYING),
        (3, PHASE_PRE_QUALIFYING),
    ]
    assert "done. 5/5 stored." in capsys.readouterr().out


def test_a_failed_backup_stops_before_any_write(cli, monkeypatch, computed):
    monkeypatch.setattr(backfill, "document_store", _Store(readable=False))

    assert cli("--apply") == 1
    assert computed == []


def test_a_call_that_did_not_land_fails_the_run(cli, monkeypatch):
    monkeypatch.setattr(backfill, "compute_and_store_race_prediction", lambda *_a, **_k: {"predictions": []})

    assert cli("--apply", "--through-round", "1") == 1
