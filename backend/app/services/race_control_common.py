"""Shared data access and normalization helpers for Race Control services."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import fastf1
import pandas as pd
import structlog
from fastf1.ergast import Ergast

logger = structlog.get_logger()


TEAM_COLORS = {
    "red-bull": "#3671C6",
    "mclaren": "#FF8000",
    "ferrari": "#E8002D",
    "mercedes": "#27F4D2",
    "aston-martin": "#229971",
    "williams": "#64C4FF",
    "rb": "#6692FF",
    "haas": "#B6BABD",
    "alpine": "#FF87BC",
    "audi": "#E0E0E0",
    "cadillac": "#B6BABD",
}
MAX_GRID_POSITION = 22


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


def safe_str(row: Any, key: str, default: str = "") -> str:
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return str(value)


def first_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else default
    return str(value)


def constructor_name_from_row(row: Any, default: str = "Unknown") -> str:
    if "constructorName" in row:
        return first_value(row.get("constructorName"), default)
    return first_value(row.get("constructorNames"), default)


def driver_full_name(row: Any) -> str:
    return f"{safe_str(row, 'givenName')} {safe_str(row, 'familyName')}".strip()


def driver_code_from_row(row: Any) -> str:
    code = safe_str(row, "driverCode").strip().upper()
    if code:
        return code

    family_name = safe_str(row, "familyName").strip().upper()
    if len(family_name) >= 3:
        return family_name[:3]

    driver_id = safe_str(row, "driverId").replace("_", "").strip().upper()
    return driver_id[:3] if driver_id else "TBC"


def normalise_driver_lookup(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def team_slug(name: str) -> str:
    return (
        name.lower()
        .replace(" racing", "")
        .replace(" f1 team", "")
        .replace(" team", "")
        .replace(" ", "-")
    )


def team_color(team_name: str) -> str:
    slug = team_slug(team_name)
    return TEAM_COLORS.get(slug, "#6B7280")


def format_points_value(value: float) -> str:
    return f"{value:g}"


def pluralise(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value} {singular if value == 1 else plural or singular + 's'}"


def get_standings_snapshot(year: int) -> tuple[list[dict], list[dict]]:
    ergast = Ergast()
    drivers = []
    constructors = []

    try:
        driver_data = ergast.get_driver_standings(season=year)
        if driver_data.content:
            for idx, (_, row) in enumerate(driver_data.content[0].iterrows(), start=1):
                drivers.append({
                    "position": safe_int(row.get("position", idx), idx),
                    "code": driver_code_from_row(row),
                    "driver": driver_full_name(row),
                    "team": constructor_name_from_row(row),
                    "points": safe_float(row.get("points", 0)),
                    "wins": safe_int(row.get("wins", 0)),
                })
    except Exception as exc:
        logger.warning("race_control.driver_snapshot.failed", year=year, error=str(exc))

    try:
        constructor_data = ergast.get_constructor_standings(season=year)
        if constructor_data.content:
            for idx, (_, row) in enumerate(constructor_data.content[0].iterrows(), start=1):
                constructors.append({
                    "position": safe_int(row.get("position", idx), idx),
                    "team": safe_str(row, "constructorName", "Unknown"),
                    "points": safe_float(row.get("points", 0)),
                    "wins": safe_int(row.get("wins", 0)),
                })
    except Exception as exc:
        logger.warning("race_control.constructor_snapshot.failed", year=year, error=str(exc))

    return drivers, constructors


def load_driver_standings(year: int) -> list[dict]:
    ergast = Ergast()
    driver_data = ergast.get_driver_standings(season=year)
    if not driver_data.content:
        return []

    standings = []
    for idx, (_, row) in enumerate(driver_data.content[0].iterrows(), start=1):
        standings.append({
            "code": driver_code_from_row(row),
            "name": driver_full_name(row),
            "team": constructor_name_from_row(row),
            "position": safe_int(row.get("position", idx), idx),
            "points": safe_float(row.get("points", 0)),
            "wins": safe_int(row.get("wins", 0)),
            "nationality": safe_str(row, "driverNationality"),
            "driver_id": safe_str(row, "driverId"),
        })
    return standings


def get_driver_options(year: int) -> dict:
    try:
        drivers = load_driver_standings(year)
    except Exception as exc:
        logger.warning("race_control.driver_options.failed", year=year, error=str(exc))
        return {
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "jolpica-ergast-driver-standings",
            "drivers": [],
            "error": "Driver standings are unavailable right now.",
        }

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jolpica-ergast-driver-standings",
        "drivers": drivers,
        "error": None if drivers else "No driver standings found for this season yet.",
    }


def find_driver(drivers: list[dict], query: str) -> dict | None:
    lookup = normalise_driver_lookup(query)
    if not lookup:
        return None

    exact_keys = ("code", "driver_id", "name")
    for driver in drivers:
        if any(normalise_driver_lookup(str(driver.get(key, ""))) == lookup for key in exact_keys):
            return driver

    for driver in drivers:
        if lookup in normalise_driver_lookup(driver["name"]):
            return driver
    return None


def completed_race_count(year: int) -> int | None:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control.completed_races.failed", year=year, error=str(exc))
        return None

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    completed = 0
    for _, row in schedule.iterrows():
        race_date = next(
            (
                row.get(f"Session{i}DateUtc").to_pydatetime()
                for i in range(1, 6)
                if row.get(f"Session{i}") == "Race" and pd.notna(row.get(f"Session{i}DateUtc"))
            ),
            None,
        )
        if race_date and now_utc > race_date + pd.Timedelta(hours=3):
            completed += 1
    return completed


def completed_race_rounds(year: int) -> tuple[list[int], int]:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control.completed_rounds.failed", year=year, error=str(exc))
        return [], 0

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
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
