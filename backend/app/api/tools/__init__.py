"""
LLM-Callable Tools
==================
Each function decorated with @tool is registered as a callable tool that the
Groq LLM (Llama 3.3 70B) can invoke during the agentic loop in the chat router.

Available tools
---------------
  get_race_predictions        — Probabilistic race outcome predictions with confidence ranges.
  query_f1_database           — Read-only text-to-SQL over the f1db dataset (1950–present).
  get_race_anomalies          — Statistical anomalies/upsets detected in a race result.
  get_pit_strategy            — Pit strategy analysis with stint data and undercut/overcut.
  get_weather_conditions      — Real weather data for F1 circuits (replaces old stub).
  perform_web_search          — Real-time web search via Tavily API.
  get_sprint_results          — Sprint race (Saturday short race) classification.
  get_sprint_qualifying_results — Sprint Qualifying / Shootout results split by SQ1/SQ2/SQ3.
  get_qualifying_results      — Main Qualifying results split by Q1/Q2/Q3.
  compare_drivers             — Fastest-lap telemetry comparison between two drivers.
  get_race_results            — Full race classification with grid delta and points.
  consult_rulebook            — Semantic search of FIA regulations via pgvector.
  get_driver_standings        — World Drivers' Championship table (via f1db).
  get_constructor_standings   — World Constructors' Championship table (via f1db).
  get_season_schedule         — Full season calendar with completed/upcoming status.

Tools are grouped by the data they reach for — ``sessions`` and ``race`` read
FastF1, ``standings`` reads f1db, ``external`` leaves the building — so a change
to one source touches one module. This package assembles them into the registry
below; the chat router imports only ``TOOL_LIST`` and ``TOOL_MAP``.
"""

from app.api.tools.external import get_weather_conditions, perform_web_search
from app.api.tools.predictions import get_pit_strategy, get_race_predictions
from app.api.tools.race import compare_drivers, get_race_anomalies, get_race_results
from app.api.tools.reference import consult_rulebook, query_f1_database
from app.api.tools.sessions import (
    get_qualifying_results,
    get_sprint_qualifying_results,
    get_sprint_results,
)
from app.api.tools.standings import (
    get_constructor_standings,
    get_driver_standings,
    get_season_schedule,
)
from app.utils.fastf1_cache import enable_fastf1_cache

# Enable FastF1 disk cache to avoid re-downloading session data on every call.
# Corrupted cache files are quarantined and recreated on startup.
enable_fastf1_cache()

# ---------------------------------------------------------------------------
# Tool registry — imported by the chat router
# ---------------------------------------------------------------------------
TOOL_LIST = [
    get_race_predictions,
    query_f1_database,
    get_race_anomalies,
    get_pit_strategy,
    get_weather_conditions,
    perform_web_search,
    get_sprint_results,
    get_sprint_qualifying_results,
    get_qualifying_results,
    compare_drivers,
    get_race_results,
    consult_rulebook,
    get_driver_standings,
    get_constructor_standings,
    get_season_schedule,
]

# Map tool name → tool object for O(1) dispatch in the agentic loop.
TOOL_MAP = {t.name: t for t in TOOL_LIST}

__all__ = ["TOOL_LIST", "TOOL_MAP"]
