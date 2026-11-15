"""
F1 AI Backend — Entry Point
============================
Boots the FastAPI application, configures CORS, and mounts the API router.

Environment variables (place in a .env file in this directory — see .env.example):
  TOKENLAB_API_KEY — AMD Token Lab key: the primary chat engine.
  GOOGLE_API_KEY   — Gemini free-tier key: the fallback chat engine.
                     At least one of the two is REQUIRED for chat.
  TAVILY_API_KEY   — Tavily web-search API key (optional).
  DATABASE_URL     — Postgres + pgvector for memory/durable store (optional).

The models themselves are not environment variables: they are defined in code
as LLM_PROVIDERS in app/config.py.
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
import structlog

from app.api import routes
from app.config import (
    F1DB_REFRESH_INTERVAL_SECONDS,
    PREFETCH_INTERVAL,
    PREFETCH_STARTUP_DELAY,
)
from app.data.f1db_source import sync_to_latest
from app.error_tracking import init_error_tracking
from app.logging_config import setup_logging
from app.services.readiness import run_warmup

logger = structlog.get_logger()


async def _self_improvement_loop() -> None:
    """Background loop: grade finished calls and write miss post-mortems every 30 minutes.

    Records actuals for every graded call that has none and asks the LLM for a
    post-mortem of its biggest misses. A failed pass is logged and retried on
    the next turn rather than ending the loop.
    """
    # Give the server a generous startup window before heavy I/O.
    await asyncio.sleep(PREFETCH_STARTUP_DELAY)

    while True:
        try:
            from app.services.self_improvement import run_self_improvement_pass

            await asyncio.to_thread(run_self_improvement_pass, datetime.now(UTC).year)
        except Exception as e:
            logger.exception("self_improvement.loop_error", error=str(e))

        # Sleep before the next pass (default 30 minutes).
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
    * ``_self_improvement_loop`` grades finished calls on a long loop. It waits
      ``PREFETCH_STARTUP_DELAY`` first, so warm-up gets the machine to itself
      rather than competing with it for the free tier's single worker.
    * ``_refresh_f1db_dataset`` keeps the historical dataset current on a slow
      loop, so freshness does not depend on the process restarting.
    """
    setup_logging()
    logger.info("server.starting")
    tasks = [
        asyncio.create_task(run_warmup()),
        asyncio.create_task(_self_improvement_loop()),
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
