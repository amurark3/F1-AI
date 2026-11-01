"""Team and driver pages: an f1db season profile plus the car's power-unit usage.

Power-unit usage belongs to the car, not the driver (FIA B8.2.7). A team page
shows each of its cars; a driver page shows every car the driver raced, marks
which rounds were theirs, and names whoever else raced it — a stand-in's parts
come out of the regular driver's allocation.

The power-unit payload is the slowest and least certain input, so a failure
there leaves the rest of the page standing with a plain reason in its place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.identity import season_directory
from app.data.profiles import driver_season, team_season
from app.data.profiles.results import rounds_label
from app.services.power_units import build_power_units
from app.services.race_control_common import team_slug

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

POWER_UNITS_FAILED = "Power-unit usage could not be loaded right now."


def load_power_units(year: int) -> tuple[dict | None, str | None]:
    """The season's power-unit payload, or ``None`` and the reason it is missing."""
    try:
        payload = build_power_units(year)
    except Exception as exc:
        logger.warning("profiles.power_units_failed", year=year, error=str(exc), error_type=type(exc).__name__)
        return None, POWER_UNITS_FAILED
    if not payload.get("available"):
        return None, payload.get("reason")
    return payload, None


def _power_units(year: int, select: Callable[[list[dict]], list[dict]]) -> dict:
    payload, reason = load_power_units(year)
    if payload is None:
        return {"available": False, "reason": reason, "as_of": None, "elements": [], "cars": []}
    return {
        "available": True,
        "reason": None,
        "as_of": payload.get("as_of"),
        "elements": payload["elements"],
        "cars": select(payload["cars"]),
    }


def _team_cars(team_id: str) -> Callable[[list[dict]], list[dict]]:
    def select(cars: list[dict]) -> list[dict]:
        return sorted((car for car in cars if car["team_id"] == team_id), key=lambda car: car["car_number"])

    return select


def _shared_with(car: dict, driver_id: str) -> list[dict]:
    return [
        {
            "id": other["id"],
            "name": other["name"],
            "rounds": other["rounds"],
            "rounds_label": rounds_label(other["rounds"]),
        }
        for other in car["drivers"]
        if other["id"] != driver_id
    ]


def _driver_cars(driver_id: str) -> Callable[[list[dict]], list[dict]]:
    def select(cars: list[dict]) -> list[dict]:
        selected = []
        for car in cars:
            mine = next((item for item in car["drivers"] if item["id"] == driver_id), None)
            if mine is not None:
                selected.append(
                    {
                        **car,
                        "driver_rounds": mine["rounds"],
                        "shared_with": _shared_with(car, driver_id),
                    }
                )
        return selected

    return select


def build_directory(year: int) -> dict:
    """Every driver and team of ``year``, for links and the team dropdown."""
    return {**season_directory(year).as_dict(), "status": "ok"}


def build_team_profile(year: int, team_id: str) -> dict:
    season = team_season(year, team_id)
    if season is None:
        return {"year": year, "status": "not_found", "team": None}
    return {
        **season,
        "status": "ok",
        # The slug the intel service keys teams by, derived the same way.
        "intel_slug": team_slug(season["team"]["name"]),
        "power_units": _power_units(year, _team_cars(team_id)),
    }


def build_driver_profile(year: int, driver_id: str) -> dict:
    season = driver_season(year, driver_id)
    if season is None:
        return {"year": year, "status": "not_found", "driver": None}
    return {**season, "status": "ok", "power_units": _power_units(year, _driver_cars(driver_id))}
