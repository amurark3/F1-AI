"""Shared feature engineering for the race-finish model.

Single source of truth for turning raw driver-race signals into the numeric
feature vector consumed by the GradientBoosting finish model. Both the offline
training pipeline (``app.ml.train``) and the live inference path
(``app.data.predictions``) import :func:`build_feature_row` from here, so the
model is always served the exact feature definitions it was trained on.

Keeping this logic in one place prevents train/serve skew: the aggregation
windows and the fallback values below are part of the feature contract and must
be identical on both sides.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Feature order is the model's contract — the trained estimator expects columns
# in exactly this sequence.
FEATURES: list[str] = [
    "grid_position",
    "sprint_position",
    "had_sprint",
    "recent_form_avg",
    "recent_sprint_avg",
    "circuit_avg",
    "team_standing",
    "driver_standing",
    "grid_delta_avg",
]
TARGET = "finish_position"

# Fallback values applied when a signal is unavailable for a driver. These are
# part of the feature contract: training and inference MUST agree on them, so
# they live here rather than at either call site.
GRID_FALLBACK = 15.0
STANDING_FALLBACK = 10.0
RECENT_FORM_FALLBACK = 10.0
CIRCUIT_FALLBACK = 10.0
RECENT_SPRINT_FALLBACK = 0.0
GRID_DELTA_FALLBACK = 0.0

# Rolling windows (most recent entries kept).
RECENT_FORM_WINDOW = 5
RECENT_SPRINT_WINDOW = 3


def _mean_or(
    values: Sequence[float] | None,
    default: float,
    window: int | None = None,
) -> float:
    """Mean of the (optionally last-``window``) values, or ``default`` if empty."""
    if not values:
        return default
    window_values = list(values)[-window:] if window else list(values)
    if not window_values:
        return default
    return float(statistics.mean(window_values))


@dataclass(frozen=True)
class DriverSignals:
    """Raw per-driver signals for one race, before they become a feature vector.

    The signal set is half of the feature contract, so it is a named type rather
    than a loose argument list: training accumulates these chronologically while
    inference queries them live, and a field either side forgets to supply is a
    train/serve skew that a flat signature would have hidden behind a default.

    Every field is optional because absence is meaningful — the fallbacks in
    :func:`build_feature_row` are what the model was trained to expect.
    """

    grid_position: float | None = None
    sprint_position: float | None = None
    had_sprint: bool = False
    recent_finishes: Sequence[int] | None = None
    recent_sprint_finishes: Sequence[int] | None = None
    circuit_finishes: Sequence[int] | None = None
    circuit_grid_deltas: Sequence[float] | None = None
    team_standing: float | None = None
    driver_standing: float | None = None


def build_feature_row(signals: DriverSignals) -> dict[str, float]:
    """Assemble the model feature dict from raw per-driver signals.

    Both training and inference gather these raw signals their own way (batch
    chronological accumulation vs. live API queries) but funnel them through
    this function so the resulting feature vector is identical.
    """
    return {
        "grid_position": float(signals.grid_position) if signals.grid_position is not None else GRID_FALLBACK,
        "sprint_position": float(signals.sprint_position) if signals.sprint_position is not None else 0.0,
        "had_sprint": 1.0 if signals.had_sprint else 0.0,
        "recent_form_avg": _mean_or(signals.recent_finishes, RECENT_FORM_FALLBACK, RECENT_FORM_WINDOW),
        "recent_sprint_avg": _mean_or(signals.recent_sprint_finishes, RECENT_SPRINT_FALLBACK, RECENT_SPRINT_WINDOW),
        "circuit_avg": _mean_or(signals.circuit_finishes, CIRCUIT_FALLBACK),
        "team_standing": float(signals.team_standing) if signals.team_standing is not None else STANDING_FALLBACK,
        "driver_standing": (
            float(signals.driver_standing) if signals.driver_standing is not None else STANDING_FALLBACK
        ),
        "grid_delta_avg": _mean_or(signals.circuit_grid_deltas, GRID_DELTA_FALLBACK),
    }


def feature_vector(row: dict[str, float]) -> list[float]:
    """Order a feature dict into the model's expected input row."""
    return [float(row.get(name, 0.0)) for name in FEATURES]
