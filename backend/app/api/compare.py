"""Fastest-lap telemetry comparison between two drivers."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter
import structlog

from app.api.errors import client_error
from app.config import FASTF1_TIMEOUT_SECONDS

logger = structlog.get_logger()

router = APIRouter()

# Comparison loads a session too, so it shares the same serialisation rule as
# race detail: one FastF1 load at a time.
_fastf1_lock = threading.Lock()

FASTF1_TIMEOUT = FASTF1_TIMEOUT_SECONDS


@router.get("/compare/{year}/{driver1}/{driver2}")
async def compare_drivers_endpoint(year: int, driver1: str, driver2: str) -> dict:
    """
    Head-to-head comparison of two drivers across the season.

    Returns qualifying battle, race battle, average positions, points,
    and per-round breakdown for charts.
    """
    try:
        return await asyncio.to_thread(_build_comparison_sync, year, driver1, driver2)
    except asyncio.TimeoutError:
        return {"error": "Comparison timed out. Try again."}
    except Exception as e:
        return client_error("api.compare_drivers.error", e, year=year, driver1=driver1, driver2=driver2)


def _build_comparison_sync(year: int, driver1_query: str, driver2_query: str) -> dict:
    """Build season-long head-to-head stats for two drivers (sourced from f1db)."""
    from app.data.f1db_results import qualifying_positions, race_results, race_schedule
    from app.data.f1db_standings import driver_standings_detailed

    standings = driver_standings_detailed(year)
    if not standings:
        return {"error": f"No standings data for {year}"}

    def find_driver(query: str) -> dict | None:
        q = query.lower().strip()
        for row in standings:
            code = str(row.get("code", "")).lower()
            name = str(row.get("name", "")).lower()
            if q == code or q in name:
                return {
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "team": row.get("team", "Unknown"),
                    "points": float(row.get("points", 0)),
                    "wins": int(row.get("wins", 0)),
                    "position": int(row.get("position", 0)),
                }
        return None

    d1 = find_driver(driver1_query)
    d2 = find_driver(driver2_query)

    if not d1 or not d2:
        return {"error": f"Could not find driver '{driver1_query}' or '{driver2_query}' in {year} standings."}

    quali_h2h = {"d1": 0, "d2": 0}
    race_h2h = {"d1": 0, "d2": 0}
    rounds = []
    d1_positions: list[int] = []
    d2_positions: list[int] = []

    # Walk the season's rounds from f1db. race_results is empty for rounds not
    # yet run / not in the dataset, so future rounds are naturally skipped.
    for event in race_schedule(year):
        round_num = int(event["round"])
        round_data = {"round": round_num, "name": event.get("name", f"Round {round_num}")}

        race_pos = race_results(year, round_num)
        if not race_pos:
            continue

        d1_race = race_pos.get(d1["code"])
        d2_race = race_pos.get(d2["code"])
        if d1_race is not None and d2_race is not None:
            round_data["d1_race"] = d1_race
            round_data["d2_race"] = d2_race
            d1_positions.append(d1_race)
            d2_positions.append(d2_race)
            if d1_race < d2_race:
                race_h2h["d1"] += 1
            elif d2_race < d1_race:
                race_h2h["d2"] += 1

        quali_pos = qualifying_positions(year, round_num)
        d1_q = quali_pos.get(d1["code"])
        d2_q = quali_pos.get(d2["code"])
        if d1_q is not None and d2_q is not None:
            round_data["d1_quali"] = d1_q
            round_data["d2_quali"] = d2_q
            if d1_q < d2_q:
                quali_h2h["d1"] += 1
            elif d2_q < d1_q:
                quali_h2h["d2"] += 1

        rounds.append(round_data)

    return {
        "driver1": d1,
        "driver2": d2,
        "qualifying_h2h": quali_h2h,
        "race_h2h": race_h2h,
        "avg_race_position": {
            "d1": round(sum(d1_positions) / len(d1_positions), 1) if d1_positions else None,
            "d2": round(sum(d2_positions) / len(d2_positions), 1) if d2_positions else None,
        },
        "rounds": rounds,
    }
