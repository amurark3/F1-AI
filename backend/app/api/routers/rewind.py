"""HTTP router for Race Rewind: a finished race's order at the line, lap by lap."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Path

from app.api.errors import client_error
from app.services.race_rewind import build_race_rewind

router = APIRouter(prefix="/race-control/rewind", tags=["rewind"])

# OpenF1's first season: nothing earlier has positions.
FIRST_OPENF1_SEASON = 2023

Year = Annotated[int, Path(ge=FIRST_OPENF1_SEASON, le=2100)]
Round = Annotated[int, Path(ge=1, le=30)]


@router.get("/{year}/{round_num}")
async def get_race_rewind(year: Year, round_num: Round) -> dict:
    """The race lap by lap, with the FIA's final classification as the last step."""
    try:
        return await asyncio.to_thread(build_race_rewind, year, round_num)
    except Exception as exc:
        return {
            "year": year,
            "round": round_num,
            "available": False,
            "reason": None,
            "total_laps": 0,
            "drivers": [],
            "grid": None,
            "neutralisations": [],
            "stops": [],
            "laps": [],
            "final": None,
            **client_error("api.race_rewind.error", exc, year=year, round=round_num),
        }
