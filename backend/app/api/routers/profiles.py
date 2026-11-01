"""HTTP router for the Teams & Drivers pages.

Ids are f1db's (``red-bull``, ``max-verstappen``) and are validated before they
reach SQL — they are bound as parameters regardless, but a malformed id is a
client error, not an empty page. An unknown id answers ``status: not_found``
so the page can 404 only when the backend actually said so.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.api.errors import client_error
from app.services.profiles import build_directory, build_driver_profile, build_team_profile

router = APIRouter(prefix="/profiles", tags=["profiles"])

FIRST_SEASON = 1950
ID_PATTERN = r"^[a-z0-9-]{1,64}$"

Year = Annotated[int, Path(ge=FIRST_SEASON)]
EntityId = Annotated[str, Path(pattern=ID_PATTERN)]


def _check_year(year: int) -> None:
    """Next season is allowed (its entry list may be out); later ones are not."""
    if year > datetime.now(UTC).year + 1:
        raise HTTPException(status_code=422, detail=f"No season data for {year}.")


@router.get("/{year}/directory")
async def get_directory(year: Year) -> dict:
    """Every driver and team of the season, keyed by f1db id."""
    _check_year(year)
    try:
        return await asyncio.to_thread(build_directory, year)
    except Exception as exc:
        return {
            "year": year,
            "status": "error",
            "drivers": [],
            "teams": [],
            **client_error("api.profiles.directory_error", exc, year=year),
        }


@router.get("/{year}/teams/{team_id}")
async def get_team(year: Year, team_id: EntityId) -> dict:
    """A constructor's season: line-up, wins, results per round, power units."""
    _check_year(year)
    try:
        return await asyncio.to_thread(build_team_profile, year, team_id)
    except Exception as exc:
        return {
            "year": year,
            "status": "error",
            "team": None,
            **client_error("api.profiles.team_error", exc, year=year, team_id=team_id),
        }


@router.get("/{year}/drivers/{driver_id}")
async def get_driver(year: Year, driver_id: EntityId) -> dict:
    """A driver's season: every round's result, wins, and their car's power unit."""
    _check_year(year)
    try:
        return await asyncio.to_thread(build_driver_profile, year, driver_id)
    except Exception as exc:
        return {
            "year": year,
            "status": "error",
            "driver": None,
            **client_error("api.profiles.driver_error", exc, year=year, driver_id=driver_id),
        }
