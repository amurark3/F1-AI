"""World champions routes — driver/constructor champions and race winners per
season, sourced from the local f1db dataset (1950–present)."""

import structlog
from fastapi import APIRouter

from app.data.champions import get_champion_stats, get_season_detail, list_champions

logger = structlog.get_logger()
router = APIRouter(tags=["champions"])


@router.get("/champions")
async def get_champions():
    """Returns every season 1950→present with its driver and constructor champions."""
    try:
        return {"seasons": list_champions()}
    except Exception as exc:
        logger.error("champions.list_failed", error=str(exc))
        return {"error": str(exc)}


@router.get("/champions/stats")
async def get_champions_stats():
    """Returns aggregate leaderboards (most driver/constructor titles)."""
    try:
        return get_champion_stats()
    except Exception as exc:
        logger.error("champions.stats_failed", error=str(exc))
        return {"error": str(exc)}


@router.get("/champions/{year}")
async def get_champion_season(year: int):
    """Returns champions plus every race winner for a single season."""
    try:
        return get_season_detail(year)
    except Exception as exc:
        logger.error("champions.detail_failed", year=year, error=str(exc))
        return {"error": str(exc)}
