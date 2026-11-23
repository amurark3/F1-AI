"""HTTP router for Race Control v2 endpoints."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.errors import client_error
from app.api.schemas.race_control import RulebookSearchRequest
from app.services import rulebook
from app.services.debrief_laps import build_debrief_laps
from app.services.debrief_overtakes import build_debrief_overtakes
from app.services.debrief_penalties import build_debrief_penalties
from app.services.debrief_radio import build_debrief_radio
from app.services.race_control import (
    build_overview,
    build_overview_circuit,
    build_overview_predictions,
    build_overview_shell,
    build_overview_strategy,
    build_overview_weather,
    build_round_circuit,
)
from app.services.race_control.clinch import build_clinch
from app.services.race_control.progression import build_standings_progression
from app.services.race_control_battles import build_driver_battle
from app.services.race_control_championship import build_championship_forecast
from app.services.race_control_common import get_driver_options
from app.services.race_control_debriefs import build_race_debrief
from app.services.race_control_standings import build_intel, build_teams
from app.services.race_glance import build_race_glance
from app.services.race_grid import build_starting_grid
from app.services.race_results import build_race_results
from app.services.race_strategy_board import build_race_strategy
from app.services.weekend_sessions import build_weekend_sessions

router = APIRouter(prefix="/race-control", tags=["race-control"])


@router.get("/overview/{year}")
async def get_overview(year: int) -> dict:
    """Every segment in one response — slowest input decides the latency."""
    try:
        return await asyncio.to_thread(build_overview, year)
    except Exception as exc:
        return {"year": year, **client_error("api.race_control_overview.error", exc, year=year)}


# The command centre fetches these five in parallel and renders each as it
# lands, so a cold telemetry load no longer holds the whole page hostage.


@router.get("/overview/{year}/shell")
async def get_overview_shell(year: int) -> dict:
    """Schedule, standings, and session state. Answers without telemetry."""
    try:
        return await asyncio.to_thread(build_overview_shell, year)
    except Exception as exc:
        return {"year": year, **client_error("api.race_control_overview_shell.error", exc, year=year)}


@router.get("/overview/{year}/weather")
async def get_overview_weather(year: int) -> dict:
    try:
        return await asyncio.to_thread(build_overview_weather, year)
    except Exception as exc:
        return {
            "year": year,
            "risk_register": [],
            **client_error("api.race_control_overview_weather.error", exc, year=year),
        }


@router.get("/overview/{year}/circuit")
async def get_overview_circuit(year: int) -> dict:
    """Circuit map, layout facts and history. Waits on MultiViewer and OpenF1 once, then cache."""
    try:
        return await asyncio.to_thread(build_overview_circuit, year)
    except Exception as exc:
        return {
            "year": year,
            "record": None,
            "lap_record": None,
            "map": None,
            **client_error("api.race_control_overview_circuit.error", exc, year=year),
        }


@router.get("/circuit/{year}/{round_num}")
async def get_round_circuit(year: int, round_num: int) -> dict:
    """The given round's circuit map, f1db record and lap record."""
    try:
        return await asyncio.to_thread(build_round_circuit, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "record": None,
            "lap_record": None,
            "map": None,
            **client_error("api.race_control_circuit.error", exc, year=year, round=round_num),
        }


@router.get("/results/{year}/{round_num}")
async def get_race_results(year: int, round_num: int) -> dict:
    """The round's official race classification, and its sprint's, with whether each is final."""
    try:
        return await asyncio.to_thread(build_race_results, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "race": None,
            "sprint": None,
            **client_error("api.race_control_results.error", exc, year=year, round=round_num),
        }


@router.get("/overview/{year}/predictions")
async def get_overview_predictions(year: int) -> dict:
    try:
        return await asyncio.to_thread(build_overview_predictions, year)
    except Exception as exc:
        return {
            "year": year,
            "predicted_podium": [],
            **client_error("api.race_control_overview_predictions.error", exc, year=year),
        }


@router.get("/overview/{year}/strategy")
async def get_overview_strategy(year: int) -> dict:
    try:
        return await asyncio.to_thread(build_overview_strategy, year)
    except Exception as exc:
        return {
            "year": year,
            "workstreams": [],
            **client_error("api.race_control_overview_strategy.error", exc, year=year),
        }


@router.get("/teams/{year}")
async def get_teams(year: int) -> dict:
    try:
        return await asyncio.to_thread(build_teams, year)
    except Exception as exc:
        return {"year": year, "teams": [], **client_error("api.race_control_teams.error", exc, year=year)}


@router.get("/teams/{team_slug}/{year}")
async def get_team(team_slug: str, year: int) -> dict:
    try:
        teams = await asyncio.to_thread(build_teams, year)
        match = next((team for team in teams["teams"] if team["slug"] == team_slug), None)
        return {"year": year, "team": match, "error": None if match else f"Team '{team_slug}' not found"}
    except Exception as exc:
        return {
            "year": year,
            "team": None,
            **client_error("api.race_control_team.error", exc, year=year, team=team_slug),
        }


@router.get("/drivers/{year}")
async def get_drivers(year: int) -> dict:
    try:
        return await asyncio.to_thread(get_driver_options, year)
    except Exception as exc:
        return {"year": year, "drivers": [], **client_error("api.race_control_drivers.error", exc, year=year)}


@router.get("/standings/{year}/progression")
async def get_standings_progression(year: int) -> dict:
    """Every round's drivers' and constructors' table, and the round each title was clinched."""
    try:
        return await asyncio.to_thread(build_standings_progression, year)
    except Exception as exc:
        return {
            "year": year,
            "rounds": [],
            **client_error("api.race_control_standings_progression.error", exc, year=year),
        }


@router.get("/grid/{year}/{round_num}")
async def get_starting_grid(year: int, round_num: int) -> dict:
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
async def get_weekend_sessions(year: int, round_num: int) -> dict:
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
async def get_race_strategy(year: int, round_num: int) -> dict:
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


@router.get("/standings/{year}/clinch")
async def get_clinch(year: int) -> dict:
    """What each championship hangs on: decided (where) or what the leader must do at the next event."""
    try:
        return await asyncio.to_thread(build_clinch, year)
    except Exception as exc:
        return {
            "year": year,
            "drivers": None,
            "constructors": None,
            **client_error("api.race_control_clinch.error", exc, year=year),
        }


@router.get("/forecast/{year}")
async def get_championship_forecast(year: int) -> dict:
    try:
        return await asyncio.to_thread(build_championship_forecast, year)
    except Exception as exc:
        return {
            "year": year,
            "drivers": [],
            "constructors": [],
            **client_error("api.race_control_forecast.error", exc, year=year),
        }


@router.get("/battle/{year}/{driver1}/{driver2}")
async def get_battle(year: int, driver1: str, driver2: str) -> dict:
    return build_driver_battle(year, driver1, driver2)


@router.get("/debrief/{year}/{round_num}")
async def get_debrief(year: int, round_num: int) -> dict:
    try:
        return await asyncio.to_thread(build_race_debrief, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            **client_error("api.race_control_debrief.error", exc, year=year, round=round_num),
        }


async def _debrief_part(name: str, builder: Callable[[int, int], dict], year: int, round_num: int) -> dict:
    try:
        return await asyncio.to_thread(builder, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            **client_error(f"api.race_control_debrief_{name}.error", exc, year=year, round=round_num),
        }


@router.get("/debrief/{year}/{round_num}/laps")
async def get_debrief_laps(year: int, round_num: int) -> dict:
    return await _debrief_part("laps", build_debrief_laps, year, round_num)


@router.get("/debrief/{year}/{round_num}/penalties")
async def get_debrief_penalties(year: int, round_num: int) -> dict:
    return await _debrief_part("penalties", build_debrief_penalties, year, round_num)


@router.get("/debrief/{year}/{round_num}/overtakes")
async def get_debrief_overtakes(year: int, round_num: int) -> dict:
    return await _debrief_part("overtakes", build_debrief_overtakes, year, round_num)


@router.get("/debrief/{year}/{round_num}/radio")
async def get_debrief_radio(year: int, round_num: int) -> dict:
    return await _debrief_part("radio", build_debrief_radio, year, round_num)


@router.post("/rulebook/search")
async def search_rulebook(request: RulebookSearchRequest) -> dict:
    return await asyncio.to_thread(rulebook.search_rulebook, request.query, request.category, request.year)


@router.get("/intel/{team_slug}")
async def get_intel(team_slug: str) -> dict:
    try:
        return await asyncio.to_thread(build_intel, team_slug)
    except Exception as exc:
        return {
            "status": "error",
            "threats": [],
            "opportunities": [],
            "upgrade_watch": [],
            **client_error("api.race_control_intel.error", exc, team_slug=team_slug),
        }


@router.get("/glance/{year}/{round_num}")
async def get_race_glance(year: int, round_num: int) -> dict:
    """Last edition's winner and pole here, and this round's PU penalty decisions."""
    try:
        return await asyncio.to_thread(build_race_glance, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "previous": None,
            "power_units": {"available": False, "reason": None, "decisions": []},
            **client_error("api.race_control_glance.error", exc, year=year, round=round_num),
        }


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "race-control", "time": datetime.now(UTC).isoformat()}
