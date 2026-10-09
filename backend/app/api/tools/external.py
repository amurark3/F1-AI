"""Tools that reach outside the F1 datasets: live weather and web search."""

from __future__ import annotations

import asyncio
import os

from langchain_core.tools import tool
import structlog
from tavily import TavilyClient

from app.data.weather import get_weather_for_circuit

logger = structlog.get_logger()

_tavily_client: TavilyClient | None = None


def get_tavily_client() -> TavilyClient:
    """Builds the Tavily client on first use, memoising it thereafter.

    Constructing this at import time made a missing ``TAVILY_API_KEY`` take the
    whole service down at boot: this module is reached from `app.api.tools` →
    `app.api.routers.chat` → `app.api.routes` → `main`, so every endpoint went
    with it, not just web search. Deferring the build keeps the boot path free
    of third-party credentials and scopes a missing key to the one tool that
    needs it — the same contract `build_chat_llm()` and the embedder already
    follow for Groq and sentence-transformers.
    """
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily_client


@tool
def get_weather_conditions(location: str) -> str:
    """
    Fetches current weather and hourly forecast for an F1 circuit.

    Use when user asks about weather conditions, rain probability, track
    temperature, or how weather affects strategy.

    Args:
        location: Circuit location name (e.g. 'Monaco', 'Silverstone', 'Sakhir').
    """
    logger.info("tool.weather_conditions", location=location)
    try:
        # get_weather_for_circuit is async; run it in a new event loop
        # since LangChain tools are called from sync context via asyncio.to_thread
        try:
            # Probes for a running loop; the value is unused, only whether it raises.
            asyncio.get_running_loop()
            # We're inside an event loop (shouldn't happen for tool calls via to_thread)
            # Use a new thread with its own loop
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(get_weather_for_circuit(location))).result(timeout=15)
        except RuntimeError:
            # No running event loop -- safe to use asyncio.run()
            result = asyncio.run(get_weather_for_circuit(location))

        if result.get("error"):
            return result["error"]

        current = result.get("current", {})
        hourly = result.get("hourly_forecast", [])
        track_context = result.get("track_context", "")
        strategy_impact = result.get("strategy_impact", "")
        circuit_name = result.get("circuit_name", location)

        lines = []
        lines.append(f"### Weather: {circuit_name} ({location})")
        lines.append("")

        # Current conditions
        lines.append("#### Current Conditions")
        lines.append(f"  - **Conditions:** {current.get('conditions', 'Unknown')}")
        lines.append(f"  - **Air temperature:** {current.get('air_temp_c', 'N/A')}C")
        lines.append(f"  - **Track temperature:** {current.get('track_temp_c', 'N/A')}C (estimated)")
        lines.append(f"  - **Humidity:** {current.get('humidity_pct', 'N/A')}%")
        lines.append(f"  - **Wind:** {current.get('wind_speed_kph', 'N/A')} km/h {current.get('wind_direction', '')}")
        lines.append(f"  - **Rain probability:** {current.get('rain_probability_pct', 'N/A')}%")
        lines.append("")

        # Hourly forecast
        if hourly:
            lines.append("#### Hourly Forecast")
            lines.append("| Time | Temp | Rain | Wind | Conditions |")
            lines.append("| :--- | :--- | :--- | :--- | :--------- |")
            lines.extend(
                f"| {h.get('time', '')} | {h.get('temp_c', '')}C "
                f"| {h.get('rain_probability_pct', '')}% "
                f"| {h.get('wind_speed_kph', '')} km/h "
                f"| {h.get('conditions', '')} |"
                for h in hourly
            )
            lines.append("")

        # Track context
        if track_context:
            lines.append(f"**Track context:** {track_context}")
            lines.append("")

        # Strategy impact
        if strategy_impact:
            lines.append(f"**Strategy impact:** {strategy_impact}")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("tool.weather_conditions.error", error=str(e))
        return f"Weather data fetch failed: {e}"


@tool
def perform_web_search(query: str) -> str:
    """
    Performs a real-time web search for F1 news, rumours, or recent events.

    Uses the Tavily search API. Returns the top 3 results with title,
    snippet, and source URL.  Use this for anything that may have changed
    after the model's knowledge cut-off (e.g. transfer rumours, latest news).
    """
    logger.info("tool.web_search", query=query)
    try:
        response = get_tavily_client().search(query=query, search_depth="basic", max_results=3)
        results = response.get("results", [])
        if not results:
            return "No search results found."
        return "\n\n".join(f"Source: {r['title']}\nSnippet: {r['content']}\nURL: {r['url']}" for r in results)
    except Exception as e:
        return f"Search failed: {e}"
