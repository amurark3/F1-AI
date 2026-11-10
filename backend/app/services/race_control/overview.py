"""Composing the command-center overview from its feature blocks.

The command centre is assembled from five independently fetchable segments so
the page can render what it has instead of waiting on its slowest input. The
shell answers from the schedule and standings alone (fast); weather and circuit
each wait on an outside feed (Open-Meteo; MultiViewer and OpenF1); strategy reads
the circuit's last edition from OpenF1 and Jolpica and predictions can require a
FastF1 session load, and both are cached durably, so the cost is paid once
rather than per process.
"""

from __future__ import annotations

import structlog

from app.data.current_standings import current_standings
from app.data.strategy import circuit_strategy_reference
from app.services.predictions import get_cached_race_prediction, get_or_compute_race_prediction
from app.services.race_control.baseline_plan import build_baseline
from app.services.race_control.circuit import build_circuit_segment
from app.services.race_control.live import build_live_status
from app.services.race_control.risk import build_risk_register
from app.services.race_control.session_weather import build_session_weather, race_day_block
from app.services.race_control.strategy_context import (
    build_competitor_rows,
    build_strategy_context,
    build_strategy_dashboard,
    season_events,
    select_event,
)
from app.services.race_control.weather import build_weather_block
from app.services.race_control.workstreams import build_workstreams

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


# What a reference read that raised stands for: an edition that could not be
# read right now, never "this circuit has no edition".
UNREAD_REFERENCE: dict = {"source_year": None, "unread_years": []}


def strategy_reference_for(year: int, race: dict | None) -> dict | None:
    """The latest same-circuit edition's measured plan for the selected race.

    None when there is no race or the circuit has no edition to read; an
    unread marker when reading it failed.
    """
    if not (race and race.get("location")):
        return None
    try:
        return circuit_strategy_reference(race["location"], year)
    except Exception as exc:
        logger.warning("race_control.strategy_reference.failed", year=year, error=str(exc))
        return dict(UNREAD_REFERENCE)


def _selected_race(year: int) -> dict | None:
    """Resolve the event a segment is reporting on, without standings or telemetry."""
    return select_event(season_events(year))


def _top_constructors(year: int) -> list[dict]:
    return current_standings(year).team_rows()[:5]


def build_overview_shell(year: int) -> dict:
    """Schedule, standings, and session state. No telemetry, no model."""

    dashboard = build_strategy_dashboard(year)
    return {**dashboard, "live_status": build_live_status(dashboard.get("race"))}


def weather_blocks(race: dict | None) -> tuple[dict, dict]:
    """The summary weather card and the per-session forecast it is drawn from.

    The card reads the race session's forecast and nothing else: with none it
    shows no number, only the forecast's reason (never current conditions).
    """
    sessions = build_session_weather(race)
    return build_weather_block(sessions), sessions


def build_overview_weather(year: int) -> dict:
    """The weekend's forecast session by session, and the risk register graded from the race's."""

    race = _selected_race(year)
    weather, sessions = weather_blocks(race)
    competitors = build_competitor_rows(_top_constructors(year))
    return {
        "year": year,
        "weather": weather,
        "session_weather": sessions,
        "risk_register": build_risk_register(race, sessions, competitors),
    }


def build_overview_circuit(year: int) -> dict:
    """The selected circuit's map, layout facts and history."""

    return {"year": year, **build_circuit_segment(year, _selected_race(year))}


def build_overview_predictions(year: int) -> dict:
    """Projected podium from the stored race model snapshot."""

    predictions = race_predictions(year, _selected_race(year))
    return {
        "year": year,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
    }


def build_overview_strategy(year: int) -> dict:
    """The baseline plan from the circuit's latest edition, and the workstreams.

    The prediction snapshot is read, never computed: the predictions segment
    owns that work, and here it only sets the race-model workstream. The
    race-day forecast flags the dry plan as the secondary branch when rain is
    likely; it is the weather segment's own read, cached for both.
    """

    race = _selected_race(year)
    predictions = get_cached_race_prediction(year, race["round"]) if race and race.get("round") else None
    baseline = build_baseline(year, strategy_reference_for(year, race), race_day_block(build_session_weather(race)))
    context = build_strategy_context(race, _top_constructors(year), baseline)
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
    weather, sessions = weather_blocks(race)
    baseline = build_baseline(year, strategy_reference_for(year, race), race_day_block(sessions))
    strategy_context = build_strategy_context(race, constructors, baseline)

    return {
        **dashboard,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
        "strategy_context": strategy_context,
        "weather": weather,
        "session_weather": sessions,
        "circuit": build_circuit_segment(year, race),
        "risk_register": build_risk_register(race, sessions, strategy_context.get("competitors", [])),
        "workstreams": build_workstreams(race, predictions, strategy_context),
        "live_status": build_live_status(race),
    }
