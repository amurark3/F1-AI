"""Startup warm-up and readiness reporting.

Render's free tier spins the container down after idle, and this app deliberately
defers its expensive imports out of module scope — ``joblib`` is imported inside
``_load_ml_model``, the f1db SQLite file is downloaded on first ``connect()`` —
so the process boots in well under a second and stays inside the free tier's
memory ceiling.

That trade has a cost: the server accepts connections long before it can actually
answer a data request. ``/api/health`` reports the first condition (the process is
alive); this module reports the second (the process can do useful work). The
warm-up runs once on startup in the background, paying those deferred costs before
a visitor asks for them rather than during their first page load.

State is a frozen snapshot replaced wholesale under a lock, so readers never see a
half-updated record and never need to copy defensively.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import structlog

from app.config import WARMUP_STEP_TIMEOUT_SECONDS

logger = structlog.get_logger()

STAGE_PENDING = "pending"
STAGE_COMPLETE = "complete"


@dataclass(frozen=True)
class WarmupStep:
    """One unit of deferred startup work."""

    stage: str
    detail: str
    run: Callable[[], None]


@dataclass(frozen=True)
class ReadinessState:
    """Immutable snapshot of how far warm-up has progressed."""

    ready: bool
    stage: str
    detail: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "stage": self.stage,
            "detail": self.detail,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_INITIAL_STATE = ReadinessState(
    ready=False,
    stage=STAGE_PENDING,
    detail="Server starting up",
)

_state: ReadinessState = _INITIAL_STATE
_lock = threading.Lock()


def current_state() -> ReadinessState:
    """Return the current readiness snapshot."""
    with _lock:
        return _state


def _set_state(state: ReadinessState) -> None:
    """Replace the readiness snapshot. Never mutates the previous one."""
    global _state
    with _lock:
        _state = state


# ---------------------------------------------------------------------------
# Warm-up steps
#
# The imports below are deliberately function-local. They are exactly the
# deferred costs this module exists to pay early — hoisting them to module scope
# would reintroduce the boot-time memory spike that lazy-loading fixed.
# ---------------------------------------------------------------------------


def _warm_database() -> None:
    """Download the f1db SQLite file if the ephemeral disk lost it."""
    from app.data.f1db_source import ensure_db

    ensure_db()


def _warm_model() -> None:
    """Pull joblib and the trained finish-position model into memory."""
    from app.data.predictions import warm_model_cache

    warm_model_cache()


def _warm_season() -> None:
    """Run one real query so the SQLite handle and schedule path are hot."""
    from app.data.f1db_results import race_schedule

    race_schedule(datetime.now(timezone.utc).year)


def _warm_store() -> None:
    """Load stored prediction snapshots, establishing document-store health.

    Doing this here rather than on first request means a store outage shows up
    in ``/api/ready`` instead of as a page that quietly renders no predictions.
    """
    from app.services.prediction_cache import prediction_snapshot_cache

    if not prediction_snapshot_cache.load():
        raise RuntimeError("prediction snapshot store unreachable")


WARMUP_STEPS: tuple[WarmupStep, ...] = (
    WarmupStep("database", "Fetching the historical race database", _warm_database),
    WarmupStep("model", "Loading the race prediction model", _warm_model),
    WarmupStep("season", "Priming this season's schedule", _warm_season),
    WarmupStep("store", "Loading stored prediction snapshots", _warm_store),
)


async def run_warmup(steps: tuple[WarmupStep, ...] = WARMUP_STEPS) -> ReadinessState:
    """Run every warm-up step in order, publishing progress as it goes.

    Each step is bounded by ``WARMUP_STEP_TIMEOUT_SECONDS`` and runs in a worker
    thread because all of them block. A step that fails or times out is logged and
    skipped rather than aborting the run — a partially warm server still serves
    requests, and leaving ``ready`` false forever would strand the client behind a
    banner that never clears. The failure is surfaced on the state so the outcome
    is visible rather than silently swallowed.
    """
    started_at = _now()
    _set_state(
        ReadinessState(
            ready=False,
            stage=steps[0].stage if steps else STAGE_COMPLETE,
            detail=steps[0].detail if steps else "Ready",
            started_at=started_at,
        )
    )
    logger.info("warmup.starting", steps=[step.stage for step in steps])

    first_error: str | None = None

    for step in steps:
        _set_state(
            ReadinessState(
                ready=False,
                stage=step.stage,
                detail=step.detail,
                started_at=started_at,
                error=first_error,
            )
        )
        try:
            await asyncio.wait_for(
                asyncio.to_thread(step.run),
                timeout=WARMUP_STEP_TIMEOUT_SECONDS,
            )
            logger.info("warmup.step_done", stage=step.stage)
        except asyncio.TimeoutError:
            first_error = first_error or f"{step.stage} timed out"
            logger.warning(
                "warmup.step_timeout", stage=step.stage, timeout=WARMUP_STEP_TIMEOUT_SECONDS
            )
        except Exception as exc:
            first_error = first_error or f"{step.stage} failed: {exc}"
            logger.error("warmup.step_failed", stage=step.stage, error=str(exc))

    final = ReadinessState(
        ready=True,
        stage=STAGE_COMPLETE,
        detail="Ready",
        started_at=started_at,
        completed_at=_now(),
        error=first_error,
    )
    _set_state(final)
    logger.info("warmup.complete", degraded=bool(first_error), error=first_error)
    return final
