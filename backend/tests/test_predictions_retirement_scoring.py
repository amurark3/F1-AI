"""A retirement is scored as a retirement call, never as a finishing place.

R19 Mexico City (the entry stored for the race, regraded to the FIA final
classification as D1.8 does): five cars retired and the published order lists
them at 18-22. Those places are not finishes, so they must not reach exact,
within-3 or average-miss metrics, in the review or the rolling accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data.predictions import accuracy as accuracy_module, review as review_module
from app.data.predictions.history import actual_fields
from app.data.predictions.review import build_prediction_review
from app.data.race_classification import (
    OPENF1_SOURCE,
    RaceClassification,
    _with_reasons,
    classification_from_openf1,
)

R19 = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
RETIRED = ("LIN", "BEA", "BOT", "STR", "ALO")


def _load(name: str) -> dict | list:
    return json.loads((R19 / name).read_text(encoding="utf-8"))


@pytest.fixture
def r19_entry(race_results_f1db) -> dict:
    codes = {row["driver_number"]: row["name_acronym"] for row in _load("openf1_drivers.json")}
    drivers = _with_reasons(2026, 19, classification_from_openf1(_load("openf1_session_result.json"), codes))
    entry = _load("prediction_history_entry.json")["entry"]
    return {**entry, **actual_fields(entry, RaceClassification(source=OPENF1_SOURCE, drivers=drivers))}


@pytest.fixture
def stored(monkeypatch, r19_entry) -> dict:
    history = {"(2026,19)": r19_entry}
    monkeypatch.setattr(review_module, "_load_prediction_history", lambda: history)
    monkeypatch.setattr(accuracy_module, "_load_prediction_history", lambda: history)
    return history


def test_the_five_retirements_are_not_misses_in_the_review(stored, r19_entry):
    review = build_prediction_review(2026, 19)
    rows = {row["driver_code"]: row for row in review["driver_results"]}
    actual = r19_entry["actual_positions"]
    predicted = r19_entry["snapshots"][-1]["predicted_positions"]
    finishers = [code for code in actual if code not in RETIRED]

    assert review["drivers_compared"] == len(finishers) == 17
    assert review["exact_position_hits"] == sum(predicted[code] == actual[code] for code in finishers)
    assert review["avg_position_error"] == round(sum(abs(predicted[c] - actual[c]) for c in finishers) / 17, 1)
    for code in RETIRED:
        assert rows[code]["status"] == "DNF"
        assert (rows[code]["actual_position"], rows[code]["position_delta"], rows[code]["exact"]) == (None, None, False)
        assert rows[code]["dnf"] is True
    assert (review["dnf_actual"], review["actual_provisional"]) == (5, True)
    assert review["dnf_correct"] <= review["dnf_predicted"]


def test_the_rolling_accuracy_counts_only_finishers_but_keeps_the_retirement_calls(stored, r19_entry):
    stats = accuracy_module.get_accuracy_stats()
    actual = r19_entry["actual_positions"]
    predicted = r19_entry["snapshots"][-1]["predicted_positions"]
    finishers = [code for code in actual if code not in RETIRED]

    assert stats["exact_position_pct"] == round(sum(predicted[c] == actual[c] for c in finishers) / 17 * 100)
    assert stats["avg_position_error"] == round(sum(abs(predicted[c] - actual[c]) for c in finishers) / 17, 1)
    assert stats["dnf_capture_pct"] is not None
