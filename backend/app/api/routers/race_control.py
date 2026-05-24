"""HTTP router for Race Control v2 endpoints."""

import asyncio
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter

from app.api.schemas.race_control import RulebookSearchRequest, StrategySimulationRequest
from app.services import race_control, rulebook

logger = structlog.get_logger()
router = APIRouter(prefix="/race-control", tags=["race-control"])


@router.get("/overview/{year}")
async def get_overview(year: int):
    try:
        return await asyncio.to_thread(race_control.build_overview, year)
    except Exception as exc:
        logger.error("api.race_control_overview.error", year=year, error=str(exc))
        return {"error": str(exc), "year": year}


@router.get("/teams/{year}")
async def get_teams(year: int):
    try:
        return await asyncio.to_thread(race_control.build_teams, year)
    except Exception as exc:
        logger.error("api.race_control_teams.error", year=year, error=str(exc))
        return {"year": year, "teams": [], "error": str(exc)}


@router.get("/teams/{team_slug}/{year}")
async def get_team(team_slug: str, year: int):
    try:
        teams = await asyncio.to_thread(race_control.build_teams, year)
        match = next((team for team in teams["teams"] if team["slug"] == team_slug), None)
        return {"year": year, "team": match, "error": None if match else f"Team '{team_slug}' not found"}
    except Exception as exc:
        logger.error("api.race_control_team.error", year=year, team=team_slug, error=str(exc))
        return {"year": year, "team": None, "error": str(exc)}


@router.get("/drivers/{year}")
async def get_drivers(year: int):
    try:
        return await asyncio.to_thread(race_control.get_driver_options, year)
    except Exception as exc:
        logger.error("api.race_control_drivers.error", year=year, error=str(exc))
        return {"year": year, "drivers": [], "error": str(exc)}


@router.get("/forecast/{year}")
async def get_championship_forecast(year: int):
    try:
        return await asyncio.to_thread(race_control.build_championship_forecast, year)
    except Exception as exc:
        logger.error("api.race_control_forecast.error", year=year, error=str(exc))
        return {"year": year, "drivers": [], "constructors": [], "error": str(exc)}


@router.post("/strategy/simulate")
async def simulate_strategy(request: StrategySimulationRequest):
    return race_control.simulate_strategy(request)


@router.get("/battle/{year}/{driver1}/{driver2}")
async def get_battle(year: int, driver1: str, driver2: str):
    return race_control.build_driver_battle(year, driver1, driver2)


@router.get("/debrief/{year}/{round_num}")
async def get_debrief(year: int, round_num: int):
    try:
        return await asyncio.to_thread(race_control.build_race_debrief, year, round_num)
    except Exception as exc:
        logger.error("api.race_control_debrief.error", year=year, round=round_num, error=str(exc))
        return {"year": year, "round": round_num, "error": str(exc), "podium": [], "takeaways": []}


@router.post("/rulebook/search")
async def search_rulebook(request: RulebookSearchRequest):
    return {
        "query": request.query,
        "category": request.category or "All",
        "year": request.year or "All",
        **await asyncio.to_thread(rulebook.search_rulebook, request.query, request.category, request.year),
    }


@router.get("/intel/{team_slug}")
async def get_intel(team_slug: str):
    return race_control.build_intel(team_slug)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "race-control", "time": datetime.now(timezone.utc).isoformat()}
