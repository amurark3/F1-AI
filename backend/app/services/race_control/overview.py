"""Composing the command-center overview from its feature blocks."""

from __future__ import annotations

import structlog

from app.data.strategy import circuit_strategy_reference
from app.services.predictions import get_or_compute_race_prediction
from app.services.race_control.risk import build_risk_register
from app.services.race_control.strategy_context import (
    build_strategy_context,
    build_strategy_dashboard,
)
from app.services.race_control.weather import build_weather_block
from app.services.race_control.workstreams import build_workstreams

logger = structlog.get_logger()


def build_overview(year: int) -> dict:
    dashboard = build_strategy_dashboard(year)
    race = dashboard.get("race")
    championship = dashboard.get("championship", {})
    constructors = championship.get("constructors", [])

    predictions = None
    if race and race.get("round"):
        try:
            predictions = get_or_compute_race_prediction(year, race["round"])
        except Exception as exc:
            logger.warning("race_control.predictions.failed", year=year, error=str(exc))

    strategy_reference = None
    if race and race.get("location"):
        try:
            strategy_reference = circuit_strategy_reference(race["location"], year)
        except Exception as exc:
            logger.warning("race_control.strategy_reference.failed", year=year, error=str(exc))

    strategy_context = build_strategy_context(race, constructors, predictions, strategy_reference)
    weather = build_weather_block(race)

    return {
        **dashboard,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
        "strategy_context": strategy_context,
        "weather": weather,
        "risk_register": build_risk_register(race, weather, strategy_context.get("competitors", [])),
        "workstreams": build_workstreams(race, predictions, strategy_context),
        "live_status": {
            "connected": bool(race and race.get("status") == "in_progress"),
            "label": "Live session active" if race and race.get("status") == "in_progress" else "Standby",
        },
    }
