"""
F1 AI Backend — Entry Point
============================
Boots the FastAPI application, configures CORS, and mounts the API router.

Environment variables (place in a .env file in this directory — see .env.example):
  GROQ_API_KEY    — Groq API key. REQUIRED — authenticates the LLM engine.
  TAVILY_API_KEY  — Tavily web-search API key (optional).
  DATABASE_URL    — Postgres + pgvector for memory/durable store (optional).

The Groq model itself is not an environment variable: it is defined in code as
GROQ_MODEL_NAME in app/config.py.
"""

from dotenv import load_dotenv

# Load .env BEFORE any other local imports so os.getenv() works everywhere.
load_dotenv()

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import fastf1
import pandas as pd
import structlog

from app.api import race_detail, routes
from app.config import (
    F1DB_REFRESH_INTERVAL_SECONDS,
    PREFETCH_INTER_RACE_DELAY,
    PREFETCH_INTERVAL,
    PREFETCH_RACE_TIMEOUT_SECONDS,
    PREFETCH_STARTUP_DELAY,
)
from app.data.f1db_source import sync_to_latest
from app.error_tracking import init_error_tracking
from app.logging_config import setup_logging
from app.services.readiness import run_warmup

logger = structlog.get_logger()


def _race_session_date(row: pd.Series) -> datetime | None:
    """UTC start of the Race session on a schedule row, if it has a dated one."""
    for index in range(1, 6):
        if f"Session{index}" in row and row[f"Session{index}"] == "Race":
            value = row[f"Session{index}DateUtc"]
            return value.to_pydatetime() if pd.notna(value) else None
    return None


async def _await_build(build: asyncio.Task[dict], year: int, round_num: int) -> dict:
    """The build's detail, however long it takes.

    The worker thread behind a build cannot be stopped, so giving up at the
    deadline would only start the next race's FastF1 load beside this one. The
    deadline just flags the race as slow in the logs.
    """
    try:
        return await asyncio.wait_for(asyncio.shield(build), timeout=PREFETCH_RACE_TIMEOUT_SECONDS)
    except TimeoutError:
        if build.done():  # the build's own timeout (a socket, say): a failure
            raise
        logger.warning("prefetch.slow", year=year, round=round_num, waited_seconds=PREFETCH_RACE_TIMEOUT_SECONDS)
        return await asyncio.shield(build)


async def _prefetch_round(year: int, round_num: int) -> None:
    """Build and cache one race's detail.

    Every failure is logged rather than raised: one unavailable race must not
    stop the sweep from reaching the rest of the calendar.
    """
    logger.info("prefetch.starting", year=year, round=round_num)
    try:
        # Joins the build a visitor already started rather than loading the race twice.
        detail = await _await_build(race_detail.start_race_detail_build(year, round_num), year, round_num)
    except Exception as inner_err:
        logger.exception("prefetch.failed", year=year, round=round_num, error=str(inner_err))
        return
    # The build caches a detail that resolved a circuit; one without is a failed build.
    if detail.get("circuit") is not None:
        logger.info("prefetch.cached", year=year, round=round_num)


async def _prefetch_race_details() -> None:
    """Background loop: pre-fetch completed race details every 30 minutes.

    Populates the in-memory ``race_detail_cache`` in race_detail.py so that
    user requests for completed races return instantly.

    Loads ONE race at a time with a 5-second pause between each to avoid
    overwhelming FastF1 / the F1 data API.
    """
    # Give the server a generous startup window before heavy I/O.
    await asyncio.sleep(PREFETCH_STARTUP_DELAY)

    while True:
        try:
            year = datetime.now(UTC).year
            schedule = await asyncio.to_thread(fastf1.get_event_schedule, year, include_testing=False)
            now_utc = datetime.now(UTC).replace(tzinfo=None)

            for _, row in schedule.iterrows():
                round_num = int(row["RoundNumber"])
                cache_key = (year, round_num)

                # Skip if already cached.
                if cache_key in race_detail.race_detail_cache:
                    continue

                # Check if the race is completed (race session + 3h buffer).
                race_date = _race_session_date(row)
                if not race_date or now_utc <= race_date + pd.Timedelta(hours=3):
                    continue

                # Pre-fetch ONE race at a time; a slow one is waited out, not left running.
                await _prefetch_round(year, round_num)

                # Pause between races to avoid hammering the API.
                await asyncio.sleep(PREFETCH_INTER_RACE_DELAY)

        except Exception as e:
            logger.exception("prefetch.loop_error", error=str(e))

        # Self-improving loop: record actuals + generate LLM miss post-mortems
        # for completed races. Guarded so a failure never breaks prefetch.
        try:
            from app.services.self_improvement import run_self_improvement_pass

            await asyncio.to_thread(run_self_improvement_pass, datetime.now(UTC).year)
        except Exception as e:
            logger.exception("self_improvement.loop_error", error=str(e))

        # Sleep before the next sweep (default 30 minutes).
        await asyncio.sleep(PREFETCH_INTERVAL)


async def _refresh_f1db_dataset() -> None:
    """Background loop: keep the local f1db dataset on the newest release.

    The boot-time check in the warm-up covers every cold start. This loop exists
    for the container that *doesn't* cold start: the keep-warm ping can hold this
    process up for days, and f1db publishes the round that just happened a day or
    two after the race. Without a periodic check, a long-lived instance would
    keep serving the dataset it happened to download on boot — which is how the
    standings page spent four weeks a race behind.

    Sleeps first: warm-up has just synced, so there is nothing to do yet.
    """
    while True:
        await asyncio.sleep(F1DB_REFRESH_INTERVAL_SECONDS)
        try:
            outcome = await asyncio.to_thread(sync_to_latest)
            if outcome.updated:
                logger.info("f1db.refresh_loop.updated", version=outcome.version)
        except Exception as e:
            logger.exception("f1db.refresh_loop_error", error=str(e))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: starts background tasks on boot, cancels on shutdown.

    Three tasks run concurrently with request serving:

    * ``run_warmup`` pays the deferred import/model/database costs immediately, so
      the first visitor after a cold start is not the one who pays them. Progress
      is reported via ``GET /api/ready``.
    * ``_prefetch_race_details`` backfills completed-race detail on a long loop.
      It waits ``PREFETCH_STARTUP_DELAY`` first, so warm-up gets the machine to
      itself rather than competing with it for the free tier's single worker.
    * ``_refresh_f1db_dataset`` keeps the historical dataset current on a slow
      loop, so freshness does not depend on the process restarting.
    """
    setup_logging()
    logger.info("server.starting")
    tasks = [
        asyncio.create_task(run_warmup()),
        asyncio.create_task(_prefetch_race_details()),
        asyncio.create_task(_refresh_f1db_dataset()),
    ]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


# Before the app exists, so the SDK's FastAPI integration sees every request.
init_error_tracking()

app = FastAPI(
    title="F1 AI Race Engineer",
    description="AI-powered Formula 1 race analysis and strategy assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restrict origins to the frontend dev server.
# For production, replace with the deployed frontend URL or read from env.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")


@app.get("/")
def read_root() -> dict:
    """Health probe for the root path."""
    return {"status": "Backend is running", "service": "F1 Race Engineer"}


if __name__ == "__main__":
    import uvicorn

    # Local dev entry point only — production is served by the start command in
    # render.yaml. Binds loopback by default; set DEV_HOST=0.0.0.0 to expose the
    # server to a container network or another device on the LAN.
    uvicorn.run(
        "main:app",
        host=os.getenv("DEV_HOST", "127.0.0.1"),
        port=int(os.getenv("DEV_PORT", "8000")),
        reload=True,
    )
