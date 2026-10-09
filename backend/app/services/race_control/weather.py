"""The weather card, live from OpenWeatherMap or honestly blank."""

from __future__ import annotations

import asyncio

import structlog

from app.data.weather import get_weather_for_circuit

logger = structlog.get_logger()

WEATHER_FEED_OFFLINE = "External forecast feed not connected"
WEATHER_FEED_LIVE = "Live forecast (OpenWeatherMap)"


def _offline_weather_block() -> dict:
    """Honest 'no live feed' block — null values, no fabricated numbers."""
    return {
        "rain_risk": None,
        "track_temp_c": None,
        "wind_kph": None,
        "confidence": WEATHER_FEED_OFFLINE,
    }


def build_weather_block(race: dict | None) -> dict:
    """Fetch live weather for the selected race's circuit location.

    Degrades to an explicit offline block when no location is available, no
    API key is configured, or the forecast call fails — never invents numbers.

    ``build_overview`` runs in a worker thread (see the race-control router,
    which offloads it via ``asyncio.to_thread``), so no event loop is running
    on this thread and ``asyncio.run`` can drive the async weather client.
    """
    location = (race or {}).get("location")
    if not location:
        return _offline_weather_block()

    try:
        weather = asyncio.run(get_weather_for_circuit(location))
    except Exception as exc:
        logger.warning("race_control.weather.failed", location=location, error=str(exc))
        return _offline_weather_block()

    current = weather.get("current") if isinstance(weather, dict) else None
    if not current or weather.get("error"):
        logger.info("race_control.weather.offline", location=location, reason=weather.get("error"))
        return _offline_weather_block()

    return {
        "rain_risk": current.get("rain_probability_pct"),
        "track_temp_c": current.get("track_temp_c"),
        "wind_kph": current.get("wind_speed_kph"),
        "confidence": WEATHER_FEED_LIVE,
    }
