"""Composing the command-center overview from its feature blocks.

The command centre is assembled from four independently fetchable segments so
the page can render what it has instead of waiting on its slowest input. The
shell answers from the schedule and standings alone (fast); the other three
each depend on something that can require a FastF1 session load, and the two
that do are cached durably, so the cost is paid once rather than per process.
"""

from __future__ import annotations

import structlog

from app.data.strategy import circuit_strategy_reference
from app.services.predictions import get_cached_race_prediction, get_or_compute_race_prediction
from app.services.race_control.live import build_live_status
from app.services.race_control.risk import build_risk_register
from app.services.race_control.strategy_context import (
    build_competitor_rows,
    build_strategy_context,
    build_strategy_dashboard,
    season_events,
    select_event,
)
from app.services.race_control.weather import build_weather_block
from app.services.race_control.workstreams import build_workstreams
from app.services.race_control_common import get_standings_snapshot

logger = structlog.get_logger()


def race_predictions(year: int, race: dict | None) -> dict | None:
    """Prediction snapshot for the selected race, computing it if none is stored.

    A prediction failure must not take the whole command centre down with it —
    every panel that does not depend on the model still has something to show.
    """
    if not (race and race.get("round")):
        return None
    try:
        return get_or_compute_race_prediction(year, race["round"])
    except Exception as exc:
        logger.warning("race_control.predictions.failed", year=year, error=str(exc))
        return None


def strategy_reference_for(year: int, race: dict | None) -> dict | None:
    """Telemetry reference for the selected circuit, or None when unavailable."""
    if not (race and race.get("location")):
        return None
    try:
        return circuit_strategy_reference(race["location"], year)
    except Exception as exc:
        logger.warning("race_control.strategy_reference.failed", year=year, error=str(exc))
        return None


def _selected_race(year: int) -> dict | None:
    """Resolve the event a segment is reporting on, without standings or telemetry."""
    return select_event(season_events(year))


def _top_constructors(year: int) -> list[dict]:
    _, constructors = get_standings_snapshot(year)
    return constructors[:5]


def build_overview_shell(year: int) -> dict:
    """Schedule, standings, and session state. No telemetry, no model."""

    dashboard = build_strategy_dashboard(year)
    return {**dashboard, "live_status": build_live_status(dashboard.get("race"))}


def build_overview_weather(year: int) -> dict:
    """Live forecast for the selected circuit, and the risk register it grades."""

    race = _selected_race(year)
    weather = build_weather_block(race)
    competitors = build_competitor_rows(_top_constructors(year))
    return {
        "year": year,
        "weather": weather,
        "risk_register": build_risk_register(race, weather, competitors),
    }


def build_overview_predictions(year: int) -> dict:
    """Projected podium from the stored race model snapshot."""

    predictions = race_predictions(year, _selected_race(year))
    return {
        "year": year,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
    }


def build_overview_strategy(year: int) -> dict:
    """Baseline strategy context derived from the circuit's telemetry reference.

    The prediction snapshot is read, never computed: the predictions segment
    owns that work, so this segment does not queue behind a model run whose
    only effect here is the confidence grade and the race-model workstream.
    """

    race = _selected_race(year)
    predictions = get_cached_race_prediction(year, race["round"]) if race and race.get("round") else None
    context = build_strategy_context(
        race,
        _top_constructors(year),
        predictions,
        strategy_reference_for(year, race),
    )
    return {
        "year": year,
        "strategy_context": context,
        "workstreams": build_workstreams(race, predictions, context),
    }


def build_overview(year: int) -> dict:
    """Full command-centre payload — every segment in one response.

    Kept for callers that want the whole picture in a single request. The web
    UI fetches the segments instead, so it never blocks on the slowest one.
    """
    dashboard = build_strategy_dashboard(year)
    race = dashboard.get("race")
    constructors = dashboard.get("championship", {}).get("constructors", [])

    predictions = race_predictions(year, race)
    strategy_context = build_strategy_context(race, constructors, predictions, strategy_reference_for(year, race))
    weather = build_weather_block(race)

    return {
        **dashboard,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
        "strategy_context": strategy_context,
        "weather": weather,
        "risk_register": build_risk_register(race, weather, strategy_context.get("competitors", [])),
        "workstreams": build_workstreams(race, predictions, strategy_context),
        "live_status": build_live_status(race),
    }
