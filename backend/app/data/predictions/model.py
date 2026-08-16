"""The trained ranking model and the adaptive corrections layered on it.

Loading is lazy and failure-tolerant: when the model file is absent or will not
load, the scorer returns None and the caller falls back to the heuristic score
alone, so a missing artefact degrades quality rather than breaking predictions.
"""

from __future__ import annotations

import os
from pathlib import Path
import statistics
from typing import Any

import structlog

from app.data.predictions.history import _load_prediction_history

logger = structlog.get_logger()

MODEL_PATH = Path(os.getenv("RACE_PREDICTOR_MODEL_PATH", "models/race_predictor.joblib"))

_ml_model_cache: dict[str, Any] | bool | None = None


def _load_ml_model() -> dict[str, Any] | None:
    """Load the trained finish-position model if runtime dependencies exist."""
    global _ml_model_cache
    if _ml_model_cache is False:
        return None
    if isinstance(_ml_model_cache, dict):
        return _ml_model_cache

    try:
        import joblib

        payload = joblib.load(MODEL_PATH)
        if isinstance(payload, dict) and payload.get("model") and payload.get("features"):
            _ml_model_cache = payload
            logger.info("predictions.ml_model_loaded", path=str(MODEL_PATH))
            return payload
    except Exception as exc:
        logger.warning("predictions.ml_model_unavailable", path=str(MODEL_PATH), error=str(exc))

    _ml_model_cache = False
    return None


def warm_model_cache() -> bool:
    """Force the finish-position model into memory ahead of the first request.

    Public entry point for the startup warm-up in ``app.services.readiness`` so it
    does not have to reach into the private loader. Returns ``True`` when a usable
    model is resident.
    """
    return _load_ml_model() is not None


def _ml_finish_score(features: dict[str, float]) -> float | None:
    payload = _load_ml_model()
    if not payload:
        return None

    model = payload["model"]
    feature_names = payload["features"]
    try:
        row = [[float(features.get(name, 0.0)) for name in feature_names]]
        prediction = model.predict(row)[0]
        return float(prediction)
    except Exception as exc:
        logger.warning("predictions.ml_inference_failed", error=str(exc))
        return None


def _ml_explanation(features: dict[str, float]) -> list[tuple[str, float]] | None:
    """Return the exact per-feature attribution for one driver's ML projection.

    Returns a list of :class:`FeatureContribution` (strongest first), or None
    when the model is unavailable or not a supported linear model.
    """
    payload = _load_ml_model()
    if not payload:
        return None
    try:
        from app.ml.explain import explain_prediction

        return explain_prediction(payload, features)
    except Exception as exc:
        logger.warning("predictions.ml_explanation_failed", error=str(exc))
        return None


def _adaptive_position_corrections() -> dict[str, dict[str, float]]:
    """Learn small driver-specific corrections from evaluated prediction misses.

    Positive correction means the model has been too optimistic and the score
    should move worse. Negative correction means the driver has usually beaten
    the model and the score can improve slightly.
    """
    history = _load_prediction_history()
    corrections: dict[str, list[float]] = {}

    for entry in history.values():
        snapshots = entry.get("snapshots")
        if not snapshots:
            snapshots = [
                {
                    "predicted_positions": entry.get("predicted_positions") or {},
                    "generated_at": entry.get("generated_at"),
                }
            ]
        actual = entry.get("actual_positions") or {}
        if not actual:
            continue

        latest = snapshots[-1] if snapshots else {}
        predicted = latest.get("predicted_positions") or entry.get("predicted_positions") or {}
        for code, predicted_pos in predicted.items():
            actual_pos = actual.get(code)
            if actual_pos is None:
                continue
            try:
                miss = float(actual_pos) - float(predicted_pos)
            except (TypeError, ValueError):
                continue
            corrections.setdefault(code, []).append(max(-6.0, min(6.0, miss)))

    return {
        code: {
            "correction": statistics.mean(values[-6:]),
            "samples": len(values[-6:]),
        }
        for code, values in corrections.items()
        if values
    }
