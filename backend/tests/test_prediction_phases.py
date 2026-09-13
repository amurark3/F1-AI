"""Tests for the two prediction phases a race can hold.

A race is predicted twice: once from form and history alone, and again once
qualifying has set the grid. The behaviour under test is that the two calls are
stored, read, scored and recomputed independently — recomputing one tab must
never disturb, evict or mis-score the other.
"""

import pytest

from app.data import predictions as predictions_module
from app.data.predictions import (
    PHASE_POST_QUALIFYING,
    PHASE_PRE_QUALIFYING,
    build_prediction_review,
    get_accuracy_stats,
    normalise_phase,
    should_use_qualifying,
    trim_snapshots,
)

pytestmark = pytest.mark.unit

YEAR = 2026
ROUND = 9
KEY = f"({YEAR},{ROUND})"

# The grid told the model something: without it VER was picked to win, with it
# NOR was. NOR actually won, so only the post-qualifying call was right.
PRE_QUALI_POSITIONS = {"VER": 1, "NOR": 2, "PIA": 3}
POST_QUALI_POSITIONS = {"NOR": 1, "VER": 2, "PIA": 3}
ACTUAL_POSITIONS = {"NOR": 1, "VER": 2, "PIA": 3}


def _history_snapshot(phase: str, positions: dict) -> dict:
    return {
        "generated_at": "2026-05-03T10:00:00+00:00",
        "prediction_phase": phase,
        "data_sources": [],
        "predicted_positions": positions,
        "risk_predictions": {},
    }


def _history(*snapshots: dict) -> dict:
    return {
        KEY: {
            "predicted_positions": snapshots[-1]["predicted_positions"],
            "prediction_phase": snapshots[-1]["prediction_phase"],
            "generated_at": snapshots[-1]["generated_at"],
            "actual_positions": ACTUAL_POSITIONS,
            "actual_statuses": {},
            "actual_incidents": {},
            "risk_predictions": {},
            "snapshots": list(snapshots),
        }
    }


@pytest.fixture
def both_phases_stored(monkeypatch):
    """History holding both calls, with the pre-qualifying one written last."""
    history = _history(
        _history_snapshot(PHASE_POST_QUALIFYING, POST_QUALI_POSITIONS),
        _history_snapshot(PHASE_PRE_QUALIFYING, PRE_QUALI_POSITIONS),
    )
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)
    return history


# ---------------------------------------------------------------------------
# Phase parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase", [PHASE_PRE_QUALIFYING, PHASE_POST_QUALIFYING])
def test_a_known_phase_survives_normalisation(phase):
    assert normalise_phase(phase) == phase


@pytest.mark.parametrize("value", [None, "", "during_qualifying", "PRE_QUALIFYING"])
def test_an_unknown_phase_means_let_the_data_decide(value):
    assert normalise_phase(value) is None


# ---------------------------------------------------------------------------
# Forcing the pre-qualifying phase
# ---------------------------------------------------------------------------

def test_a_forced_pre_qualifying_call_ignores_a_qualifying_result_that_exists(monkeypatch):
    monkeypatch.setattr(predictions_module, "_qualifying_has_occurred", lambda row: True)

    assert should_use_qualifying(object(), forced_pre_qualifying=True) is False


def test_an_unforced_call_still_uses_qualifying_once_it_has_run(monkeypatch):
    monkeypatch.setattr(predictions_module, "_qualifying_has_occurred", lambda row: True)

    assert should_use_qualifying(object(), forced_pre_qualifying=False) is True


def test_an_unforced_call_skips_qualifying_before_the_session(monkeypatch):
    monkeypatch.setattr(predictions_module, "_qualifying_has_occurred", lambda row: False)

    assert should_use_qualifying(object(), forced_pre_qualifying=False) is False


def test_an_unknown_schedule_attempts_the_qualifying_load():
    assert should_use_qualifying(None, forced_pre_qualifying=False) is True


def test_a_deliberately_excluded_grid_is_not_reported_as_missing_data():
    forced = predictions_module._pre_qualifying_warning(True, "practice")
    unavailable = predictions_module._pre_qualifying_warning(False, "practice")

    assert "deliberately excluded" in forced
    assert "unavailable" in unavailable


def test_a_forced_call_with_no_session_data_says_why_it_has_none():
    assert "deliberately excluded" in predictions_module._pre_qualifying_warning(True, "history")
    assert "No qualifying or practice data" in predictions_module._pre_qualifying_warning(False, "history")


# ---------------------------------------------------------------------------
# Per-phase review scoring
# ---------------------------------------------------------------------------

def test_each_phase_is_scored_against_its_own_call(both_phases_stored):
    pre = build_prediction_review(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)
    post = build_prediction_review(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)

    assert pre["predicted_winner"] == "VER"
    assert pre["winner_correct"] is False
    assert post["predicted_winner"] == "NOR"
    assert post["winner_correct"] is True


def test_a_phase_that_was_never_computed_is_not_scored_from_the_other_one(monkeypatch):
    history = _history(_history_snapshot(PHASE_PRE_QUALIFYING, PRE_QUALI_POSITIONS))
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)

    review = build_prediction_review(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)

    assert review["evaluated"] is False
    assert review["reason"] == "No stored post-qualifying prediction for this race."


def test_a_missing_pre_qualifying_call_names_its_own_phase(monkeypatch):
    history = _history(_history_snapshot(PHASE_POST_QUALIFYING, POST_QUALI_POSITIONS))
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)

    review = build_prediction_review(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)

    assert review["reason"] == "No stored pre-qualifying prediction for this race."


def test_asking_for_no_phase_scores_the_most_recent_call(both_phases_stored):
    review = build_prediction_review(YEAR, ROUND)

    assert review["predicted_winner"] == "VER"


def test_a_legacy_entry_without_a_snapshot_list_is_still_scored_by_phase(monkeypatch):
    history = {
        KEY: {
            "predicted_positions": POST_QUALI_POSITIONS,
            "prediction_phase": PHASE_POST_QUALIFYING,
            "generated_at": "2026-05-03T10:00:00+00:00",
            "actual_positions": ACTUAL_POSITIONS,
            "actual_incidents": {},
        }
    }
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)

    assert build_prediction_review(YEAR, ROUND, phase=PHASE_POST_QUALIFYING)["evaluated"] is True
    assert build_prediction_review(YEAR, ROUND, phase=PHASE_PRE_QUALIFYING)["evaluated"] is False


# ---------------------------------------------------------------------------
# Rolling accuracy
# ---------------------------------------------------------------------------

def test_rolling_accuracy_scores_the_post_qualifying_call_whichever_was_stored_last(
    both_phases_stored,
):
    # The pre-qualifying call was written last and got the winner wrong. Rolling
    # accuracy must not drop because a user refreshed that tab.
    stats = get_accuracy_stats()

    assert stats["races_evaluated"] == 1
    assert stats["recent_winner_pct"] == 100.0


def test_rolling_accuracy_falls_back_to_whatever_phase_exists(monkeypatch):
    history = _history(_history_snapshot(PHASE_PRE_QUALIFYING, PRE_QUALI_POSITIONS))
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: history)

    stats = get_accuracy_stats()

    assert stats["races_evaluated"] == 1
    assert stats["recent_winner_pct"] == 0.0


# ---------------------------------------------------------------------------
# Snapshot retention
# ---------------------------------------------------------------------------

def test_a_short_snapshot_list_is_kept_whole():
    snapshots = [{"prediction_phase": PHASE_PRE_QUALIFYING} for _ in range(3)]

    assert trim_snapshots(snapshots, limit=8) == snapshots


def test_trimming_never_evicts_the_only_call_of_a_phase():
    lone_post_quali = {"prediction_phase": PHASE_POST_QUALIFYING, "id": "keep-me"}
    snapshots = [lone_post_quali] + [
        {"prediction_phase": PHASE_PRE_QUALIFYING, "id": f"pre-{index}"} for index in range(10)
    ]

    kept = trim_snapshots(snapshots, limit=4)

    assert lone_post_quali in kept
    assert [item["id"] for item in kept] == ["keep-me", "pre-6", "pre-7", "pre-8", "pre-9"]
