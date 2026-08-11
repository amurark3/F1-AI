"""
Weather Module
==============
Fetches live weather data from OpenWeatherMap for F1 circuit locations.
Combines raw weather numbers with track-specific strategic context.

Features:
  - Current conditions: air temp, humidity, wind, rain probability
  - Hourly forecast for session duration (next 3-4 hours)
  - Track surface temperature estimate from air temp + sun heuristic
  - Track-specific context (street circuit drainage, altitude, desert sand)
  - Strategy impact assessment based on rain probability thresholds
  - TTL-based caching to avoid excessive API calls

Uses httpx.AsyncClient for async HTTP calls.  Falls back from One Call 3.0
to 2.5 current weather API when the premium subscription is not available.
"""

from datetime import datetime, timezone
import time

import httpx
import structlog

from app.api.circuits import CIRCUIT_DATA, get_circuit_gps
from app.config import OPENWEATHERMAP_API_KEY, WEATHER_CACHE_TTL

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# In-memory TTL cache — simple dict for single-threaded asyncio
# ---------------------------------------------------------------------------
# location_key -> (timestamp, weather_data_dict)
_weather_cache: dict[str, tuple[float, dict]] = {}


# ---------------------------------------------------------------------------
# Wind direction helper
# ---------------------------------------------------------------------------
_WIND_DIRECTIONS = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]


def _degrees_to_direction(degrees: float) -> str:
    """Convert wind direction in degrees to a compass direction string."""
    idx = round(degrees / 22.5) % 16
    return _WIND_DIRECTIONS[idx]


# ---------------------------------------------------------------------------
# Track surface temperature estimate
# ---------------------------------------------------------------------------
def _estimate_track_temp(air_temp_c: float, cloud_pct: int) -> float:
    """Estimate track surface temperature from air temperature and cloud cover.

    Track surface is typically 15-25C above air temp in direct sunlight,
    and only 5-10C above in overcast conditions.  This is a rough heuristic;
    actual track temp depends on surface color, recent rain, time of day, etc.
    """
    # Sun exposure factor: 1.0 = clear sky, 0.0 = fully overcast
    sun_factor = max(0.0, 1.0 - (cloud_pct / 100.0))

    # Base heating: 5C above air temp (overcast) to 20C above (clear sun)
    heating = 5.0 + (15.0 * sun_factor)

    return round(air_temp_c + heating, 1)


# ---------------------------------------------------------------------------
# Track-specific context
# ---------------------------------------------------------------------------
# Circuits considered "desert" for context purposes
_DESERT_CIRCUITS = {"Sakhir", "Lusail", "Yas Island", "Abu Dhabi", "Yas Marina", "Jeddah"}

# Circuits considered "coastal" for wind context
_COASTAL_CIRCUITS = {
    "Melbourne",
    "Jeddah",
    "Miami",
    "Miami Gardens",
    "Marina Bay",
    "Singapore",
    "Baku",
    "Monte Carlo",
    "Monaco",
    "Zandvoort",
}

# High-altitude circuits (elevation > 2000m)
_HIGH_ALTITUDE_CIRCUITS = {"Mexico City"}


def _get_track_context(location: str) -> str:
    """Return track-specific weather context based on circuit characteristics."""
    circuit_data = CIRCUIT_DATA.get(location, {})
    circuit_type = circuit_data.get("circuit_type", "")

    contexts = []

    if "street" in circuit_type.lower() or "Street" in circuit_type:
        contexts.append(
            "Street circuit -- limited drainage means wet conditions "
            "significantly impact grip and increase Safety Car probability"
        )

    if location in _HIGH_ALTITUDE_CIRCUITS:
        contexts.append(
            "High altitude (2,240m) reduces air density -- affects engine performance and aerodynamic downforce"
        )

    if location in _DESERT_CIRCUITS:
        contexts.append(
            "Desert circuit -- sand on track surface is common, especially "
            "early in the weekend. Track evolution is significant"
        )

    if location in _COASTAL_CIRCUITS and not contexts:
        contexts.append("Coastal location -- wind direction can change significantly during the session")

    if not contexts:
        return ""

    return ". ".join(contexts)


# ---------------------------------------------------------------------------
# Strategy impact assessment
# ---------------------------------------------------------------------------
def _assess_strategy_impact(hourly_forecasts: list[dict]) -> str:
    """Determine the strategy impact message based on rain probabilities.

    Thresholds:
      - Any hour pop >= 0.4 -> High rain
      - Any hour pop >= 0.2 -> Moderate rain
      - Otherwise -> Low rain
    """
    if not hourly_forecasts:
        return "No forecast data available"

    max_rain = max(
        (h.get("rain_probability_pct", 0) / 100.0 for h in hourly_forecasts),
        default=0.0,
    )

    if max_rain >= 0.4:
        return "High rain probability -- dual dry/wet strategy scenarios recommended"
    if max_rain >= 0.2:
        return "Moderate rain risk -- teams may prepare intermediate tyres as backup"
    return "Low rain probability -- standard dry strategy expected"


# ---------------------------------------------------------------------------
# OpenWeatherMap API calls
# ---------------------------------------------------------------------------
async def _fetch_onecall(lat: float, lon: float, client: httpx.AsyncClient) -> dict | None:
    """Try One Call 3.0 API (requires subscription)."""
    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric",
        "exclude": "minutely,daily,alerts",
    }

    try:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
        logger.debug(
            "weather.onecall_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
    except Exception as exc:
        logger.debug("weather.onecall_error", error=str(exc))

    return None


async def _fetch_current_weather(lat: float, lon: float, client: httpx.AsyncClient) -> dict | None:
    """Fallback to 2.5 current weather API (free tier)."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric",
    }

    try:
        resp = await client.get(url, params=params, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(
            "weather.current_api_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
    except Exception as exc:
        logger.warning("weather.current_api_error", error=str(exc))

    return None


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------
def _build_from_onecall(data: dict, _location: str) -> dict:
    """Build weather response from One Call 3.0 API data."""
    current = data.get("current", {})
    hourly_raw = data.get("hourly", [])

    # Current conditions
    air_temp = current.get("temp", 0.0)
    humidity = current.get("humidity", 0)
    wind_speed_ms = current.get("wind_speed", 0.0)
    wind_deg = current.get("wind_deg", 0)
    clouds = current.get("clouds", 0)
    weather_desc = current.get("weather", [{}])[0].get("description", "unknown")

    # Rain probability from first hourly entry
    rain_prob = 0.0
    if hourly_raw:
        rain_prob = hourly_raw[0].get("pop", 0.0)

    wind_speed_kph = round(wind_speed_ms * 3.6, 1)
    track_temp = _estimate_track_temp(air_temp, clouds)

    current_conditions = {
        "air_temp_c": round(air_temp, 1),
        "track_temp_c": track_temp,
        "humidity_pct": humidity,
        "wind_speed_kph": wind_speed_kph,
        "wind_direction": _degrees_to_direction(wind_deg),
        "rain_probability_pct": round(rain_prob * 100),
        "conditions": weather_desc.capitalize(),
    }

    # Hourly forecast (next 4 hours)
    hourly_forecast = []
    for h in hourly_raw[:4]:
        dt = datetime.fromtimestamp(h.get("dt", 0), tz=timezone.utc)
        h_desc = h.get("weather", [{}])[0].get("description", "unknown")
        h_wind = round(h.get("wind_speed", 0.0) * 3.6, 1)
        h_pop = h.get("pop", 0.0)

        hourly_forecast.append(
            {
                "time": dt.strftime("%H:%M"),
                "temp_c": round(h.get("temp", 0.0), 1),
                "rain_probability_pct": round(h_pop * 100),
                "wind_speed_kph": h_wind,
                "conditions": h_desc.capitalize(),
            }
        )

    return current_conditions, hourly_forecast


def _build_from_current(data: dict, _location: str) -> tuple[dict, list[dict]]:
    """Build weather response from 2.5 current weather API (no hourly forecast)."""
    main = data.get("main", {})
    wind = data.get("wind", {})
    clouds_data = data.get("clouds", {})
    weather_list = data.get("weather", [{}])

    air_temp = main.get("temp", 0.0)
    humidity = main.get("humidity", 0)
    wind_speed_ms = wind.get("speed", 0.0)
    wind_deg = wind.get("deg", 0)
    clouds_pct = clouds_data.get("all", 0)
    desc = weather_list[0].get("description", "unknown") if weather_list else "unknown"

    wind_speed_kph = round(wind_speed_ms * 3.6, 1)
    track_temp = _estimate_track_temp(air_temp, clouds_pct)

    # Rain probability heuristic from current conditions
    # (2.5 API doesn't have pop; use weather code as proxy)
    weather_id = weather_list[0].get("id", 800) if weather_list else 800
    if weather_id < 600:  # Rain/drizzle/thunderstorm codes
        rain_prob_pct = 80
    elif 600 <= weather_id < 700:  # Snow
        rain_prob_pct = 60
    elif 700 <= weather_id < 800:  # Atmosphere (fog, mist)
        rain_prob_pct = 30
    elif clouds_pct > 80:
        rain_prob_pct = 20
    else:
        rain_prob_pct = 5

    current_conditions = {
        "air_temp_c": round(air_temp, 1),
        "track_temp_c": track_temp,
        "humidity_pct": humidity,
        "wind_speed_kph": wind_speed_kph,
        "wind_direction": _degrees_to_direction(wind_deg),
        "rain_probability_pct": rain_prob_pct,
        "conditions": desc.capitalize(),
    }

    # No hourly forecast available from 2.5 API
    hourly_forecast = []

    return current_conditions, hourly_forecast


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------
async def get_weather_for_circuit(location: str) -> dict:
    """Fetch weather data for an F1 circuit location.

    Args:
        location: Circuit location key (e.g. 'Monaco', 'Sakhir', 'Silverstone').
                  Must match a key in CIRCUIT_DATA.

    Returns:
        Dict with current conditions, hourly forecast, track context,
        and strategy impact assessment.
    """
    logger.info("weather.fetch", location=location)

    # Check cache first
    if location in _weather_cache:
        cached_time, cached_data = _weather_cache[location]
        if time.time() - cached_time < WEATHER_CACHE_TTL:
            logger.debug("weather.cache_hit", location=location)
            return cached_data

    # Validate API key
    if not OPENWEATHERMAP_API_KEY:
        logger.warning("weather.no_api_key")
        return {
            "location": location,
            "error": "OpenWeatherMap API key not configured. "
            "Set OPENWEATHERMAP_API_KEY environment variable. "
            "Get a key at https://home.openweathermap.org/api_keys",
        }

    # Look up GPS coordinates
    coords = get_circuit_gps(location)
    if coords is None:
        # Try looking up via circuit_data keys
        circuit_data = CIRCUIT_DATA.get(location, {})
        if not circuit_data:
            return {
                "location": location,
                "error": f"Circuit '{location}' not found in circuit database. "
                f"Available locations: {', '.join(sorted(CIRCUIT_DATA.keys()))}",
            }

    lat, lon = coords
    circuit_data = CIRCUIT_DATA.get(location, {})
    circuit_name = circuit_data.get("circuit_name", location)

    # Fetch weather data
    async with httpx.AsyncClient() as client:
        # Try One Call 3.0 first
        onecall_data = await _fetch_onecall(lat, lon, client)

        if onecall_data:
            current_conditions, hourly_forecast = _build_from_onecall(onecall_data, location)
            logger.info("weather.onecall_success", location=location)
        else:
            # Fallback to 2.5 current weather
            current_data = await _fetch_current_weather(lat, lon, client)

            if current_data:
                current_conditions, hourly_forecast = _build_from_current(current_data, location)
                logger.info("weather.current_fallback", location=location)
            else:
                return {
                    "location": location,
                    "circuit_name": circuit_name,
                    "error": "Failed to fetch weather data from OpenWeatherMap. "
                    "Please check your API key and network connection.",
                }

    # Build response
    track_context = _get_track_context(location)
    strategy_impact = _assess_strategy_impact(hourly_forecast)

    # If no hourly forecast (2.5 fallback), use current conditions for strategy
    if not hourly_forecast:
        strategy_impact = _assess_strategy_impact([current_conditions])

    result = {
        "location": location,
        "circuit_name": circuit_name,
        "current": current_conditions,
        "hourly_forecast": hourly_forecast,
        "track_context": track_context,
        "strategy_impact": strategy_impact,
    }

    # Cache the result
    _weather_cache[location] = (time.time(), result)
    logger.info("weather.cached", location=location)

    return result
