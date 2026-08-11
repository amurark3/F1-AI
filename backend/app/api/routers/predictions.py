"""Race prediction REST routes."""

import asyncio

from fastapi import APIRouter, Query
import structlog

from app.api.errors import client_error
from app.config import FASTF1_TIMEOUT_SECONDS
from app.data.predictions import get_prediction_review
from app.services.prediction_cache import prediction_snapshot_cache
from app.services.predictions import (
    compute_and_store_race_prediction,
    enrich_prediction_result,
    get_cached_race_prediction,
    get_or_compute_race_prediction,
)

logger = structlog.get_logger()
router = APIRouter(tags=["predictions"])
prediction_locks: dict[tuple[int, int], asyncio.Lock] = {}

# How long a request waits for a post-race result load before serving the
# snapshot as-is. Kept short: the page must stay fast, and a slower load still
# finishes in the background and lands on the next request.
REVIEW_REFRESH_TIMEOUT_SECONDS = 4.0


def _prediction_lock(cache_key: tuple[int, int]) -> asyncio.Lock:
    lock = prediction_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        prediction_locks[cache_key] = lock
    return lock


def _log_late_review(task: asyncio.Task) -> None:
    """Drain a review refresh that outran its wait, so failures are not silent."""
    if task.cancelled():
        return
    error = task.exception()
    if error:
        logger.warning("api.predictions.review_refresh_failed", error=str(error))
    else:
        logger.info("api.predictions.review_refreshed_late")


async def _with_scored_review(result: dict) -> dict:
    """Score a stored snapshot against the actual result once the race has run.

    The stored review is whatever was known when the snapshot was computed —
    for a pre-race prediction, "not available yet". Fetching the result is a
    FastF1 load, so it runs off the event loop and only blocks briefly.
    """
    review = result.get("prediction_review") or {}
    if review.get("evaluated") or not result.get("predictions"):
        return result

    year = int(result.get("year") or 0)
    round_num = int(result.get("round") or 0)
    if not year or not round_num:
        return result

    task = asyncio.create_task(asyncio.to_thread(get_prediction_review, year, round_num))
    done, _pending = await asyncio.wait({task}, timeout=REVIEW_REFRESH_TIMEOUT_SECONDS)
    if task not in done:
        task.add_done_callback(_log_late_review)
        return result

    try:
        return {**result, "prediction_review": task.result()}
    except Exception as exc:
        logger.warning(
            "api.predictions.review_refresh_failed",
            year=year,
            round=round_num,
            error=str(exc),
        )
        return result


@router.get("/predictions/{year}/{round_num}")
async def get_predictions(year: int, round_num: int) -> dict:
    """Returns structured race predictions for existing web and mobile clients.

    This legacy route computes on a cache miss for backwards compatibility.
    Use ``/snapshot`` when a client must not trigger model work.
    """

    cache_key = (year, round_num)
    cached = prediction_snapshot_cache.get(year, round_num)
    if cached:
        return await _with_scored_review(enrich_prediction_result(cached))

    async with _prediction_lock(cache_key):
        cached = prediction_snapshot_cache.get(year, round_num)
        if cached:
            return await _with_scored_review(enrich_prediction_result(cached))

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(get_or_compute_race_prediction, year, round_num),
                timeout=FASTF1_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("api.predictions.timeout", year=year, round=round_num)
            return {
                "year": year,
                "round": round_num,
                "predictions": [],
                "error": "Prediction data source timed out. Try again shortly.",
            }
        except Exception as exc:
            return {
                "year": year,
                "round": round_num,
                "predictions": [],
                **client_error("api.predictions.error", exc, year=year, round=round_num),
            }

        return result


@router.get("/predictions/{year}/{round_num}/snapshot")
async def get_prediction_snapshot(year: int, round_num: int) -> dict:
    """Return a stored prediction snapshot without generating a new one."""

    cached = get_cached_race_prediction(year, round_num)
    if cached:
        return await _with_scored_review(cached)
    return {
        "year": year,
        "round": round_num,
        "predictions": [],
        "risk_predictions": [],
        "error": "No stored prediction snapshot. Run the model to create one.",
        "cache": {"status": "missing", "policy": "stored_until_manual_recompute"},
    }


@router.get("/predictions/{year}/{round_num}/postmortem")
async def get_prediction_postmortem(year: int, round_num: int) -> dict:
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
) -> dict:
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
            return {
                "year": year,
                "round": round_num,
                "predictions": [],
                "risk_predictions": [],
                "error": "Prediction data source timed out. Try again shortly.",
            }
        except Exception as exc:
            return {
                "year": year,
                "round": round_num,
                "predictions": [],
                "risk_predictions": [],
                **client_error("api.predictions.compute_error", exc, year=year, round=round_num, reason=reason),
            }

        return result
