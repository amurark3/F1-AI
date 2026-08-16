"""Tests for the trained ranker and adaptive corrections (…predictions.model).

The trained model is optional infrastructure: the artefact lives outside the
repo, is absent on a fresh checkout, and can be a version that will not
deserialise. The contract this file pins is that *every* such failure degrades
to the heuristic score rather than breaking a prediction — and that the failure
is remembered, so a missing artefact does not cost a disk probe on every driver
of every request.

The adaptive layer is the other half: it learns a per-driver correction from
historical misses. Its inputs come from a JSON/Postgres document written by
earlier releases, so it must survive strings where numbers were expected,
entries with no result yet, and snapshot-less legacy records — and it must clamp
what it learns, so one 20-place outlier cannot dominate a driver's score.

A real (tiny) scikit-learn pipeline is fitted here rather than mocked, so the
joblib round-trip and the linear attribution path are genuinely exercised.
"""

from __future__ import annotations

import joblib
import numpy as np
import pytest
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.data.predictions import model as model_module
from app.data.predictions.model import (
    _adaptive_position_corrections,
    _load_ml_model,
    _ml_explanation,
    _ml_finish_score,
    warm_model_cache,
)
from app.ml import explain as explain_module
from app.ml.features import FEATURES


def _features(**overrides: float) -> dict[str, float]:
    """A complete feature row, midfield everywhere except what is overridden."""
    row = dict.fromkeys(FEATURES, 10.0)
    row["had_sprint"] = 0.0
    row["sprint_position"] = 0.0
    row["grid_delta_avg"] = 0.0
    row.update(overrides)
    return row


def _fit_pipeline() -> Pipeline:
    """A scaler+Ridge fitted so that finishing position tracks the grid slot.

    Every column is given some spread: a constant column has zero variance, and
    a scaler fitted on one produces a degenerate model that is not what the
    production artefact looks like.
    """
    rows = []
    targets = []
    for grid in range(1, 21):
        row = _features(grid_position=float(grid), recent_form_avg=float(grid))
        row["sprint_position"] = float(grid % 5)
        row["had_sprint"] = float(grid % 2)
        row["recent_sprint_avg"] = float(grid % 7)
        row["circuit_avg"] = float(21 - grid)
        row["team_standing"] = float(1 + grid // 2)
        row["driver_standing"] = float(grid)
        row["grid_delta_avg"] = float(grid % 3) - 1.0
        rows.append([row[name] for name in FEATURES])
        targets.append(float(grid))
    pipeline = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=0.1))])
    # The BLAS backing numpy on this platform raises spurious matmul warnings
    # from inside Ridge's cholesky solve; the fitted coefficients are fine.
    with np.errstate(all="ignore"):
        pipeline.fit(rows, targets)
    return pipeline


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """The loaded model is a process-wide singleton."""
    model_module._ml_model_cache = None
    yield
    model_module._ml_model_cache = None


@pytest.fixture
def trained_model(tmp_path, monkeypatch):
    """Write a real joblib artefact and point the loader at it."""
    payload = {"model": _fit_pipeline(), "features": FEATURES}
    path = tmp_path / "race_predictor.joblib"
    joblib.dump(payload, path)
    monkeypatch.setattr(model_module, "MODEL_PATH", path)
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_valid_artefact_loads_and_is_reported_as_warm(trained_model):
    assert warm_model_cache() is True
    assert _load_ml_model()["features"] == FEATURES


@pytest.mark.integration
def test_the_artefact_is_read_from_disk_only_once(trained_model):
    first = _load_ml_model()
    trained_model.unlink()  # a second read would now fail outright

    assert _load_ml_model() is first


@pytest.mark.unit
def test_a_missing_artefact_degrades_to_no_model(tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "MODEL_PATH", tmp_path / "absent.joblib")

    assert _load_ml_model() is None
    assert warm_model_cache() is False


@pytest.mark.unit
def test_a_failed_load_is_remembered_so_it_is_not_retried_per_driver(tmp_path, monkeypatch):
    calls: list[str] = []

    def _count(path):
        calls.append(str(path))
        raise OSError("no such artefact")

    monkeypatch.setattr(model_module, "MODEL_PATH", tmp_path / "absent.joblib")
    monkeypatch.setattr(joblib, "load", _count)

    assert _load_ml_model() is None
    assert _load_ml_model() is None
    # Twenty drivers per race times a disk probe each is the cost this avoids.
    assert len(calls) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not a dict", id="wrong_type"),
        pytest.param({"features": FEATURES}, id="no_model"),
        pytest.param({"model": object(), "features": []}, id="no_feature_names"),
    ],
)
def test_an_artefact_missing_its_feature_contract_is_rejected(tmp_path, monkeypatch, payload):
    # Features are the model's calling convention: loading a model without them
    # would silently feed it columns in an arbitrary order.
    path = tmp_path / "bad.joblib"
    joblib.dump(payload, path)
    monkeypatch.setattr(model_module, "MODEL_PATH", path)

    assert _load_ml_model() is None


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_model_means_no_projection_rather_than_a_guess(tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "MODEL_PATH", tmp_path / "absent.joblib")

    assert _ml_finish_score(_features()) is None


@pytest.mark.integration
def test_a_better_grid_slot_never_projects_a_worse_finish(trained_model):
    pole = _ml_finish_score(_features(grid_position=1.0, recent_form_avg=1.0))
    back = _ml_finish_score(_features(grid_position=18.0, recent_form_avg=18.0))

    assert pole < back


@pytest.mark.unit
def test_an_estimator_that_raises_at_predict_time_yields_no_projection():
    class _BrokenModel:
        def predict(self, rows):
            raise ValueError("feature shape mismatch")

    model_module._ml_model_cache = {"model": _BrokenModel(), "features": FEATURES}

    assert _ml_finish_score(_features()) is None


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_model_means_no_attribution(tmp_path, monkeypatch):
    monkeypatch.setattr(model_module, "MODEL_PATH", tmp_path / "absent.joblib")

    assert _ml_explanation(_features()) is None


@pytest.mark.integration
def test_attribution_is_ordered_strongest_first_and_names_the_grid_slot(trained_model):
    contributions = _ml_explanation(_features(grid_position=1.0, recent_form_avg=1.0))

    magnitudes = [abs(c.contribution) for c in contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)
    # Grid position is what this model was fitted on, so it must lead — and a
    # pole slot helps, i.e. pulls the projected finish lower (negative).
    assert contributions[0].feature in {"grid_position", "recent_form_avg"}
    assert contributions[0].contribution < 0


@pytest.mark.integration
def test_a_failing_explainer_costs_the_reasoning_not_the_prediction(trained_model, monkeypatch):
    def _fail(payload, features):
        raise RuntimeError("explainer blew up")

    monkeypatch.setattr(explain_module, "explain_prediction", _fail)

    assert _ml_explanation(_features()) is None
    assert _ml_finish_score(_features()) is not None


# ---------------------------------------------------------------------------
# Adaptive corrections
# ---------------------------------------------------------------------------


@pytest.fixture
def stored_history(monkeypatch):
    """Serve prediction history to the adaptive learner without a store."""
    history: dict = {}
    monkeypatch.setattr(model_module, "_load_prediction_history", lambda: history)
    return history


@pytest.mark.unit
def test_no_history_means_no_corrections(stored_history):
    assert _adaptive_position_corrections() == {}


@pytest.mark.unit
def test_a_driver_who_keeps_finishing_worse_than_predicted_is_downgraded(stored_history):
    stored_history["(2026,1)"] = {
        "snapshots": [{"predicted_positions": {"VER": 1, "NOR": 5}}],
        "actual_positions": {"VER": 4, "NOR": 3},
    }

    corrections = _adaptive_position_corrections()

    # Positive means "the model was too optimistic"; VER finished 3 places worse
    # than called, NOR 2 places better.
    assert corrections["VER"]["correction"] == 3.0
    assert corrections["NOR"]["correction"] == -2.0
    assert corrections["VER"]["samples"] == 1


@pytest.mark.unit
def test_a_legacy_entry_without_snapshots_still_teaches_a_correction(stored_history):
    # Records written before snapshots existed carry the prediction at the top
    # level; dropping them would silently shrink the learning window.
    stored_history["(2025,3)"] = {
        "predicted_positions": {"LEC": 2},
        "actual_positions": {"LEC": 6},
    }

    assert _adaptive_position_corrections()["LEC"]["correction"] == 4.0


@pytest.mark.unit
def test_a_race_with_no_recorded_result_teaches_nothing(stored_history):
    stored_history["(2026,9)"] = {
        "snapshots": [{"predicted_positions": {"VER": 1}}],
        "actual_positions": {},
    }

    assert _adaptive_position_corrections() == {}


@pytest.mark.unit
def test_a_driver_absent_from_the_result_is_skipped_rather_than_scored_as_zero(stored_history):
    stored_history["(2026,2)"] = {
        "snapshots": [{"predicted_positions": {"VER": 1, "HUL": 12}}],
        "actual_positions": {"VER": 1},
    }

    corrections = _adaptive_position_corrections()

    assert "HUL" not in corrections
    assert corrections["VER"]["correction"] == 0.0


@pytest.mark.unit
def test_an_unparsable_stored_position_is_skipped_rather_than_raising(stored_history):
    stored_history["(2026,4)"] = {
        "snapshots": [{"predicted_positions": {"VER": "P1", "NOR": 2}}],
        "actual_positions": {"VER": 1, "NOR": 4},
    }

    corrections = _adaptive_position_corrections()

    assert "VER" not in corrections
    assert corrections["NOR"]["correction"] == 2.0


@pytest.mark.unit
@pytest.mark.parametrize(("predicted", "actual", "expected"), [(1, 20, 6.0), (20, 1, -6.0)])
def test_a_single_catastrophic_miss_is_clamped(stored_history, predicted, actual, expected):
    # A first-lap crash from pole is not evidence the model is 19 places wrong
    # about a driver; the clamp stops one outlier owning the correction.
    stored_history["(2026,5)"] = {
        "snapshots": [{"predicted_positions": {"VER": predicted}}],
        "actual_positions": {"VER": actual},
    }

    assert _adaptive_position_corrections()["VER"]["correction"] == expected


@pytest.mark.unit
def test_only_the_last_six_races_of_evidence_are_averaged(stored_history):
    # Eight races: two stale +5 misses that must fall out of the window, then
    # six clean ones.
    for round_num, miss in enumerate([5, 5, 0, 0, 0, 0, 0, 0], start=1):
        stored_history[f"(2026,{round_num})"] = {
            "snapshots": [{"predicted_positions": {"VER": 1}}],
            "actual_positions": {"VER": 1 + miss},
        }

    correction = _adaptive_position_corrections()["VER"]

    assert correction["samples"] == 6
    assert correction["correction"] == 0.0


@pytest.mark.unit
def test_the_latest_snapshot_is_the_one_scored(stored_history):
    # A weekend produces several snapshots (pre-quali, post-quali). The final
    # one is what was actually published, so it is what gets graded.
    stored_history["(2026,6)"] = {
        "snapshots": [
            {"predicted_positions": {"VER": 10}},
            {"predicted_positions": {"VER": 2}},
        ],
        "actual_positions": {"VER": 5},
    }

    assert _adaptive_position_corrections()["VER"]["correction"] == 3.0
