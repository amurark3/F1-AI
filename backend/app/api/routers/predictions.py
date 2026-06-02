"""Race prediction REST routes."""

import asyncio

import structlog
from fastapi import APIRouter

from app.config import FASTF1_TIMEOUT_SECONDS
from app.services.predictions import enrich_prediction_result, get_or_compute_race_prediction
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
    """Returns structured race predictions for web and mobile clients."""

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
