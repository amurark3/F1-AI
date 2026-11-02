"""Tests for app.data.predictions.driver_score — one driver's predicted finish.

This is where a race weekend's signals become a single number and the sentences
that justify it, so the tests pin the arithmetic and the wording together:

* **The weighted blend must respect its signs.** ``grid_delta`` is subtracted
  because a positive delta means places gained; flipping it would reward the
  drivers who historically lose ground.
* **A missing signal must not read as a good one.** A driver with no sprint
  result on a sprint weekend takes an explicit back-of-grid penalty rather than
  a zero, and a back-filled driver's synthetic grid slot is flagged in the
  reasoning.
* **The reasoning must agree with the model's inputs, in both phases.** Before
  qualifying the grid input is an estimate, so no factor may call it a
  qualifying result or a back-of-grid slot while the attribution credits it as
  a front-row start (the R20 pre-qualifying bug).
* **Advertised sources must be sources actually used.** The ``used_*`` flags
  decide what the response claims it consulted.

The model boundary (``_ml_finish_score`` / ``_ml_explanation``) is stubbed; the
scoring helpers and feature builder are the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import pytest

from app.data.predictions import driver_score as module
from app.data.predictions.driver_score import RaceSignals
from app.ml.explain import FEATURE_LABELS, FeatureContribution

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_EVEN_WEIGHTS = {"qualifying": 0.5, "recent_form": 0.5}


def _signals(**overrides: Any) -> RaceSignals:
    defaults: dict[str, Any] = {
        "year": 2024,
        "round_num": 5,
        "active_weights": dict(_EVEN_WEIGHTS),
        "ml_blend_weight": 0.65,
        "adaptive_weight": 0.22,
        "circuit_history": {},
        "constructor_standings": [],
        "driver_standings": {},
        "grid_deltas": {},
        "sprint_positions": {},
        "had_sprint": False,
        "recent_sprint_form": {},
        "adaptive_corrections": {},
        "is_pre_qualifying": False,
    }
    return RaceSignals(**{**defaults, **overrides})


def _driver(code: str = "VER", **overrides: Any) -> dict:
    return {
        "driver_code": code,
        "driver_name": f"{code} Driver",
        "team": "Red Bull",
        "position": 3,
        **overrides,
    }


@pytest.fixture(autouse=True)
def _no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to no recent form and no trained model."""
    monkeypatch.setattr(module, "_load_recent_form", lambda code, year, rnd: [])
    monkeypatch.setattr(module, "_ml_finish_score", lambda features: None)
    monkeypatch.setattr(module, "_ml_explanation", lambda features: None)


def _contribution(feature: str, label: str, value: float, contribution: float) -> FeatureContribution:
    return FeatureContribution(feature=feature, label=label, value=value, contribution=contribution)


# ---------------------------------------------------------------------------
# _weighted_heuristic_score
# ---------------------------------------------------------------------------


_BASE_MEASURES: dict[str, float | None] = {
    "qualifying": 4.0,
    "sprint_position": None,
    "recent_form": 6.0,
    "circuit_history": 8.0,
    "team_strength": 2.0,
    "grid_delta": 3.0,
    "ml_score": None,
}


@pytest.mark.unit
def test_only_the_weighted_signals_contribute_to_the_score():
    score = module._weighted_heuristic_score({"qualifying": 0.5, "recent_form": 0.5}, _BASE_MEASURES)

    assert score == pytest.approx(5.0)


@pytest.mark.unit
def test_a_positive_grid_delta_improves_the_score_rather_than_worsening_it():
    weights = {"qualifying": 0.9, "grid_delta": 0.1}

    score = module._weighted_heuristic_score(weights, _BASE_MEASURES)

    assert score == pytest.approx(0.9 * 4.0 - 0.1 * 3.0)
    assert score < 0.9 * 4.0


@pytest.mark.unit
def test_a_sprint_result_is_scored_at_its_finishing_position():
    weights = {"sprint": 1.0}
    measures = {**_BASE_MEASURES, "sprint_position": 2.0}

    assert module._weighted_heuristic_score(weights, measures) == pytest.approx(2.0)


@pytest.mark.unit
def test_a_missing_sprint_result_takes_a_back_of_grid_penalty():
    """No sprint finish on a sprint weekend means a DNF/DNS, not a free pass."""
    assert module._weighted_heuristic_score({"sprint": 1.0}, _BASE_MEASURES) == pytest.approx(18.0)


@pytest.mark.unit
def test_a_weightless_signal_set_scores_zero():
    assert module._weighted_heuristic_score({}, _BASE_MEASURES) == 0.0


# ---------------------------------------------------------------------------
# _confidence_signals
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confidence_uses_only_the_signals_that_have_data():
    signals = module._confidence_signals(_BASE_MEASURES, has_recent=False, has_circuit=False)

    assert signals == [4.0, 2.0]


@pytest.mark.unit
def test_every_available_signal_widens_the_confidence_input_set():
    measures = {**_BASE_MEASURES, "sprint_position": 5.0, "ml_score": 3.0}

    signals = module._confidence_signals(measures, has_recent=True, has_circuit=True)

    assert signals == [4.0, 5.0, 6.0, 8.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# _model_reasoning
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_attribution_from_the_model_yields_no_reasoning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module, "_ml_explanation", lambda features: None)

    assert module._model_reasoning({"grid_position": 3.0}, is_pre_qualifying=False) == (None, [])


@pytest.mark.unit
def test_model_reasoning_serialises_contributions_and_phrases_the_top_two(
    monkeypatch: pytest.MonkeyPatch,
):
    contributions = [
        _contribution("grid_position", "grid position", 3.0, -2.4),
        _contribution("recent_form_avg", "recent form", 8.0, 1.2),
        _contribution("team_standing", "car/team strength", 2.0, -0.9),
    ]
    monkeypatch.setattr(module, "_ml_explanation", lambda features: contributions)

    attribution, phrases = module._model_reasoning({"grid_position": 3.0}, is_pre_qualifying=False)

    assert [row["feature"] for row in attribution] == [
        "grid_position",
        "recent_form_avg",
        "team_standing",
    ]
    assert [row["direction"] for row in attribution] == ["helps", "hurts", "helps"]
    assert phrases == [
        "Grid position lifts the projection ~2.4 places",
        "Recent form drags the projection ~1.2 places",
    ]


@pytest.mark.unit
def test_before_qualifying_the_model_reasoning_names_the_grid_input_as_an_estimate(
    monkeypatch: pytest.MonkeyPatch,
):
    contributions = [
        _contribution("grid_position", "grid position", 1.0, -3.8),
        _contribution("team_standing", "car/team strength", 1.0, -0.9),
    ]
    monkeypatch.setattr(module, "_ml_explanation", lambda features: contributions)

    attribution, phrases = module._model_reasoning({"grid_position": 1.0}, is_pre_qualifying=True)

    assert [row["label"] for row in attribution] == ["expected grid (pre-qualifying estimate)", "car/team strength"]
    assert phrases == [
        "Expected grid (pre-qualifying estimate) lifts the projection ~3.8 places",
        "Car/team strength lifts the projection ~0.9 places",
    ]


# ---------------------------------------------------------------------------
# _build_factors
# ---------------------------------------------------------------------------

_POST_QUALIFYING_CONTEXT = {"ml_score": None, "correction": None, "is_pre_qualifying": False}


@pytest.mark.unit
def test_heuristic_reasoning_is_capped_at_three_factors():
    factors = module._build_factors(
        _driver(),
        ["one", "two", "three", "four"],
        [],
        _POST_QUALIFYING_CONTEXT,
    )

    assert factors == ["one", "two", "three"]


@pytest.mark.unit
def test_a_model_backed_prediction_leads_with_its_projection_and_allows_five_factors():
    factors = module._build_factors(
        _driver(),
        ["one", "two", "three"],
        ["phrase one", "phrase two"],
        {**_POST_QUALIFYING_CONTEXT, "ml_score": 2.4},
    )

    assert factors == ["Trained model projects P2.4", "phrase one", "phrase two", "one", "two"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("correction", "expected"),
    [
        (2.5, "Adaptive history downgrades by 2.5 places"),
        (-3.0, "Adaptive history upgrades by 3.0 places"),
    ],
)
def test_a_meaningful_adaptive_correction_is_explained(correction: float, expected: str):
    factors = module._build_factors(
        _driver(),
        ["one"],
        [],
        {**_POST_QUALIFYING_CONTEXT, "correction": {"correction": correction, "samples": 4}},
    )

    assert factors == ["one", expected]


@pytest.mark.unit
def test_a_sub_place_correction_is_not_worth_reporting():
    factors = module._build_factors(
        _driver(),
        ["one"],
        [],
        {**_POST_QUALIFYING_CONTEXT, "correction": {"correction": 0.4, "samples": 4}},
    )

    assert factors == ["one"]


@pytest.mark.unit
def test_a_back_filled_driver_leads_with_the_missing_qualifying_flag():
    factors = module._build_factors(
        _driver(no_qualifying_time=True),
        ["one", "two", "three"],
        [],
        _POST_QUALIFYING_CONTEXT,
    )

    assert factors[0] == "No qualifying time set — placed at back of grid"
    assert factors[1:] == ["one", "two", "three"]


@pytest.mark.unit
def test_before_qualifying_a_back_filled_driver_is_not_said_to_start_from_the_back():
    """Nobody has a qualifying time yet, and the slot may be P1 (championship order)."""
    factors = module._build_factors(
        _driver(position=1, no_qualifying_time=True),
        ["one", "two", "three"],
        [],
        {**_POST_QUALIFYING_CONTEXT, "is_pre_qualifying": True},
    )

    assert factors == ["one", "two", "three"]


# ---------------------------------------------------------------------------
# score_driver
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_heuristic_only_score_reports_no_model_and_no_adaptive_use():
    result = module.score_driver(_driver(position=4), _signals())

    assert result.used_model is False
    assert result.used_adaptive is False
    assert result.used_recent_form is False
    assert result.scored["ml_score"] is None
    assert result.scored["adaptive_correction"] is None
    # Qualifying P4 and the default recent-form mean of 10, evenly weighted.
    assert result.scored["score"] == pytest.approx(7.0)
    assert result.scored["heuristic_score"] == pytest.approx(7.0)


@pytest.mark.unit
def test_recent_form_is_used_and_advertised_when_the_driver_has_history(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(module, "_load_recent_form", lambda code, year, rnd: [2, 4])

    result = module.score_driver(_driver(position=4), _signals())

    assert result.used_recent_form is True
    assert result.scored["score"] == pytest.approx(3.5)


@pytest.mark.unit
def test_a_model_projection_is_blended_over_the_heuristic(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module, "_ml_finish_score", lambda features: 2.0)

    result = module.score_driver(_driver(position=4), _signals(ml_blend_weight=0.65))

    assert result.used_model is True
    assert result.scored["ml_score"] == 2.0
    assert result.scored["heuristic_score"] == pytest.approx(7.0)
    assert result.scored["score"] == pytest.approx(0.65 * 2.0 + 0.35 * 7.0)
    assert result.scored["factors"][0] == "Trained model projects P2.0"


@pytest.mark.unit
def test_an_adaptive_correction_with_samples_shifts_the_score(monkeypatch: pytest.MonkeyPatch):
    correction = {"correction": 2.0, "samples": 6}

    result = module.score_driver(
        _driver(position=4),
        _signals(adaptive_corrections={"VER": correction}, adaptive_weight=0.22),
    )

    assert result.used_adaptive is True
    assert result.scored["adaptive_correction"] == correction
    assert result.scored["score"] == pytest.approx(7.0 + 0.22 * 2.0)


@pytest.mark.unit
def test_a_correction_with_no_samples_behind_it_is_not_applied():
    correction = {"correction": 3.0, "samples": 0}

    result = module.score_driver(
        _driver(position=4),
        _signals(adaptive_corrections={"VER": correction}),
    )

    assert result.used_adaptive is False
    assert result.scored["score"] == pytest.approx(7.0)


@pytest.mark.unit
def test_a_driver_with_no_grid_slot_is_scored_from_a_midfield_default():
    result = module.score_driver({"driver_code": "VER"}, _signals())

    assert result.scored["quali_pos"] == 10
    assert result.scored["driver_standing"] == 10
    assert result.scored["team_pos"] == 10
    assert result.scored["driver_name"] == "VER"
    assert result.scored["team"] == ""


@pytest.mark.unit
def test_the_scored_row_carries_the_context_the_risk_model_reads():
    signals = _signals(
        sprint_positions={"VER": 2},
        had_sprint=True,
        driver_standings={"VER": 1},
        constructor_standings=[{"constructor_name": "Red Bull", "position": 1}],
        grid_deltas={"VER": 1.5},
        circuit_history={"VER": [1, 3]},
        active_weights={"sprint": 0.4, "qualifying": 0.3, "recent_form": 0.3},
    )

    result = module.score_driver(_driver(position=3), signals)

    assert result.scored["sprint_pos"] == 2
    assert result.scored["team_pos"] == 1
    assert result.scored["driver_standing"] == 1
    assert result.scored["confidence_low"] < result.scored["confidence_high"]


@pytest.mark.unit
def test_a_pre_qualifying_prediction_is_less_confident_than_a_post_qualifying_one():
    driver = _driver(position=3)

    post = module.score_driver(driver, _signals(is_pre_qualifying=False))
    pre = module.score_driver(driver, _signals(is_pre_qualifying=True))

    assert pre.scored["confidence_high"] < post.scored["confidence_high"]
    assert pre.scored["confidence_low"] < post.scored["confidence_low"]


@pytest.mark.unit
def test_a_model_backed_driver_carries_its_attribution_into_the_row(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(module, "_ml_finish_score", lambda features: 3.0)
    monkeypatch.setattr(
        module,
        "_ml_explanation",
        lambda features: [_contribution("grid_position", "grid position", 3.0, -2.4)],
    )

    result = module.score_driver(_driver(position=3), _signals())

    assert result.scored["model_attribution"] == [
        {
            "feature": "grid_position",
            "label": "grid position",
            "value": 3.0,
            "contribution": -2.4,
            "direction": "helps",
        }
    ]
    assert "Grid position lifts the projection ~2.4 places" in result.scored["factors"]


@pytest.mark.unit
def test_a_back_filled_driver_is_flagged_in_its_own_reasoning():
    result = module.score_driver(_driver(position=20, no_qualifying_time=True), _signals())

    assert result.scored["factors"][0] == "No qualifying time set — placed at back of grid"


# ---------------------------------------------------------------------------
# the reasoning agrees with the model's inputs, in both phases
# ---------------------------------------------------------------------------

# The trained StandardScaler -> Ridge model reduced to its grid term: a slot
# ahead of the training mean helps, one behind it hurts. P1 comes out at about
# -4 places, which is what the R20 pre-qualifying attribution showed.
_MODEL_GRID_MEAN = 10.5
_MODEL_GRID_COEF = 0.4
_FIELD_SIZE = 22
_PRE_QUALIFYING_GRID_LABEL = "expected grid (pre-qualifying estimate)"

# A factor that names a grid slot: "Qualifying P7", "Practice pace P16",
# "Pole position (qualifying P1)", "Expected grid P3 (pre-qualifying estimate)".
_GRID_SLOT_CLAIM = re.compile(r"(?i:qualifying|practice|grid)\D*?P(\d+)")
# A model phrase: "<Label> lifts|drags the projection ~x places".
_MODEL_PHRASE = re.compile(r"^(?P<label>.+) (?P<verb>lifts|drags) the projection")


def _grid_term(features: dict[str, float]) -> list[FeatureContribution]:
    grid = features["grid_position"]
    contribution = _MODEL_GRID_COEF * (grid - _MODEL_GRID_MEAN)
    return [_contribution("grid_position", FEATURE_LABELS["grid_position"], grid, contribution)]


@dataclass(frozen=True)
class _Weekend:
    """How far a weekend got, which decides what the grid input really is."""

    name: str
    pre_qualifying: bool
    # Cars with a time in the session the grid was read from. The rest are
    # back-filled behind them, or from P1 in championship order when none ran.
    timed: int
    weights: dict[str, float]


_WEEKENDS = (
    _Weekend("pre-qualifying, no session run (R20)", pre_qualifying=True, timed=0, weights={"recent_form": 1.0}),
    _Weekend("pre-qualifying, practice pace", pre_qualifying=True, timed=18, weights=dict(_EVEN_WEIGHTS)),
    _Weekend("post-qualifying", pre_qualifying=False, timed=20, weights=dict(_EVEN_WEIGHTS)),
)


def _field(weekend: _Weekend) -> list[dict]:
    """The whole grid as the weekend roster hands it to the scorer."""
    return [
        _driver(f"D{slot:02d}", position=slot, **({"no_qualifying_time": True} if slot > weekend.timed else {}))
        for slot in range(1, _FIELD_SIZE + 1)
    ]


def _names_another_slot(factor: str, grid: dict) -> bool:
    claim = _GRID_SLOT_CLAIM.search(factor)
    return claim is not None and int(claim.group(1)) != grid["value"]


def _misplaces_at_the_back(factor: str, grid: dict, weekend: _Weekend) -> bool:
    """ "Back of grid" holds only behind every timed car, with the slot hurting the projection."""
    if "back of grid" not in factor:
        return False
    behind_every_timed_car = 0 < weekend.timed < grid["value"]
    return weekend.pre_qualifying or not behind_every_timed_car or grid["direction"] == "helps"


def _cites_qualifying_before_it_ran(factor: str, weekend: _Weekend) -> bool:
    return weekend.pre_qualifying and "qualifying" in factor.lower().replace("pre-qualifying", "")


def _cites_practice_without_a_time(factor: str, *, timed: bool) -> bool:
    return not timed and "practice" in factor.lower()


def _misreads_the_attribution(factor: str, attribution: list[dict]) -> bool:
    phrase = _MODEL_PHRASE.match(factor)
    if phrase is None:
        return False
    verbs = {row["label"].capitalize(): "lifts" if row["direction"] == "helps" else "drags" for row in attribution}
    return verbs.get(phrase["label"]) != phrase["verb"]


def _contradictions(scored: dict, weekend: _Weekend, *, timed: bool) -> list[str]:
    """Every factor that disagrees with the inputs the model was actually given."""
    attribution = scored["model_attribution"]
    grid = next(row for row in attribution if row["feature"] == "grid_position")
    checks = (
        lambda factor: _names_another_slot(factor, grid),
        lambda factor: _misplaces_at_the_back(factor, grid, weekend),
        lambda factor: _cites_qualifying_before_it_ran(factor, weekend),
        lambda factor: _cites_practice_without_a_time(factor, timed=timed),
        lambda factor: _misreads_the_attribution(factor, attribution),
    )
    return [factor for factor in scored["factors"] if any(check(factor) for check in checks)]


@pytest.fixture
def _linear_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_ml_finish_score", lambda features: features["grid_position"])
    monkeypatch.setattr(module, "_ml_explanation", _grid_term)


@pytest.mark.unit
@pytest.mark.usefixtures("_linear_model")
@pytest.mark.parametrize("weekend", _WEEKENDS, ids=lambda weekend: weekend.name)
def test_no_reasoning_factor_contradicts_the_model_attribution(weekend: _Weekend):
    signals = _signals(is_pre_qualifying=weekend.pre_qualifying, active_weights=weekend.weights)

    contradictions = {}
    for driver in _field(weekend):
        scored = module.score_driver(driver, signals).scored
        found = _contradictions(scored, weekend, timed=not driver.get("no_qualifying_time"))
        if found:
            contradictions[driver["driver_code"]] = found

    assert contradictions == {}


@pytest.mark.unit
@pytest.mark.usefixtures("_linear_model")
@pytest.mark.parametrize(
    ("pre_qualifying", "label"),
    [(True, _PRE_QUALIFYING_GRID_LABEL), (False, "grid position")],
)
def test_the_grid_input_is_labelled_for_the_phase_it_was_read_in(pre_qualifying: bool, label: str):
    driver = _driver("ANT", position=1, no_qualifying_time=pre_qualifying)

    scored = module.score_driver(driver, _signals(is_pre_qualifying=pre_qualifying)).scored

    grid = scored["model_attribution"][0]
    assert (grid["feature"], grid["label"], grid["value"], grid["direction"]) == ("grid_position", label, 1.0, "helps")
    assert f"{label.capitalize()} lifts the projection ~3.8 places" in scored["factors"]


@pytest.mark.unit
@pytest.mark.usefixtures("_linear_model")
def test_the_r20_pre_qualifying_leader_reads_as_an_expected_grid_slot():
    """Before any session the field is back-filled from P1 in championship order."""
    leader = _driver("ANT", position=1, no_qualifying_time=True)

    scored = module.score_driver(leader, _signals(is_pre_qualifying=True, active_weights={"recent_form": 1.0})).scored

    assert "Expected grid P1 (pre-qualifying estimate)" in scored["factors"]
    assert not any("back of grid" in factor or "practice" in factor for factor in scored["factors"])
