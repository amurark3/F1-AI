"""World champions routes — driver/constructor champions and race winners per
season, sourced from the local f1db dataset (1950–present)."""

from fastapi import APIRouter

from app.api.errors import client_error
from app.data.champions import get_champion_stats, get_season_detail, list_champions

router = APIRouter(tags=["champions"])


@router.get("/champions")
async def get_champions():
    """Returns every season 1950→present with its driver and constructor champions."""
    try:
        return {"seasons": list_champions()}
    except Exception as exc:
        return {"seasons": [], **client_error("champions.list_failed", exc)}


@router.get("/champions/stats")
async def get_champions_stats():
    """Returns aggregate leaderboards (most driver/constructor titles)."""
    try:
        return get_champion_stats()
    except Exception as exc:
        return client_error("champions.stats_failed", exc)


@router.get("/champions/{year}")
async def get_champion_season(year: int):
    """Returns champions plus every race winner for a single season."""
    try:
        return get_season_detail(year)
    except Exception as exc:
        return {"year": year, **client_error("champions.detail_failed", exc, year=year)}
