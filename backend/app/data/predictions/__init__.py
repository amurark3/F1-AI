"""
Race Prediction Engine
======================
Computes probabilistic race outcome predictions for all drivers using a
weighted heuristic scoring model.  Data sources:

  - Qualifying results (or practice session data as fallback)
  - Recent form (last 5 race results per driver)
  - Circuit history (driver's results at this track, last 3 editions)
  - Team strength (constructor championship position)
  - Grid-to-finish delta (historical overtaking pattern at circuit)

Confidence ranges are expressed as percentage pairs that widen when data
signals conflict and narrow when they agree.

Thread safety: All FastF1 session loads are wrapped with the shared lock in
``fastf1_lock`` to prevent data corruption from concurrent loads.

Layout
------
The engine is split by the stage of work each module does, lowest first — a
module only ever imports from those above it, so the dependency graph is a
line rather than a web:

    version, fastf1_lock   constants and the shared FastF1 lock
    sessions               qualifying / practice / sprint results
    form                   recent form, circuit history, grid-to-finish delta
    standings              championship positions
    incidents              retirement and incident history
    scoring                score, confidence band and risk profile
    history                durable prediction history and actual results
    model                  the trained ranker and adaptive corrections
    review                 prediction vs. actual, side by side
    accuracy               rolling accuracy across recent races
    compute                the entry point that assembles all of the above

This module re-exports the public surface, so ``from app.data.predictions
import compute_race_predictions`` keeps working unchanged.
"""

from app.data.predictions.accuracy import get_accuracy_stats
from app.data.predictions.compute import (
    ADAPTIVE_CORRECTION_WEIGHT,
    ML_BLEND_WEIGHT,
    compute_race_predictions,
)
from app.data.predictions.history import (
    ACTUAL_RESULT_RETRY_SECONDS,
    _load_prediction_history,
    record_actual_result,
    save_prediction,
)
from app.data.predictions.model import MODEL_PATH, warm_model_cache
from app.data.predictions.review import (
    _latest_prediction_snapshot,
    build_prediction_review,
    get_prediction_review,
)
from app.data.predictions.scoring import safe_number
from app.data.predictions.version import PREDICTION_LOGIC_VERSION

__all__ = [
    "ACTUAL_RESULT_RETRY_SECONDS",
    "ADAPTIVE_CORRECTION_WEIGHT",
    "ML_BLEND_WEIGHT",
    "MODEL_PATH",
    "PREDICTION_LOGIC_VERSION",
    # Underscore-prefixed but re-exported: app.services.self_improvement reads
    # raw history and snapshots, which no public helper exposes.
    "_latest_prediction_snapshot",
    "_load_prediction_history",
    "build_prediction_review",
    "compute_race_predictions",
    "get_accuracy_stats",
    "get_prediction_review",
    "record_actual_result",
    "safe_number",
    "save_prediction",
    "warm_model_cache",
]
