"""Prediction application service."""

from __future__ import annotations

from app.data.predictions import build_prediction_review, compute_race_predictions
from app.services.prediction_cache import prediction_snapshot_cache


def get_cached_race_prediction(year: int, round_num: int) -> dict | None:
    """Return a stored race prediction snapshot without computing a new one."""

    cached = prediction_snapshot_cache.get(year, round_num)
    return enrich_prediction_result(cached) if cached else None


def compute_and_store_race_prediction(
    year: int,
    round_num: int,
    *,
    reason: str = "manual_compute",
) -> dict:
    """Compute a fresh race prediction snapshot and store it as the active version."""

    result = compute_race_predictions(year, round_num)
    if result.get("predictions"):
        return enrich_prediction_result(prediction_snapshot_cache.set(year, round_num, result, reason=reason))
    return enrich_prediction_result(result)


def get_or_compute_race_prediction(year: int, round_num: int) -> dict:
    """Return a cached race prediction snapshot, computing it on first use."""

    cached = prediction_snapshot_cache.get(year, round_num)
    if cached:
        return enrich_prediction_result(cached)

    return compute_and_store_race_prediction(year, round_num, reason="first_compute")


def enrich_prediction_result(result: dict) -> dict:
    """Add web-oriented transparency without changing the core prediction contract."""

    enriched = dict(result)
    predictions = enriched.get("predictions") or []
    risk_predictions = enriched.get("risk_predictions") or []
    sources = set(enriched.get("data_sources") or [])
    warnings = enriched.get("warnings") or []
    top_three = predictions[:3]

    confidence_values = [
        round((safe_number(row.get("confidence_low")) + safe_number(row.get("confidence_high"))) / 2)
        for row in top_three
    ]
    leader = predictions[0] if predictions else None

    enriched["model_summary"] = {
        "leader": leader.get("driver_name") if leader else None,
        "leader_code": leader.get("driver_code") if leader else None,
        "average_top3_confidence": round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else None,
        "source_count": len(sources),
        "status": "ready" if predictions else "data_unavailable",
        "snapshot_policy": "Stored race predictions stay fixed until a manual compute or qualifying recompute is requested.",
        "risk_count": len(risk_predictions),
    }
    enriched["model_inputs"] = [
        input_card(
            "Trained finish model",
            "available" if "trained_ml_model" in sources else "fallback",
            "Blends the historical GradientBoosting finish model with heuristic race signals.",
            "backend/models/race_predictor.joblib" if "trained_ml_model" in sources else "heuristic-only path",
        ),
        input_card(
            "Qualifying / practice pace",
            "available" if {"qualifying", "practice"} & sources else "missing",
            "Sets the launch-risk and opening-stint baseline.",
            "Main qualifying order" if "qualifying" in sources else "practice timing proxy" if "practice" in sources else "not loaded",
        ),
        input_card(
            "Recent form",
            "available" if "last_5_races" in sources else "fallback",
            "Keeps the forecast anchored to current finishing momentum.",
            "last five classified race results" if "last_5_races" in sources else "historical finishing prior",
        ),
        input_card(
            "Circuit history",
            "available" if "circuit_history" in sources else "limited",
            "Adds track-specific performance and grid-to-finish tendencies.",
            "driver history at this venue" if "circuit_history" in sources else "generic circuit-type prior",
        ),
        input_card(
            "Constructor strength",
            "available" if "constructor_standings" in sources else "missing",
            "Adds team-level pace/reliability context.",
            "constructor championship order" if "constructor_standings" in sources else "not loaded",
        ),
        input_card(
            "Sprint signal",
            "available" if "sprint_result" in sources else "not applicable",
            "Tightens confidence if same-weekend sprint race data exists.",
            "sprint classification" if "sprint_result" in sources else "no sprint result",
        ),
        input_card(
            "Adaptive correction",
            "available" if "adaptive_history" in sources else "limited",
            "Learns from prior over- and under-predictions as race results are reviewed.",
            "prediction history review" if "adaptive_history" in sources else "waiting for more evaluated races",
        ),
        input_card(
            "DNF / crash risk",
            "available" if risk_predictions else "limited",
            "Separates retirement and accident risk from finishing-order prediction.",
            "recent status history and grid traffic bands" if risk_predictions else "not generated",
        ),
    ]
    enriched["model_limitations"] = [
        "Forecasts are probabilistic scenario calls, not live timing telemetry.",
        "Weather and safety-car outcomes are not live stochastic simulations in this model.",
        "Stored snapshots intentionally do not change until a manual compute or recompute.",
        *warnings[:2],
    ]
    enriched["risk_predictions"] = risk_predictions

    # A snapshot is frozen at compute time, so a prediction made before the race
    # carries an unevaluated review forever. Rebuild it from stored history
    # (no network) until it has actually been scored.
    review = enriched.get("prediction_review") or {}
    if predictions and not review.get("evaluated"):
        enriched["prediction_review"] = build_prediction_review(
            int(enriched.get("year", 0)),
            int(enriched.get("round", 0)),
        )
    return enriched


def input_card(label: str, status: str, impact: str, source: str) -> dict:
    return {"label": label, "status": status, "impact": impact, "source": source}


def safe_number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
