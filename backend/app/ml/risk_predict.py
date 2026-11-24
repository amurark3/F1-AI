"""Serving side of the fitted DNF/crash risk: features, coefficients, probabilities.

Pure and dependency-free so request-time scoring never imports numpy or sklearn.
The coefficients below are the output of ``python -m app.ml.risk_model`` (fit on
f1db 2018-2026); refit and paste them here when the backtest still passes.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

LABELS = ("dnf", "crash", "other")
FEATURES = ("crash_rate", "other_rate", "team_pos", "grid")

# Pseudo-starts that pull a thin history toward the field-wide rate.
PRIOR_STARTS = 12
PRIOR_RATES = {"dnf": 0.18, "crash": 0.07, "other": 0.11}


@dataclass(frozen=True)
class LogisticFit:
    """Standardised logistic coefficients: p = sigmoid(bias + sum(w * (x - mean) / scale))."""

    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float

    def predict(self, features: list[float]) -> float:
        z = self.bias + sum(
            w * (x - m) / s for w, x, m, s in zip(self.weights, features, self.means, self.scales, strict=True)
        )
        return 1 / (1 + math.exp(-z))


_MEANS = (0.0682779468707411, 0.09556045996915168, 5.57230298393267, 10.65646518745218)
_SCALES = (0.032329071811668636, 0.0461676277892481, 2.9226076239646184, 5.873925338285247)

FITS = {
    "dnf": LogisticFit(
        _MEANS,
        _SCALES,
        (-0.017828308667095227, 0.1806917837262536, 0.002628416225850472, 0.28096287829035343),
        -1.7409507975995382,
    ),
    "crash": LogisticFit(
        _MEANS,
        _SCALES,
        (-0.03413033683781055, 0.11688272143767377, -0.03390619371882988, 0.21960135889868312),
        -2.65077120987424,
    ),
    "other": LogisticFit(
        _MEANS,
        _SCALES,
        (5.689508374659191e-05, 0.19272247535050505, 0.04318634620438071, 0.28072618133289645),
        -2.408661150393083,
    ),
}


def shrunk_rates(starts: int, dnfs: int, crashes: int) -> dict[str, float]:
    """Incident rates pulled toward the field rate so two starts don't read as 50%."""
    counts = {"dnf": dnfs, "crash": crashes, "other": dnfs - crashes}
    return {k: (counts[k] + PRIOR_STARTS * PRIOR_RATES[k]) / (starts + PRIOR_STARTS) for k in LABELS}


def risk_features(profile: Mapping[str, Any], quali_pos: int, team_pos: int) -> list[float]:
    """The model inputs, in ``FEATURES`` order, from an incident profile and the context."""
    rates = shrunk_rates(profile["starts"], profile["dnfs"], profile["crashes"])
    return [rates["crash"], rates["other"], float(team_pos), float(quali_pos)]


def risk_probabilities(profile: Mapping[str, Any], quali_pos: int, team_pos: int) -> dict[str, float]:
    """Calibrated ``{dnf, crash, other}`` probabilities for one driver-race."""
    features = risk_features(profile, quali_pos, team_pos)
    return {label: FITS[label].predict(features) for label in LABELS}
