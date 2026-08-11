"""
API Routes
==========
Assembles every endpoint of the F1 AI backend onto one router:

  POST /api/chat                       — Streaming AI chat with tool orchestration
  GET  /api/schedule/{year}            — Full season calendar with UTC session times
  GET  /api/race/{year}/{round_num}    — Enriched race detail (circuit, results, qualifying)
  GET  /api/standings/drivers/{year}   — World Drivers' Championship standings
  GET  /api/standings/constructors/{year} — World Constructors' Championship standings
  WS   /api/live/{year}/{round_num}    — Live timing feed with commentary
  GET  /api/health                     — Liveness probe (is the process up?)
  GET  /api/ready                      — Readiness probe (has warm-up finished?)

The chat endpoint implements an agentic loop:
  1. Build message history with system prompt.
  2. Call the LLM; it may request one or more tools.
  3. Execute every requested tool and append results to history.
  4. Repeat until the model produces a plain-text final answer (or max_turns is reached).
  5. Stream the final text back to the client.

This module holds no endpoint logic of its own beyond the liveness probe —
each feature owns its router and this file only wires them together.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
import structlog

from app.api.compare import router as compare_router
from app.api.live.websocket import router as live_router
from app.api.race_detail import router as race_detail_router
from app.api.routers.champions import router as champions_router
from app.api.routers.chat import router as chat_router
from app.api.routers.memory import router as memory_router
from app.api.routers.predictions import router as predictions_router
from app.api.routers.race_control import router as race_control_router
from app.api.routers.readiness import router as readiness_router
from app.api.routers.season import router as season_router
from app.utils.fastf1_cache import enable_fastf1_cache

logger = structlog.get_logger()

router = APIRouter()
router.include_router(chat_router)
router.include_router(memory_router)
router.include_router(predictions_router)
router.include_router(race_control_router)
router.include_router(season_router)
router.include_router(champions_router)
router.include_router(readiness_router)
router.include_router(race_detail_router)
router.include_router(compare_router)
router.include_router(live_router)

# ---------------------------------------------------------------------------
# FastF1 cache — speeds up repeated session data requests significantly.
# Corrupted cache files are quarantined and recreated on startup.
# ---------------------------------------------------------------------------
enable_fastf1_cache()


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe — returns 200 OK when the server is running."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc)}
