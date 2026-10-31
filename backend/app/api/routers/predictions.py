"""Race prediction REST routes."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial

from fastapi import APIRouter, Query
import structlog

from app.api.errors import client_error
from app.config import FASTF1_TIMEOUT_SECONDS
from app.data.predictions import (
    PHASE_POST_QUALIFYING,
    PHASE_PRE_QUALIFYING,
    get_prediction_review,
    normalise_phase,
)
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

# A model run in flight, keyed by race and by which call it is computing: a
# phase name, "auto" when the data picks the phase, or the legacy first compute.
RunKey = tuple[int, int, str]
model_runs: dict[RunKey, asyncio.Task[dict]] = {}
AUTO_PHASE_RUN = "auto"
FIRST_COMPUTE_RUN = "first_compute"
STILL_RUNNING_MESSAGE = "The model is still running. Try again in a minute."

# How long a request waits for a post-race result load before serving the
# snapshot as-is. Kept short: the page must stay fast, and a slower load still
# finishes in the background and lands on the next request.
REVIEW_REFRESH_TIMEOUT_SECONDS = 4.0


_MISSING_SNAPSHOT_BY_PHASE = {
    PHASE_PRE_QUALIFYING: "No stored pre-qualifying prediction. Run the model to create one.",
    PHASE_POST_QUALIFYING: "No stored post-qualifying prediction. Run the model to create one.",
}


def _missing_snapshot_message(phase: str | None) -> str:
    """Name the tab that is empty, so the client does not report both as missing."""
    return _MISSING_SNAPSHOT_BY_PHASE.get(phase or "", "No stored prediction snapshot. Run the model to create one.")


def _prediction_lock(cache_key: tuple[int, int]) -> asyncio.Lock:
    lock = prediction_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        prediction_locks[cache_key] = lock
    return lock


def _start_model_run(key: RunKey, work: Callable[[], Awaitable[dict]]) -> asyncio.Task[dict]:
    """The run for ``key`` already in flight, or a newly started one.

    A run is a task of its own, not part of the request that started it. A
    request that stops waiting leaves the run to finish, store its snapshot and
    only then release the race. A request that arrives meanwhile joins the run,
    so a retry never stacks a second full model run beside the first — on a
    512 MB instance that is what ran the worker out of memory.
    """
    run = model_runs.get(key)
    if run is None:
        run = asyncio.create_task(work())
        model_runs[key] = run
        run.add_done_callback(partial(_forget_model_run, key))
    return run


def _forget_model_run(key: RunKey, run: asyncio.Task[dict]) -> None:
    """Drop a finished run, logging a failure no request may have stayed to see."""
    model_runs.pop(key, None)
    if run.cancelled():
        return
    error = run.exception()
    if error:
        logger.warning("api.predictions.model_run_failed", year=key[0], round=key[1], run=key[2], error=str(error))


async def _wait_for_model_run(run: asyncio.Task[dict]) -> dict | None:
    """The run's result, or ``None`` when it is still going as this request's wait ends.

    ``shield`` is what lets the wait end without cancelling the run. A
    ``TimeoutError`` from a run that has already finished is the run's own
    failure (a socket timeout, say), so it is raised, not read as a slow run.
    """
    try:
        return await asyncio.wait_for(asyncio.shield(run), timeout=FASTF1_TIMEOUT_SECONDS)
    except TimeoutError:
        if run.done():
            return run.result()
        return None


async def _get_or_compute_under_race_lock(year: int, round_num: int) -> dict:
    async with _prediction_lock((year, round_num)):
        cached = prediction_snapshot_cache.get(year, round_num)
        if cached:
            return await _with_scored_review(enrich_prediction_result(cached))
        return await asyncio.to_thread(get_or_compute_race_prediction, year, round_num)


async def _compute_under_race_lock(year: int, round_num: int, reason: str, phase: str | None) -> dict:
    async with _prediction_lock((year, round_num)):
        return await asyncio.to_thread(compute_and_store_race_prediction, year, round_num, reason=reason, phase=phase)


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

    task = asyncio.create_task(
        asyncio.to_thread(get_prediction_review, year, round_num, result.get("prediction_phase"))
    )
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

    cached = prediction_snapshot_cache.get(year, round_num)
    if cached:
        return await _with_scored_review(enrich_prediction_result(cached))

    run = _start_model_run(
        (year, round_num, FIRST_COMPUTE_RUN),
        partial(_get_or_compute_under_race_lock, year, round_num),
    )
    try:
        result = await _wait_for_model_run(run)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "predictions": [],
            **client_error("api.predictions.error", exc, year=year, round=round_num),
        }

    if result is None:
        logger.warning("api.predictions.still_running", year=year, round=round_num)
        return {"year": year, "round": round_num, "predictions": [], "error": STILL_RUNNING_MESSAGE}
    return result


@router.get("/predictions/{year}/{round_num}/snapshot")
async def get_prediction_snapshot(
    year: int,
    round_num: int,
    phase: str | None = Query(None),
) -> dict:
    """Return a stored prediction snapshot without generating a new one.

    ``phase`` selects one of the two stored calls for the race. Omitting it
    returns the most recently stored one, which is what clients written before
    phases existed expect.

    ``model_running`` says whether a compute for that phase is still in flight,
    so a client waiting on a "computing" answer can tell a slow run (keep
    waiting) from one that ended without storing anything (stop and say so).
    """

    wanted = normalise_phase(phase)
    running = (year, round_num, wanted or AUTO_PHASE_RUN) in model_runs
    cached = get_cached_race_prediction(year, round_num, phase=wanted)
    if cached:
        return {**(await _with_scored_review(cached)), "model_running": running}
    return {
        "model_running": running,
        "year": year,
        "round": round_num,
        "predictions": [],
        "risk_predictions": [],
        "prediction_phase": wanted,
        "error": _missing_snapshot_message(wanted),
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
    phase: str | None = Query(None),
) -> dict:
    """Compute and store a fresh prediction snapshot on explicit request.

    ``phase`` recomputes just that one of the race's two stored calls; the other
    is left untouched, so refreshing one tab never clears the other.

    A run that outlasts the wait answers ``cache.status == "computing"``: the run
    carries on and stores its snapshot, which the client then picks up from
    ``/snapshot``. Posting again meanwhile joins that run instead of starting one.
    """

    if reason not in {"manual_compute", "qualifying_recompute"}:
        reason = "manual_compute"
    wanted = normalise_phase(phase)
    empty = {"year": year, "round": round_num, "predictions": [], "risk_predictions": [], "prediction_phase": wanted}

    run = _start_model_run(
        (year, round_num, wanted or AUTO_PHASE_RUN),
        partial(_compute_under_race_lock, year, round_num, reason, wanted),
    )
    try:
        result = await _wait_for_model_run(run)
    except Exception as exc:
        return {
            **empty,
            **client_error("api.predictions.compute_error", exc, year=year, round=round_num, reason=reason),
        }

    if result is None:
        logger.info("api.predictions.compute_still_running", year=year, round=round_num, reason=reason, phase=wanted)
        return {**empty, "cache": {"status": "computing", "policy": "stored_until_manual_recompute"}}
    return result
