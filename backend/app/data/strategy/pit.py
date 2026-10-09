"""The pit-strategy entry point: one race, optionally one driver."""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import TYPE_CHECKING, Any

import structlog

from app.data.strategy.analysis import (
    _analyze_undercut_overcut,
    _get_pit_stop_laps,
    _percentile,
    _summarize_compound_stints,
)
from app.data.strategy.history import (
    _calculate_safety_car_probability,
    _get_historical_strategies,
)
from app.data.strategy.session import _extract_pit_stops, _extract_stint_data, _load_race_data

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()


def _circuit_overview(laps: pd.DataFrame) -> dict:
    """Field-wide strategy view for a race, used when no driver is named."""
    strategy_distribution: dict[str, int] = {}
    driver_summaries = []
    stints_by_driver = []
    first_stop_laps = []
    stop_counts = []

    for driver in laps["Driver"].unique():
        stints = _extract_stint_data(laps, driver)
        if not stints:
            continue

        compounds = "-".join(stint["compound"] for stint in stints)
        num_stops = len(stints) - 1
        pit_laps = _get_pit_stop_laps(laps, driver)
        key = f"{num_stops}-stop ({compounds})"

        strategy_distribution[key] = strategy_distribution.get(key, 0) + 1
        stop_counts.append(num_stops)
        if pit_laps:
            first_stop_laps.append(pit_laps[0])
        driver_summaries.append(
            {
                "driver": driver,
                "strategy": key,
                "num_stops": num_stops,
                "first_stop_lap": pit_laps[0] if pit_laps else None,
            }
        )
        stints_by_driver.append({"driver": driver, "stints": stints})

    return {
        "strategy_distribution": dict(sorted(strategy_distribution.items(), key=lambda item: item[1], reverse=True)),
        "drivers": driver_summaries,
        "compound_summary": _summarize_compound_stints(stints_by_driver),
        "first_stop_window": {
            "sample_size": len(first_stop_laps),
            "p25": round(_percentile(first_stop_laps, 0.25), 1) if first_stop_laps else None,
            "median": round(median(first_stop_laps), 1) if first_stop_laps else None,
            "p75": round(_percentile(first_stop_laps, 0.75), 1) if first_stop_laps else None,
        },
        "stop_count_summary": {
            "sample_size": len(stop_counts),
            "median": round(median(stop_counts), 1) if stop_counts else None,
            "most_common": Counter(stop_counts).most_common(1)[0][0] if stop_counts else None,
        },
    }


def _historical_strategies_section(location: str, year: int) -> dict:
    """Historical strategies for the circuit, degrading to a placeholder."""
    try:
        return _get_historical_strategies(location, year)
    except Exception as exc:
        logger.warning("strategy.historical_error", error=str(exc))
        return {"dominant_strategy": "Data unavailable", "editions": []}


def _safety_car_section(location: str, year: int) -> tuple[int, str]:
    """Safety car probability and its context, degrading to a neutral 50%."""
    try:
        return _calculate_safety_car_probability(location, year)
    except Exception as exc:
        logger.warning("strategy.safety_car_error", error=str(exc))
        return 50, "Unable to calculate safety car probability"


def analyze_pit_strategy(year: int, round_num: int, driver_code: str | None = None) -> dict:
    """Analyze pit strategy for a specific race.

    Args:
        year: Season year (e.g. 2024).
        round_num: Round number in the season calendar.
        driver_code: Optional 3-letter driver abbreviation (e.g. 'VER').
                     If provided, returns detailed analysis for that driver.
                     If None, returns a circuit-level strategy overview.

    Returns:
        Dict with stint breakdowns, historical strategies, undercut/overcut
        analysis, and safety car probability.
    """
    logger.info(
        "strategy.analyze",
        year=year,
        round=round_num,
        driver=driver_code,
    )

    # Load race data
    race_data = _load_race_data(year, round_num)
    if race_data is None:
        return {
            "year": year,
            "round": round_num,
            "error": f"Race data not available for {year} Round {round_num}. "
            "The race may not have occurred yet or data is not loaded.",
        }

    laps = race_data["laps"]
    results = race_data["results"]
    event_name = race_data["event_name"]
    location = race_data["location"]

    # Validate driver if specified
    if driver_code is not None:
        available_drivers = laps["Driver"].unique()
        if driver_code not in available_drivers:
            return {
                "year": year,
                "round": round_num,
                "grand_prix": event_name,
                "error": f"Driver '{driver_code}' not found in race data. "
                f"Available: {', '.join(sorted(available_drivers))}",
            }

    # Build response
    response: dict[str, Any] = {
        "year": year,
        "round": round_num,
        "grand_prix": event_name,
        "driver": driver_code,
    }

    # Stint data
    if driver_code:
        stints = _extract_stint_data(laps, driver_code)
        response["stints"] = stints
        response["pit_stops"] = _extract_pit_stops(laps, results, driver_code)

        # Undercut/overcut analysis
        response["undercut_overcut"] = _analyze_undercut_overcut(laps, results, driver_code)
    else:
        response.update(_circuit_overview(laps))

    response["historical_strategies"] = _historical_strategies_section(location, year)
    probability, context = _safety_car_section(location, year)
    response["safety_car_probability"] = probability
    response["safety_car_context"] = context

    logger.info(
        "strategy.complete",
        year=year,
        round=round_num,
        driver=driver_code,
        stints=len(response.get("stints", [])),
    )

    return response
