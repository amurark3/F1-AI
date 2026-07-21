"""Exact per-feature attribution for the linear race-finish model.

The production model is a ``StandardScaler -> Ridge`` pipeline, so its
prediction decomposes *exactly* into a sum of per-feature contributions:

    predicted_finish = intercept + Σ_i  coef_i * (x_i - mean_i) / scale_i

Each term ``coef_i * z_i`` is that feature's signed contribution in
finishing-position units.  Because the model is linear this attribution is
exact — not a sampled approximation like SHAP for tree ensembles.

Sign convention (TARGET is finish_position, where 1 = best):
  * contribution < 0  → pulls the predicted finish lower → HELPS the driver
  * contribution > 0  → pushes the predicted finish higher → HURTS the driver
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ml.features import FEATURES

# Human-readable labels for each model feature.
FEATURE_LABELS: dict[str, str] = {
    "grid_position": "grid position",
    "sprint_position": "sprint result",
    "had_sprint": "sprint weekend",
    "recent_form_avg": "recent form",
    "recent_sprint_avg": "recent sprint form",
    "circuit_avg": "circuit history",
    "team_standing": "car/team strength",
    "driver_standing": "championship standing",
    "grid_delta_avg": "overtaking record here",
}

# Contributions smaller than this (in position units) are treated as noise.
_MIN_MEANINGFUL_CONTRIBUTION = 0.15


@dataclass(frozen=True)
class FeatureContribution:
    """One feature's exact signed effect on the predicted finishing position."""

    feature: str
    label: str
    value: float          # raw (pre-scaling) feature value
    contribution: float   # signed, in finishing-position units (negative = helps)


def _unwrap(model) -> tuple[object | None, object]:
    """Return (scaler_or_None, final_estimator) from a pipeline or bare estimator."""
    if hasattr(model, "named_steps"):
        steps = list(model.named_steps.values())
        scaler = next(
            (s for s in steps if hasattr(s, "mean_") and hasattr(s, "scale_")), None
        )
        return scaler, steps[-1]
    return None, model


def explain_prediction(
    payload: dict, features: dict[str, float]
) -> list[FeatureContribution] | None:
    """Decompose one prediction into exact per-feature contributions.

    Returns contributions sorted by absolute impact (strongest first), or
    ``None`` if the loaded model is not a supported linear model.
    """
    model = payload.get("model")
    feature_names = payload.get("features") or FEATURES
    if model is None:
        return None

    scaler, final = _unwrap(model)
    coef = getattr(final, "coef_", None)
    if coef is None:
        return None  # non-linear estimator — no exact linear attribution

    contributions: list[FeatureContribution] = []
    for i, name in enumerate(feature_names):
        raw = float(features.get(name, 0.0))
        if scaler is not None:
            mean = float(scaler.mean_[i])
            scale = float(scaler.scale_[i]) or 1.0
            z = (raw - mean) / scale
        else:
            z = raw
        contributions.append(
            FeatureContribution(
                feature=name,
                label=FEATURE_LABELS.get(name, name),
                value=raw,
                contribution=float(coef[i]) * z,
            )
        )

    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    return contributions


def attribution_dicts(contributions: list[FeatureContribution]) -> list[dict]:
    """Serialize contributions to plain dicts for API/model consumption."""
    return [
        {
            "feature": c.feature,
            "label": c.label,
            "value": round(c.value, 2),
            "contribution": round(c.contribution, 3),
            "direction": "helps" if c.contribution < 0 else "hurts",
        }
        for c in contributions
    ]


def attribution_phrases(
    contributions: list[FeatureContribution], top_n: int = 2
) -> list[str]:
    """Turn the strongest contributions into short human phrases.

    Skips near-zero contributions.  Phrases read from the driver's point of
    view: a helpful feature "lifts" the projection, a harmful one "drags" it.
    """
    phrases: list[str] = []
    for c in contributions:
        if abs(c.contribution) < _MIN_MEANINGFUL_CONTRIBUTION:
            continue
        verb = "lifts" if c.contribution < 0 else "drags"
        places = round(abs(c.contribution), 1)
        unit = "place" if places == 1.0 else "places"
        phrases.append(f"{c.label.capitalize()} {verb} the projection ~{places:.1f} {unit}")
        if len(phrases) >= top_n:
            break
    return phrases
