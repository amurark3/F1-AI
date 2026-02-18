"""
F1 AI Backend — Entry Point
============================
Boots the FastAPI application, configures CORS, and mounts the API router.

Environment variables required (place in a .env file in this directory):
  GOOGLE_API_KEY  — Google Generative AI (Gemini) API key
  TAVILY_API_KEY  — Tavily web-search API key
"""

from dotenv import load_dotenv

# Load .env BEFORE any other local imports so os.getenv() works everywhere.
load_dotenv()

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
import fastf1
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logging_config import setup_logging
from app.api import routes
from app.config import (
    PREFETCH_STARTUP_DELAY,
    PREFETCH_RACE_TIMEOUT_SECONDS,
    PREFETCH_INTER_RACE_DELAY,
    PREFETCH_INTERVAL,
)

logger = structlog.get_logger()


async def _prefetch_race_details():
    """Background loop: pre-fetch completed race details every 30 minutes.

    Populates the in-memory ``race_detail_cache`` in routes.py so that
    user requests for completed races return instantly.

    Loads ONE race at a time with a 5-second pause between each to avoid
    overwhelming FastF1 / the F1 data API.
    """
    # Give the server a generous startup window before heavy I/O.
    await asyncio.sleep(PREFETCH_STARTUP_DELAY)

    while True:
        try:
            year = datetime.now(timezone.utc).year
            schedule = await asyncio.to_thread(
                fastf1.get_event_schedule, year, include_testing=False
            )
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            for _, row in schedule.iterrows():
                round_num = int(row["RoundNumber"])
                cache_key = (year, round_num)

                # Skip if already cached.
                if cache_key in routes.race_detail_cache:
                    continue

                # Check if the race is completed (race session + 3h buffer).
                race_date = None
                for i in range(1, 6):
                    if f"Session{i}" in row and row[f"Session{i}"] == "Race":
                        d = row[f"Session{i}DateUtc"]
                        if pd.notna(d):
                            race_date = d.to_pydatetime()
                        break

                if not race_date or now_utc <= race_date + pd.Timedelta(hours=3):
                    continue

                # Pre-fetch ONE race at a time with a 60s timeout.
                logger.info("prefetch.starting", year=year, round=round_num)
                try:
                    detail = await asyncio.wait_for(
                        asyncio.to_thread(
                            routes._build_race_detail_sync, year, round_num
                        ),
                        timeout=PREFETCH_RACE_TIMEOUT_SECONDS,
                    )
                    if detail.get("circuit") is not None:
                        routes.race_detail_cache[cache_key] = detail
                        logger.info("prefetch.cached", year=year, round=round_num)
                except asyncio.TimeoutError:
                    logger.warning("prefetch.timeout", year=year, round=round_num)
                except Exception as inner_err:
                    logger.error("prefetch.failed", year=year, round=round_num, error=str(inner_err))

                # Pause between races to avoid hammering the API.
                await asyncio.sleep(PREFETCH_INTER_RACE_DELAY)

        except Exception as e:
            logger.error("prefetch.loop_error", error=str(e))

        # Sleep before the next sweep (default 30 minutes).
        await asyncio.sleep(PREFETCH_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: starts background prefetch on boot, cancels on shutdown."""
    setup_logging()
    logger.info("server.starting")
    task = asyncio.create_task(_prefetch_race_details())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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
def read_root():
    """Health probe for the root path."""
    return {"status": "Backend is running", "service": "F1 Race Engineer"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
