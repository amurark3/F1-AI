"""Tests for the post-race prediction review (app.data.predictions).

The behaviour under test: a stored prediction is compared driver by driver
against the recorded result, and a snapshot frozen before the race is scored
once the result exists rather than staying "not available yet" forever.
"""

import pytest

from app.data import predictions as predictions_module
from app.data.predictions import build_prediction_review
from app.services.predictions import enrich_prediction_result

YEAR = 2026
ROUND = 11
KEY = f"({YEAR},{ROUND})"

# One race: the model called HAM to win, HAM crashed out to P11, NOR won, and
# ALO raced without being in the snapshot (a substitute drive).
PREDICTED = {"HAM": 1, "NOR": 2, "VER": 3, "PIA": 4}
ACTUAL = {"NOR": 1, "VER": 2, "ALO": 3, "HAM": 11}

HISTORY = {
    KEY: {
        "predicted_positions": PREDICTED,
        "generated_at": "2026-07-25T12:00:00+00:00",
        "prediction_phase": "post_qualifying",
        "actual_positions": ACTUAL,
        "actual_statuses": {"HAM": "Accident", "NOR": "Finished"},
        "actual_incidents": {"HAM": {"dnf": True, "crash": True}},
        "risk_predictions": {"HAM": {"dnf_risk_pct": 18, "crash_risk_pct": 12}},
        "snapshots": [
            {
                "generated_at": "2026-07-25T12:00:00+00:00",
                "prediction_phase": "post_qualifying",
                "predicted_positions": PREDICTED,
                "risk_predictions": {"HAM": {"dnf_risk_pct": 18, "crash_risk_pct": 12}},
            }
        ],
    }
}


@pytest.fixture
def stored_history(monkeypatch):
    """Serve a fixed prediction history without touching the document store."""
    monkeypatch.setattr(predictions_module, "_load_prediction_history", lambda: HISTORY)
    return HISTORY


def _row(review: dict, code: str) -> dict:
    return next(row for row in review["driver_results"] if row["driver_code"] == code)


def test_review_reports_every_driver_side_by_side(stored_history):
    review = build_prediction_review(YEAR, ROUND)

    assert review["evaluated"] is True
    rows = review["driver_results"]
    assert [row["driver_code"] for row in rows] == ["NOR", "VER", "ALO", "HAM", "PIA"]
    assert _row(review, "NOR")["predicted_position"] == 2
    assert _row(review, "NOR")["actual_position"] == 1
    assert _row(review, "NOR")["position_delta"] == -1


def test_review_marks_exact_hits_and_misses(stored_history):
    review = build_prediction_review(YEAR, ROUND)

    assert _row(review, "HAM")["position_delta"] == 10
    assert _row(review, "HAM")["exact"] is False
    assert _row(review, "HAM")["dnf"] is True
    assert _row(review, "HAM")["crash"] is True
    assert _row(review, "HAM")["status"] == "Accident"
    assert review["winner_correct"] is False
    assert review["predicted_winner"] == "HAM"
    assert review["actual_winner"] == "NOR"


def test_review_keeps_drivers_present_on_only_one_side(stored_history):
    review = build_prediction_review(YEAR, ROUND)

    # Raced but was not predicted, and predicted but did not race: both stay
    # visible with a null on the missing side rather than being dropped.
    assert _row(review, "ALO")["predicted_position"] is None
    assert _row(review, "ALO")["actual_position"] == 3
    assert _row(review, "PIA")["actual_position"] is None
    assert _row(review, "PIA")["position_delta"] is None
    assert _row(review, "PIA")["exact"] is False


def test_review_without_a_result_is_not_evaluated(monkeypatch):
    monkeypatch.setattr(
        predictions_module,
        "_load_prediction_history",
        lambda: {KEY: {**HISTORY[KEY], "actual_positions": {}}},
    )

    review = build_prediction_review(YEAR, ROUND)

    assert review["evaluated"] is False
    assert "not available yet" in review["reason"]


def test_enrich_rescores_a_snapshot_frozen_before_the_race(stored_history):
    # What a snapshot computed before lights out stores forever.
    stale = {
        "year": YEAR,
        "round": ROUND,
        "predictions": [{"driver_code": "HAM", "driver_name": "Lewis Hamilton", "team": "Ferrari", "position": 1}],
        "prediction_review": {"evaluated": False, "reason": "Actual race result is not available yet."},
    }

    enriched = enrich_prediction_result(stale)

    assert enriched["prediction_review"]["evaluated"] is True
    assert enriched["prediction_review"]["actual_winner"] == "NOR"
    assert stale["prediction_review"]["evaluated"] is False  # input untouched


def test_enrich_keeps_an_already_scored_review(stored_history):
    scored = {
        "year": YEAR,
        "round": ROUND,
        "predictions": [{"driver_code": "HAM", "driver_name": "Lewis Hamilton", "team": "Ferrari", "position": 1}],
        "prediction_review": {"evaluated": True, "actual_winner": "SAI"},
    }

    enriched = enrich_prediction_result(scored)

    assert enriched["prediction_review"]["actual_winner"] == "SAI"
