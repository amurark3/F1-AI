"""Race prediction REST routes."""

import asyncio
from functools import partial
import secrets
import threading

from fastapi import APIRouter, Depends, Header, HTTPException, Query
import structlog

from app.api.errors import client_error
from app.api.single_flight import SingleFlight
from app.config import FASTF1_TIMEOUT_SECONDS, PREDICTIONS_ADMIN_KEY
from app.data.predictions import (
    PHASE_POST_QUALIFYING,
    PHASE_PRE_QUALIFYING,
    get_prediction_review,
    normalise_phase,
)
from app.services.predictions import (
    compute_and_store_race_prediction,
    get_cached_race_prediction,
)

logger = structlog.get_logger()
router = APIRouter(tags=["predictions"])

# A model run in flight, keyed by race and by which call it is computing: a
# phase name, or "auto" when the data picks the phase. A retry joins the run
# instead of stacking a second one beside it.
model_runs: SingleFlight[dict] = SingleFlight("predictions")
# One model run at a time across every race: two side by side ran the 512 MB
# worker out of memory.
_model_lock = threading.Lock()
AUTO_PHASE_RUN = "auto"
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


def _compute_one_at_a_time(year: int, round_num: int, reason: str, phase: str | None) -> dict:
    """Run the model with no other run beside it, on any race or phase."""
    with _model_lock:
        return compute_and_store_race_prediction(year, round_num, reason=reason, phase=phase)


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
    running = model_runs.running((year, round_num, wanted or AUTO_PHASE_RUN))
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


def require_admin_key(x_admin_key: str = Header("")) -> None:
    """Refuse a compute unless it carries the owner's key; no key configured refuses all."""
    if not PREDICTIONS_ADMIN_KEY or not secrets.compare_digest(x_admin_key, PREDICTIONS_ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Predictions are computed by the site owner only.")


@router.post("/predictions/{year}/{round_num}/compute", dependencies=[Depends(require_admin_key)])
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

    try:
        result = await model_runs.run(
            (year, round_num, wanted or AUTO_PHASE_RUN),
            partial(_compute_one_at_a_time, year, round_num, reason, wanted),
            FASTF1_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return {
            **empty,
            **client_error("api.predictions.compute_error", exc, year=year, round=round_num, reason=reason),
        }

    if result is None:
        logger.info("api.predictions.compute_still_running", year=year, round=round_num, reason=reason, phase=wanted)
        return {**empty, "cache": {"status": "computing", "policy": "stored_until_manual_recompute"}}
    return result
