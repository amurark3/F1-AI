"""Scoring one driver against the signals loaded for a race weekend.

Split out of ``compute`` because this is the part that runs per driver: given
the race-wide data loaded once, it produces one driver's predicted score,
confidence band and reasoning. Keeping it separate means the orchestration in
``compute`` reads as the sequence of stages it is, and this file can be reasoned
about one driver at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from app.data.predictions.form import _load_recent_form
from app.data.predictions.model import _ml_explanation, _ml_finish_score
from app.data.predictions.scoring import (
    FactorInputs,
    _compute_confidence,
    _generate_factors,
    _get_team_position,
    _safe_mean,
)
from app.ml.features import DriverSignals, build_feature_row

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = structlog.get_logger()

# Penalty position applied when a driver has no sprint result (DNF/DNS) but the
# weekend did run a sprint — roughly a back-of-grid finish.
_MISSING_SPRINT_POSITION = 18.0

# Grid slot assumed when a driver has no qualifying or practice position.
_DEFAULT_GRID_POSITION = 10

# Championship position assumed for a driver absent from the standings.
_DEFAULT_DRIVER_STANDING = 10

# A correction smaller than this is not worth showing as a reasoning factor.
_MIN_REPORTABLE_CORRECTION = 1

# Reasoning factors kept per driver. Model-backed predictions carry more because
# the model contributes its own per-feature attribution.
_MAX_FACTORS_WITH_MODEL = 5
_MAX_FACTORS_HEURISTIC = 3


@dataclass(frozen=True)
class RaceSignals:
    """Race-wide data loaded once and shared by every driver's score.

    Frozen and passed as one value so the scorer takes a single argument
    instead of a dozen positional ones that are easy to transpose.
    """

    year: int
    round_num: int
    # Normalised to sum to 1.0 across the signals that have data. The model and
    # adaptive weights below are deliberately *not* members: they blend on top
    # of the finished heuristic score, so including them would corrupt that sum.
    active_weights: Mapping[str, float]
    ml_blend_weight: float
    adaptive_weight: float
    circuit_history: Mapping[str, list[int]]
    constructor_standings: Sequence[dict]
    driver_standings: Mapping[str, int]
    grid_deltas: Mapping[str, float]
    sprint_positions: Mapping[str, int]
    had_sprint: bool
    recent_sprint_form: Mapping[str, list]
    adaptive_corrections: Mapping[str, dict]
    is_pre_qualifying: bool


@dataclass(frozen=True)
class DriverScore:
    """One driver's score plus which optional signals actually contributed.

    The flags let the caller report data sources accurately: a model that
    exists but returned nothing for this driver should not be advertised.
    """

    scored: dict
    used_model: bool
    used_adaptive: bool
    used_recent_form: bool


def _weighted_heuristic_score(weights: Mapping[str, float], measures: Mapping[str, float | None]) -> float:
    """Combine the weighted signals into a score, lower being a better finish.

    ``grid_delta`` is subtracted rather than added: a positive delta means the
    driver historically gains places at this circuit.
    """
    score = 0.0
    if "sprint" in weights:
        sprint_pos = measures["sprint_position"]
        score += weights["sprint"] * (_MISSING_SPRINT_POSITION if sprint_pos is None else sprint_pos)
    for signal in ("qualifying", "recent_form", "circuit_history", "team_strength"):
        if signal in weights:
            score += weights[signal] * measures[signal]
    if "grid_delta" in weights:
        score -= weights["grid_delta"] * measures["grid_delta"]
    return score


def _confidence_signals(measures: Mapping[str, float | None], *, has_recent: bool, has_circuit: bool) -> list[float]:
    """Collect the inputs whose spread determines the confidence band."""
    signals = [float(measures["qualifying"])]
    if measures["sprint_position"] is not None:
        signals.append(float(measures["sprint_position"]))
    if has_recent:
        signals.append(measures["recent_form"])
    if has_circuit:
        signals.append(measures["circuit_history"])
    signals.append(float(measures["team_strength"]))
    if measures["ml_score"] is not None:
        signals.append(measures["ml_score"])
    return signals


def _model_reasoning(ml_features: dict[str, float]) -> tuple[list[dict] | None, list[str]]:
    """Return the model's per-feature attribution and its top phrases.

    Imported lazily: the explanation path is only reached when a model actually
    scored, and ``app.ml.explain`` pulls in the numeric stack.
    """
    contributions = _ml_explanation(ml_features)
    if not contributions:
        return None, []

    from app.ml.explain import attribution_dicts, attribution_phrases

    return attribution_dicts(contributions), attribution_phrases(contributions, top_n=2)


def _build_factors(
    driver: Mapping[str, Any],
    heuristic_factors: Sequence[str],
    model_phrases: Sequence[str],
    context: Mapping[str, Any],
) -> list[str]:
    """Assemble the reasoning shown for a driver, most significant first."""
    ml_score = context["ml_score"]
    correction = context["correction"]

    factors = list(heuristic_factors)
    if ml_score is not None:
        factors = [f"Trained model projects P{ml_score:.1f}", *model_phrases, *factors]
    if correction and abs(correction["correction"]) >= _MIN_REPORTABLE_CORRECTION:
        direction = "downgrades" if correction["correction"] > 0 else "upgrades"
        factors.append(f"Adaptive history {direction} by {abs(correction['correction']):.1f} places")

    limit = _MAX_FACTORS_WITH_MODEL if ml_score is not None else _MAX_FACTORS_HEURISTIC
    factors = factors[:limit]

    if driver.get("no_qualifying_time"):
        # Back-filled from the entry list — flag it so the synthetic
        # back-of-grid slot isn't mistaken for a real qualifying result.
        factors = ["No qualifying time set — placed at back of grid", *factors[:4]]
    return factors


def score_driver(driver: Mapping[str, Any], signals: RaceSignals) -> DriverScore:
    """Score one driver, blending the heuristic, the trained model and history."""
    code = driver["driver_code"]

    quali_pos = driver.get("position", _DEFAULT_GRID_POSITION)
    sprint_pos = signals.sprint_positions.get(code)
    recent_positions = _load_recent_form(code, signals.year, signals.round_num)
    driver_circuit = signals.circuit_history.get(code, [])
    team_pos = _get_team_position(driver.get("team", ""), signals.constructor_standings)
    driver_standing = signals.driver_standings.get(code, _DEFAULT_DRIVER_STANDING)
    driver_delta = signals.grid_deltas.get(code, 0.0)

    measures: dict[str, Any] = {
        "qualifying": quali_pos,
        "sprint_position": sprint_pos,
        "recent_form": _safe_mean(recent_positions),
        "circuit_history": _safe_mean(driver_circuit),
        "team_strength": team_pos,
        "grid_delta": driver_delta,
        "ml_score": None,
    }

    heuristic_score = _weighted_heuristic_score(signals.active_weights, measures)
    score = heuristic_score

    ml_features = build_feature_row(
        DriverSignals(
            grid_position=quali_pos,
            sprint_position=sprint_pos,
            had_sprint=signals.had_sprint,
            recent_finishes=recent_positions,
            recent_sprint_finishes=signals.recent_sprint_form.get(code, []),
            circuit_finishes=driver_circuit,
            circuit_grid_deltas=[driver_delta] if driver_delta else [],
            team_standing=team_pos,
            driver_standing=driver_standing,
        )
    )
    ml_score = _ml_finish_score(ml_features)
    measures["ml_score"] = ml_score
    if ml_score is not None:
        blend = signals.ml_blend_weight
        score = (blend * ml_score) + ((1 - blend) * heuristic_score)

    correction = signals.adaptive_corrections.get(code)
    used_adaptive = bool(correction and correction.get("samples", 0) > 0)
    if used_adaptive:
        score += signals.adaptive_weight * correction["correction"]

    confidence_low, confidence_high = _compute_confidence(
        _confidence_signals(measures, has_recent=bool(recent_positions), has_circuit=bool(driver_circuit)),
        signals.is_pre_qualifying,
    )

    heuristic_factors = _generate_factors(
        FactorInputs(
            quali_pos=quali_pos,
            recent_positions=recent_positions,
            circuit_positions=driver_circuit,
            team_pos=team_pos,
            grid_delta=driver_delta,
            is_pre_qualifying=signals.is_pre_qualifying,
            sprint_pos=sprint_pos,
        )
    )

    model_attribution: list[dict] | None = None
    model_phrases: list[str] = []
    if ml_score is not None:
        model_attribution, model_phrases = _model_reasoning(ml_features)

    factors = _build_factors(
        driver,
        heuristic_factors,
        model_phrases,
        {"ml_score": ml_score, "correction": correction},
    )

    return DriverScore(
        scored={
            "driver_code": code,
            "driver_name": driver.get("driver_name", code),
            "team": driver.get("team", ""),
            "score": score,
            "heuristic_score": heuristic_score,
            "ml_score": ml_score,
            "adaptive_correction": correction,
            "quali_pos": quali_pos,
            "sprint_pos": sprint_pos,
            "team_pos": team_pos,
            "driver_standing": driver_standing,
            "confidence_low": confidence_low,
            "confidence_high": confidence_high,
            "factors": factors,
            "model_attribution": model_attribution,
        },
        used_model=ml_score is not None,
        used_adaptive=used_adaptive,
        used_recent_form=bool(recent_positions),
    )
