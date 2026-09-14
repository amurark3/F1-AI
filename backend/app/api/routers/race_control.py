"""HTTP router for Race Control v2 endpoints."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.errors import client_error
from app.api.schemas.race_control import RulebookSearchRequest
from app.services import rulebook
from app.services.race_control import (
    build_overview,
    build_overview_predictions,
    build_overview_shell,
    build_overview_strategy,
    build_overview_weather,
)
from app.services.race_control_battles import build_driver_battle
from app.services.race_control_championship import build_championship_forecast
from app.services.race_control_common import get_driver_options
from app.services.race_control_debriefs import build_race_debrief
from app.services.race_control_standings import build_intel, build_teams
from app.services.race_grid import build_starting_grid
from app.services.race_strategy_board import build_race_strategy
from app.services.weekend_sessions import build_weekend_sessions

router = APIRouter(prefix="/race-control", tags=["race-control"])


@router.get("/overview/{year}")
async def get_overview(year: int):
    """Every segment in one response — slowest input decides the latency."""
    try:
        return await asyncio.to_thread(build_overview, year)
    except Exception as exc:
        return {"year": year, **client_error("api.race_control_overview.error", exc, year=year)}


# The command centre fetches these four in parallel and renders each as it
# lands, so a cold telemetry load no longer holds the whole page hostage.


@router.get("/overview/{year}/shell")
async def get_overview_shell(year: int):
    """Schedule, standings, and session state. Answers without telemetry."""
    try:
        return await asyncio.to_thread(build_overview_shell, year)
    except Exception as exc:
        return {"year": year, **client_error("api.race_control_overview_shell.error", exc, year=year)}


@router.get("/overview/{year}/weather")
async def get_overview_weather(year: int):
    try:
        return await asyncio.to_thread(build_overview_weather, year)
    except Exception as exc:
        return {
            "year": year,
            "risk_register": [],
            **client_error("api.race_control_overview_weather.error", exc, year=year),
        }


@router.get("/overview/{year}/predictions")
async def get_overview_predictions(year: int):
    try:
        return await asyncio.to_thread(build_overview_predictions, year)
    except Exception as exc:
        return {
            "year": year,
            "predicted_podium": [],
            **client_error("api.race_control_overview_predictions.error", exc, year=year),
        }


@router.get("/overview/{year}/strategy")
async def get_overview_strategy(year: int):
    try:
        return await asyncio.to_thread(build_overview_strategy, year)
    except Exception as exc:
        return {
            "year": year,
            "workstreams": [],
            **client_error("api.race_control_overview_strategy.error", exc, year=year),
        }


@router.get("/teams/{year}")
async def get_teams(year: int):
    try:
        return await asyncio.to_thread(build_teams, year)
    except Exception as exc:
        return {"year": year, "teams": [], **client_error("api.race_control_teams.error", exc, year=year)}


@router.get("/teams/{team_slug}/{year}")
async def get_team(team_slug: str, year: int):
    try:
        teams = await asyncio.to_thread(build_teams, year)
        match = next((team for team in teams["teams"] if team["slug"] == team_slug), None)
        return {"year": year, "team": match, "error": None if match else f"Team '{team_slug}' not found"}
    except Exception as exc:
        return {"year": year, "team": None, **client_error("api.race_control_team.error", exc, year=year, team=team_slug)}


@router.get("/drivers/{year}")
async def get_drivers(year: int):
    try:
        return await asyncio.to_thread(get_driver_options, year)
    except Exception as exc:
        return {"year": year, "drivers": [], **client_error("api.race_control_drivers.error", exc, year=year)}


@router.get("/grid/{year}/{round_num}")
async def get_starting_grid(year: int, round_num: int):
    """The round's starting grid and any grid penalties applied to it."""
    try:
        return await asyncio.to_thread(build_starting_grid, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "available": False,
            "provisional": False,
            "grid": [],
            "penalties": [],
            **client_error("api.race_control_grid.error", exc, year=year, round=round_num),
        }


@router.get("/sessions/{year}/{round_num}")
async def get_weekend_sessions(year: int, round_num: int):
    """Every session the weekend ran — practice, and the sprint set if any."""
    try:
        return await asyncio.to_thread(build_weekend_sessions, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "available": False,
            "is_sprint": False,
            "sessions": [],
            **client_error("api.race_control_sessions.error", exc, year=year, round=round_num),
        }


@router.get("/stints/{year}/{round_num}")
async def get_race_strategy(year: int, round_num: int):
    """Tyre stints and pit stops for the race."""
    try:
        return await asyncio.to_thread(build_race_strategy, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "available": False,
            "has_stints": False,
            "has_stops": False,
            "drivers": [],
            "stops": [],
            **client_error("api.race_control_stints.error", exc, year=year, round=round_num),
        }


@router.get("/forecast/{year}")
async def get_championship_forecast(year: int):
    try:
        return await asyncio.to_thread(build_championship_forecast, year)
    except Exception as exc:
        return {"year": year, "drivers": [], "constructors": [], **client_error("api.race_control_forecast.error", exc, year=year)}


@router.get("/battle/{year}/{driver1}/{driver2}")
async def get_battle(year: int, driver1: str, driver2: str):
    return build_driver_battle(year, driver1, driver2)


@router.get("/debrief/{year}/{round_num}")
async def get_debrief(year: int, round_num: int):
    try:
        return await asyncio.to_thread(build_race_debrief, year, round_num)
    except Exception as exc:
        return {"year": year, "round": round_num, "podium": [], "takeaways": [], **client_error("api.race_control_debrief.error", exc, year=year, round=round_num)}


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
    return build_intel(team_slug)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "race-control", "time": datetime.now(timezone.utc).isoformat()}
