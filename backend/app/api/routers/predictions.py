"""Race prediction REST routes."""

import asyncio

import structlog
from fastapi import APIRouter, Query

from app.config import FASTF1_TIMEOUT_SECONDS
from app.services.predictions import (
    compute_and_store_race_prediction,
    enrich_prediction_result,
    get_cached_race_prediction,
    get_or_compute_race_prediction,
)
from app.services.prediction_cache import prediction_snapshot_cache

logger = structlog.get_logger()
router = APIRouter(tags=["predictions"])
prediction_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _prediction_lock(cache_key: tuple[int, int]) -> asyncio.Lock:
    lock = prediction_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        prediction_locks[cache_key] = lock
    return lock


@router.get("/predictions/{year}/{round_num}")
async def get_predictions(year: int, round_num: int):
    """Returns structured race predictions for existing web and mobile clients.

    This legacy route computes on a cache miss for backwards compatibility.
    Use ``/snapshot`` when a client must not trigger model work.
    """

    cache_key = (year, round_num)
    cached = prediction_snapshot_cache.get(year, round_num)
    if cached:
        return enrich_prediction_result(cached)

    async with _prediction_lock(cache_key):
        cached = prediction_snapshot_cache.get(year, round_num)
        if cached:
            return enrich_prediction_result(cached)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(get_or_compute_race_prediction, year, round_num),
                timeout=FASTF1_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("api.predictions.timeout", year=year, round=round_num)
            return {"year": year, "round": round_num, "predictions": [], "error": "Prediction data source timed out. Try again shortly."}
        except Exception as exc:
            logger.error("api.predictions.error", year=year, round=round_num, error=str(exc))
            return {"year": year, "round": round_num, "predictions": [], "error": str(exc)}

        return result


@router.get("/predictions/{year}/{round_num}/snapshot")
async def get_prediction_snapshot(year: int, round_num: int):
    """Return a stored prediction snapshot without generating a new one."""

    cached = get_cached_race_prediction(year, round_num)
    if cached:
        return cached
    return {
        "year": year,
        "round": round_num,
        "predictions": [],
        "risk_predictions": [],
        "error": "No stored prediction snapshot. Run the model to create one.",
        "cache": {"status": "missing", "policy": "stored_until_manual_recompute"},
    }


@router.get("/predictions/{year}/{round_num}/postmortem")
async def get_prediction_postmortem(year: int, round_num: int):
    """Return the LLM post-mortem for a completed race, generating it on demand."""
    from app.services.self_improvement import generate_miss_postmortem, get_postmortem

    existing = get_postmortem(year, round_num)
    if existing:
        return existing

    result = await asyncio.to_thread(generate_miss_postmortem, year, round_num)
    if result:
        return result
    return {
        "year": year,
        "round": round_num,
        "available": False,
        "reason": "Race not evaluated yet (no actual result) or LLM engine unavailable.",
    }


@router.post("/predictions/{year}/{round_num}/compute")
async def compute_predictions(
    year: int,
    round_num: int,
    reason: str = Query("manual_compute"),
):
    """Compute and store a fresh prediction snapshot on explicit request."""

    cache_key = (year, round_num)
    if reason not in {"manual_compute", "qualifying_recompute"}:
        reason = "manual_compute"

    async with _prediction_lock(cache_key):
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(compute_and_store_race_prediction, year, round_num, reason=reason),
                timeout=FASTF1_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("api.predictions.compute_timeout", year=year, round=round_num, reason=reason)
            return {"year": year, "round": round_num, "predictions": [], "risk_predictions": [], "error": "Prediction data source timed out. Try again shortly."}
        except Exception as exc:
            logger.error("api.predictions.compute_error", year=year, round=round_num, reason=reason, error=str(exc))
            return {"year": year, "round": round_num, "predictions": [], "risk_predictions": [], "error": str(exc)}

        return result
