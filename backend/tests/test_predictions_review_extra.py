"""Refusal paths of the post-race review (app.data.predictions.review).

``tests/test_prediction_review.py`` pins the happy path — a stored snapshot
scored against a recorded result. This file covers the other half: every reason
the review declines to grade itself, plus the legacy record shape it still has
to read.

The risk is a review that reports a *number* when it has nothing to compare.
``evaluated: False`` with a stated reason is a load-bearing contract — the UI
renders the reason instead of a fabricated 0% accuracy — so each refusal must
name the specific thing that was missing (no snapshot / no order / no result /
no shared drivers) rather than collapsing into one generic failure.

``_latest_prediction_snapshot`` also has to read records written before
snapshots existed, where the prediction sat at the top level of the entry.
Losing those would silently shrink both the review and the adaptive-learning
window that reads the same document.
"""

from __future__ import annotations

import pytest

from app.data.predictions import review as review_module
from app.data.predictions.review import (
    _latest_prediction_snapshot,
    build_prediction_review,
    get_prediction_review,
)

YEAR = 2026
ROUND = 7
KEY = f"({YEAR},{ROUND})"


@pytest.fixture
def stored_history(monkeypatch) -> dict:
    """Serve a mutable prediction history without touching the document store."""
    history: dict = {}
    monkeypatch.setattr(review_module, "_load_prediction_history", lambda: history)
    return history


# ---------------------------------------------------------------------------
# Snapshot selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_legacy_entry_without_snapshots_is_read_from_its_top_level_fields():
    # Records written before snapshots existed carry the prediction inline;
    # reading them as "no snapshot" would discard a whole season of history.
    snapshot = _latest_prediction_snapshot(
        {
            "generated_at": "2026-05-24T13:00:00+00:00",
            "prediction_phase": "post_qualifying",
            "data_sources": ["qualifying"],
            "predicted_positions": {"VER": 1, "LEC": 2},
            "risk_predictions": {"VER": {"dnf_risk_pct": 9}},
        }
    )

    assert snapshot["predicted_positions"] == {"VER": 1, "LEC": 2}
    assert snapshot["prediction_phase"] == "post_qualifying"
    assert snapshot["data_sources"] == ["qualifying"]
    assert snapshot["risk_predictions"] == {"VER": {"dnf_risk_pct": 9}}


@pytest.mark.unit
def test_an_empty_legacy_entry_yields_empty_collections_not_none():
    # The caller iterates these directly, so absent must read as empty.
    snapshot = _latest_prediction_snapshot({})

    assert snapshot["predicted_positions"] == {}
    assert snapshot["risk_predictions"] == {}
    assert snapshot["data_sources"] == []


@pytest.mark.unit
def test_the_newest_snapshot_wins_over_the_pre_qualifying_one():
    # A weekend writes a pre-qualifying snapshot then a post-qualifying one;
    # the published prediction is the last, so that is what gets graded.
    snapshot = _latest_prediction_snapshot(
        {
            "snapshots": [
                {"prediction_phase": "pre_qualifying", "predicted_positions": {"VER": 4}},
                {"prediction_phase": "post_qualifying", "predicted_positions": {"VER": 1}},
            ]
        }
    )

    assert snapshot["prediction_phase"] == "post_qualifying"


# ---------------------------------------------------------------------------
# Refusal paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_race_that_was_never_predicted_is_reported_as_having_no_snapshot(stored_history):
    review = build_prediction_review(YEAR, ROUND)

    assert review == {"evaluated": False, "reason": "No stored prediction snapshot for this race."}


@pytest.mark.unit
def test_a_snapshot_with_no_finishing_order_is_distinguished_from_a_missing_result(stored_history):
    # A prediction that ran but produced no grid (no driver data) is a different
    # failure from one that simply has not been raced yet.
    stored_history[KEY] = {
        "snapshots": [{"predicted_positions": {}}],
        "actual_positions": {"VER": 1},
    }

    review = build_prediction_review(YEAR, ROUND)

    assert review == {"evaluated": False, "reason": "Stored prediction has no finishing order."}


@pytest.mark.unit
def test_a_prediction_and_result_sharing_no_driver_codes_is_refused_rather_than_scored_zero(stored_history):
    # A code-set mismatch (e.g. numbers on one side, abbreviations on the other)
    # would otherwise report a perfectly plausible-looking 0% accuracy.
    stored_history[KEY] = {
        "snapshots": [{"predicted_positions": {"VER": 1, "LEC": 2}}],
        "actual_positions": {"1": 1, "16": 2},
    }

    review = build_prediction_review(YEAR, ROUND)

    assert review == {"evaluated": False, "reason": "Prediction and result do not share driver codes."}


# ---------------------------------------------------------------------------
# Fetching entry point
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_prediction_review_loads_the_actual_result_before_comparing(monkeypatch, stored_history):
    """The fetching variant must record the result *first*, then review it."""
    order: list[str] = []

    def _record(year: int, round_num: int) -> None:
        order.append(f"record:{year}:{round_num}")
        stored_history[KEY] = {
            "snapshots": [
                {
                    "generated_at": "2026-06-14T13:00:00+00:00",
                    "predicted_positions": {"VER": 1, "LEC": 2},
                }
            ],
            "actual_positions": {"VER": 1, "LEC": 2},
        }

    monkeypatch.setattr(review_module, "record_actual_result", _record)

    review = get_prediction_review(YEAR, ROUND)

    # Without the load-first step this race would still read as "not available".
    assert order == [f"record:{YEAR}:{ROUND}"]
    assert review["evaluated"] is True
    assert review["winner_correct"] is True
    assert review["exact_position_hits"] == 2


@pytest.mark.unit
def test_get_prediction_review_still_reports_when_the_result_load_finds_nothing(monkeypatch, stored_history):
    monkeypatch.setattr(review_module, "record_actual_result", lambda year, round_num: None)

    assert get_prediction_review(YEAR, ROUND)["evaluated"] is False
