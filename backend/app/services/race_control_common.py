"""Shared data access and normalization helpers for Race Control services."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import TYPE_CHECKING, Any

import fastf1
import pandas as pd
import structlog

from app.data.current_standings import current_standings
from app.data.identity import NEUTRAL_TEAM_COLOR, TEAM_COLORS as IDENTITY_TEAM_COLORS

if TYPE_CHECKING:
    from app.data.standings_table import Standing

logger = structlog.get_logger()


# Keyed by slug, which matches the f1db constructor id for every current team;
# "rb" is the slug of the 2024-25 "RB F1 Team" name.
TEAM_COLORS = {**IDENTITY_TEAM_COLORS, "rb": IDENTITY_TEAM_COLORS["racing-bulls"]}
MAX_GRID_POSITION = 22
# The drivers list reads the computed table (``current_standings``), as the teams page does.
DRIVERS_SOURCE = "computed-standings"


def safe_int(value: Any, default: Any = 0) -> Any:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return int(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return float(value)


def normalise_driver_lookup(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def team_slug(name: str) -> str:
    return name.lower().replace(" racing", "").replace(" f1 team", "").replace(" team", "").replace(" ", "-")


def team_color(team_name: str) -> str:
    slug = team_slug(team_name)
    return TEAM_COLORS.get(slug, NEUTRAL_TEAM_COLOR)


def format_points_value(value: float) -> str:
    return f"{value:g}"


def pluralise(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value} {singular if value == 1 else plural or singular + 's'}"


def _driver_option(row: Standing) -> dict:
    return {
        "code": row.key,
        "name": row.name,
        "team": row.team,
        "position": row.position,
        "points": row.points,
        "wins": row.wins,
    }


def get_driver_options(year: int) -> dict:
    """The season's drivers in championship order, from the table as of its newest round (``current_standings``)."""
    try:
        standings = current_standings(year)
    except Exception as exc:
        logger.warning("race_control.driver_options.failed", year=year, error=str(exc))
        return {
            "year": year,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": DRIVERS_SOURCE,
            "drivers": [],
            "as_of_round": None,
            "provisional": False,
            "sources": [],
            "error": "Driver standings are unavailable right now.",
        }

    drivers = [_driver_option(row) for row in standings.drivers]
    return {
        "year": year,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": DRIVERS_SOURCE,
        "drivers": drivers,
        **standings.meta(),
        "error": None if drivers else "No driver standings found for this season yet.",
    }


def find_driver(drivers: list[dict], query: str) -> dict | None:
    lookup = normalise_driver_lookup(query)
    if not lookup:
        return None

    exact_keys = ("code", "name")
    for driver in drivers:
        if any(normalise_driver_lookup(str(driver.get(key, ""))) == lookup for key in exact_keys):
            return driver

    for driver in drivers:
        if lookup in normalise_driver_lookup(driver["name"]):
            return driver
    return None


def completed_race_rounds(year: int) -> tuple[list[int], int]:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control.completed_rounds.failed", year=year, error=str(exc))
        return [], 0

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    completed: list[int] = []
    total_events = 0
    for _, row in schedule.iterrows():
        total_events += 1
        race_date = next(
            (
                row.get(f"Session{i}DateUtc").to_pydatetime()
                for i in range(1, 6)
                if row.get(f"Session{i}") == "Race" and pd.notna(row.get(f"Session{i}DateUtc"))
            ),
            None,
        )
        if race_date and now_utc > race_date + pd.Timedelta(hours=3):
            completed.append(safe_int(row.get("RoundNumber")))
    return completed, total_events
