"""HTTP router for the power-unit usage screen."""

import asyncio

from fastapi import APIRouter

from app.api.errors import client_error
from app.services.power_units import build_power_units

router = APIRouter(prefix="/race-control", tags=["race-control"])


@router.get("/power-units/{year}")
async def get_power_units(year: int) -> dict:
    """Every car's element allowance, usage, and the grid penalties it cost."""
    try:
        return await asyncio.to_thread(build_power_units, year)
    except Exception as exc:
        return {
            "year": year,
            "available": False,
            "cars": [],
            "unread": [],
            "warnings": [],
            **client_error("api.power_units.error", exc, year=year),
        }
