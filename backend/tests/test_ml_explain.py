"""Tests for app.ml.explain — exact attribution for the linear finish model.

The explanation is shown to users as the reason behind a prediction, so a wrong
sign or a mismatched feature/coefficient pairing is a correctness bug that looks
like a feature. The properties pinned here:

* the contributions sum, with the intercept, back to the model's own prediction
  (which is what makes this attribution *exact* rather than approximate);
* index ``i`` of ``coef_``/``mean_``/``scale_`` always lines up with feature
  ``i``;
* the sign convention holds — negative contribution means a better (lower)
  finishing position, i.e. it helps the driver.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ml.explain import (
    FEATURE_LABELS,
    FeatureContribution,
    _unwrap,
    attribution_dicts,
    attribution_phrases,
    explain_prediction,
)
from app.ml.features import FEATURES


def _linear_payload(coef, *, mean=None, scale=None, features=None) -> dict:
    """A payload shaped like the joblib artifact, with a hand-built estimator."""
    final = SimpleNamespace(coef_=list(coef))
    if mean is None:
        model = final
    else:
        scaler = SimpleNamespace(mean_=list(mean), scale_=list(scale))
        model = SimpleNamespace(named_steps={"scaler": scaler, "ridge": final})
    return {"model": model, "features": features}


@pytest.mark.unit
def test_every_model_feature_has_a_human_label():
    assert set(FEATURE_LABELS) == set(FEATURES)


@pytest.mark.unit
def test_unwrap_returns_scaler_and_final_estimator_from_a_pipeline():
    scaler = SimpleNamespace(mean_=[0.0], scale_=[1.0])
    ridge = SimpleNamespace(coef_=[1.0])
    model = SimpleNamespace(named_steps={"scaler": scaler, "ridge": ridge})

    assert _unwrap(model) == (scaler, ridge)


@pytest.mark.unit
def test_unwrap_returns_no_scaler_for_a_bare_estimator():
    ridge = SimpleNamespace(coef_=[1.0])

    assert _unwrap(ridge) == (None, ridge)


@pytest.mark.unit
def test_unwrap_returns_no_scaler_when_the_pipeline_has_none():
    """A pipeline of unscaled steps must not mistake a step for a scaler."""
    ridge = SimpleNamespace(coef_=[1.0])
    model = SimpleNamespace(named_steps={"passthrough": SimpleNamespace(), "ridge": ridge})

    assert _unwrap(model) == (None, ridge)


@pytest.mark.unit
def test_explain_prediction_returns_none_without_a_model():
    assert explain_prediction({"model": None}, dict.fromkeys(FEATURES, 1.0)) is None


@pytest.mark.unit
def test_explain_prediction_returns_none_for_a_non_linear_estimator():
    """Tree ensembles have no coefficients, so no exact linear attribution."""
    forest = SimpleNamespace(feature_importances_=[0.5, 0.5])

    assert explain_prediction({"model": forest}, {}) is None


@pytest.mark.unit
def test_explain_prediction_falls_back_to_the_shared_feature_order():
    payload = _linear_payload([1.0] * len(FEATURES), features=None)

    contributions = explain_prediction(payload, dict.fromkeys(FEATURES, 1.0))

    assert {c.feature for c in contributions} == set(FEATURES)


@pytest.mark.unit
def test_explain_prediction_uses_the_feature_list_stored_with_the_model():
    """The artifact's own feature list wins — that is what it was fitted on."""
    payload = _linear_payload([2.0, 3.0], features=["grid_position", "team_standing"])

    contributions = explain_prediction(payload, {"grid_position": 1.0, "team_standing": 2.0})

    assert [c.feature for c in contributions] == ["team_standing", "grid_position"]


@pytest.mark.unit
def test_unscaled_contribution_is_coefficient_times_raw_value():
    payload = _linear_payload([2.0, -4.0], features=["grid_position", "driver_standing"])

    contributions = explain_prediction(payload, {"grid_position": 3.0, "driver_standing": 1.0})
    by_name = {c.feature: c for c in contributions}

    assert by_name["grid_position"].contribution == pytest.approx(6.0)
    assert by_name["driver_standing"].contribution == pytest.approx(-4.0)


@pytest.mark.unit
def test_scaled_contribution_standardizes_the_raw_value_first():
    payload = _linear_payload([2.0], mean=[10.0], scale=[4.0], features=["grid_position"])

    (contribution,) = explain_prediction(payload, {"grid_position": 14.0})

    # z = (14 - 10) / 4 = 1.0 → contribution = coef * z
    assert contribution.contribution == pytest.approx(2.0)
    assert contribution.value == 14.0, "the reported value stays in raw units"


@pytest.mark.unit
def test_zero_variance_feature_does_not_divide_by_zero():
    """A constant column gets scale 0 from StandardScaler; treat it as 1.0."""
    payload = _linear_payload([2.0], mean=[5.0], scale=[0.0], features=["had_sprint"])

    (contribution,) = explain_prediction(payload, {"had_sprint": 6.0})

    assert contribution.contribution == pytest.approx(2.0)


@pytest.mark.unit
def test_missing_feature_value_is_treated_as_zero():
    payload = _linear_payload([3.0], features=["grid_position"])

    (contribution,) = explain_prediction(payload, {})

    assert contribution.value == 0.0
    assert contribution.contribution == pytest.approx(0.0)


@pytest.mark.unit
def test_contributions_are_sorted_by_absolute_impact():
    payload = _linear_payload([1.0, -5.0, 2.0], features=["grid_position", "team_standing", "circuit_avg"])

    contributions = explain_prediction(payload, {"grid_position": 1.0, "team_standing": 1.0, "circuit_avg": 1.0})

    assert [c.feature for c in contributions] == ["team_standing", "circuit_avg", "grid_position"]


@pytest.mark.unit
def test_labels_come_from_the_lookup_and_fall_back_to_the_raw_name():
    payload = _linear_payload([1.0, 1.0], features=["grid_position", "tyre_temp"])

    contributions = explain_prediction(payload, {"grid_position": 1.0, "tyre_temp": 2.0})
    by_name = {c.feature: c.label for c in contributions}

    assert by_name["grid_position"] == "grid position"
    assert by_name["tyre_temp"] == "tyre_temp"


@pytest.mark.integration
def test_contributions_reconstruct_the_real_pipeline_prediction():
    """The whole point of a linear attribution: it is exact, not approximate.

    Fits a genuine ``StandardScaler -> Ridge`` and checks that
    ``intercept + Σ contributions`` equals ``model.predict`` to floating-point
    precision.
    """
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rows = [[float(i % 7), float(i % 3), float(i % 5)] for i in range(40)]
    target = [float((i % 7) + 1) for i in range(40)]
    names = ["grid_position", "team_standing", "circuit_avg"]

    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(rows, target)

    features = dict(zip(names, [4.0, 1.0, 2.0], strict=True))
    contributions = explain_prediction({"model": model, "features": names}, features)

    predicted = float(model.predict([[4.0, 1.0, 2.0]])[0])
    intercept = float(model.steps[-1][1].intercept_)
    assert sum(c.contribution for c in contributions) + intercept == pytest.approx(predicted)


@pytest.mark.unit
def test_attribution_dicts_label_the_direction_from_the_sign():
    contributions = [
        FeatureContribution("grid_position", "grid position", 1.234, -2.3456),
        FeatureContribution("team_standing", "car/team strength", 9.0, 1.5),
    ]

    assert attribution_dicts(contributions) == [
        {
            "feature": "grid_position",
            "label": "grid position",
            "value": 1.23,
            "contribution": -2.346,
            "direction": "helps",
        },
        {
            "feature": "team_standing",
            "label": "car/team strength",
            "value": 9.0,
            "contribution": 1.5,
            "direction": "hurts",
        },
    ]


@pytest.mark.unit
def test_attribution_dicts_calls_a_zero_contribution_hurts():
    """The boundary is ``< 0``, so an exactly neutral feature is not "helps"."""
    (row,) = attribution_dicts([FeatureContribution("had_sprint", "sprint weekend", 0.0, 0.0)])

    assert row["direction"] == "hurts"


@pytest.mark.unit
def test_attribution_dicts_handles_no_contributions():
    assert attribution_dicts([]) == []


@pytest.mark.unit
def test_attribution_phrases_reads_from_the_drivers_point_of_view():
    contributions = [
        FeatureContribution("grid_position", "grid position", 2.0, -3.42),
        FeatureContribution("team_standing", "car/team strength", 8.0, 2.5),
    ]

    assert attribution_phrases(contributions) == [
        "Grid position lifts the projection ~3.4 places",
        "Car/team strength drags the projection ~2.5 places",
    ]


@pytest.mark.unit
def test_attribution_phrases_uses_the_singular_for_exactly_one_place():
    contributions = [FeatureContribution("grid_position", "grid position", 2.0, -1.02)]

    assert attribution_phrases(contributions) == ["Grid position lifts the projection ~1.0 place"]


@pytest.mark.unit
def test_attribution_phrases_skips_contributions_below_the_noise_floor():
    contributions = [
        FeatureContribution("had_sprint", "sprint weekend", 0.0, 0.01),
        FeatureContribution("grid_position", "grid position", 2.0, -0.9),
    ]

    assert attribution_phrases(contributions) == ["Grid position lifts the projection ~0.9 places"]


@pytest.mark.unit
def test_attribution_phrases_stops_at_top_n():
    contributions = [FeatureContribution(f"f{i}", f"feature {i}", 1.0, -1.0 - i) for i in range(5)]

    assert len(attribution_phrases(contributions, top_n=3)) == 3


@pytest.mark.unit
def test_attribution_phrases_returns_nothing_when_every_effect_is_noise():
    contributions = [FeatureContribution("had_sprint", "sprint weekend", 0.0, 0.05)]

    assert attribution_phrases(contributions) == []
