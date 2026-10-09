"""Race Control overview orchestration and public service facade.

Focused feature services live beside this module. The package keeps the
existing router contract stable while limiting each file to one block of the
command center:

    live               whether a session is on track — the desk's only clock
    weather            live forecast card, or an honest blank one
    risk               weather and championship-rival risk register
    workstreams        per-workstream status cards
    strategy_context   season calendar, strategy dashboard and the numbers behind it
    overview           composes the above into the page payload, whole or by segment
"""

from app.services.race_control.live import build_live_status
from app.services.race_control.overview import (
    build_overview,
    build_overview_predictions,
    build_overview_shell,
    build_overview_strategy,
    build_overview_weather,
)
from app.services.race_control.risk import build_risk_register
from app.services.race_control.strategy_context import DEFAULT_RACE_LAPS, build_strategy_context
from app.services.race_control.weather import WEATHER_FEED_LIVE, WEATHER_FEED_OFFLINE
from app.services.race_control.workstreams import focus_for_event

__all__ = [
    "DEFAULT_RACE_LAPS",
    "WEATHER_FEED_LIVE",
    "WEATHER_FEED_OFFLINE",
    "build_live_status",
    "build_overview",
    "build_overview_predictions",
    "build_overview_shell",
    "build_overview_strategy",
    "build_overview_weather",
    "build_risk_register",
    "build_strategy_context",
    "focus_for_event",
]
