"""Hourly weather from Open-Meteo, for the hours a race weekend's sessions run.

Open-Meteo is keyless and serves an hourly forecast from today to fifteen days
ahead, and the same hourly series for roughly three months back. That reach is
the point: OpenWeatherMap's free tier forecasts five days in three-hour steps,
so on the Tuesday before a race the Sunday is still out of range.

Hours are requested and returned in UTC, the clock the schedule's session times
use. A missing reading stays ``None`` — a gap must never read as 0 % rain.

Weather data by Open-Meteo.com (CC BY 4.0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import threading
import time

import httpx
import structlog

from app.config import WEATHER_CACHE_TTL

logger = structlog.get_logger()

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com"
# The furthest ahead Open-Meteo forecasts, in days after today; a request that
# reaches past it is refused outright rather than answered in part.
FORECAST_HORIZON_DAYS = 15
# How far back the forecast endpoint still serves its hourly series.
PAST_DAYS_LIMIT = 92
REQUEST_TIMEOUT_SECONDS = 8.0

HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "is_day",
)


@dataclass(frozen=True)
class HourlyReading:
    """One hour of the series; any reading Open-Meteo left blank is ``None``."""

    time: datetime
    temperature_c: float | None
    humidity_pct: float | None
    rain_probability_pct: float | None
    precipitation_mm: float | None
    weather_code: int | None
    cloud_cover_pct: float | None
    wind_kph: float | None
    wind_direction_deg: float | None
    is_day: bool | None


_CacheKey = tuple[float, float, str, str]
_cache: dict[_CacheKey, tuple[float, tuple[HourlyReading, ...]]] = {}
_cache_lock = threading.Lock()


def _number(values: object, index: int) -> float | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _hour(stamp: object) -> datetime | None:
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp).replace(tzinfo=UTC)
    except ValueError:
        return None


def _reading(hourly: dict, index: int, moment: datetime) -> HourlyReading:
    code = _number(hourly.get("weather_code"), index)
    day = _number(hourly.get("is_day"), index)
    return HourlyReading(
        time=moment,
        temperature_c=_number(hourly.get("temperature_2m"), index),
        humidity_pct=_number(hourly.get("relative_humidity_2m"), index),
        rain_probability_pct=_number(hourly.get("precipitation_probability"), index),
        precipitation_mm=_number(hourly.get("precipitation"), index),
        weather_code=None if code is None else int(code),
        cloud_cover_pct=_number(hourly.get("cloud_cover"), index),
        wind_kph=_number(hourly.get("wind_speed_10m"), index),
        wind_direction_deg=_number(hourly.get("wind_direction_10m"), index),
        is_day=None if day is None else day >= 1,
    )


def parse_hourly(payload: object) -> tuple[HourlyReading, ...]:
    """Open-Meteo's column-per-variable answer as one reading per hour."""
    if not isinstance(payload, dict):
        return ()
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        return ()
    readings = []
    for index, stamp in enumerate(hourly["time"]):
        moment = _hour(stamp)
        if moment is not None:
            readings.append(_reading(hourly, index, moment))
    return tuple(readings)


def forecast_window(first: date, last: date, today: date) -> tuple[date, date] | None:
    """The part of ``first``..``last`` Open-Meteo will serve; None when none of it is."""
    start = max(first, today - timedelta(days=PAST_DAYS_LIMIT))
    end = min(last, today + timedelta(days=FORECAST_HORIZON_DAYS))
    return (start, end) if start <= end else None


def new_client() -> httpx.Client:
    return httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)


def _request(lat: float, lon: float, start: date, end: date) -> tuple[HourlyReading, ...] | None:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    try:
        with new_client() as client:
            response = client.get(OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("open_meteo.fetch_failed", lat=lat, lon=lon, error=str(exc))
        return None
    readings = parse_hourly(payload)
    if not readings:
        logger.warning("open_meteo.empty_series", lat=lat, lon=lon)
        return None
    return readings


def _remember(key: _CacheKey, stamp: float, readings: tuple[HourlyReading, ...]) -> None:
    with _cache_lock:
        expired = [old for old, (kept_at, _) in _cache.items() if stamp - kept_at >= WEATHER_CACHE_TTL]
        for old in expired:
            del _cache[old]
        _cache[key] = (stamp, readings)


def fetch_hourly(lat: float, lon: float, start: date, end: date) -> tuple[HourlyReading, ...] | None:
    """Every hour from ``start`` to ``end`` (UTC days, inclusive); None when the feed fails.

    A good answer is kept for ``WEATHER_CACHE_TTL`` seconds. A failure is not,
    so the next page view asks again rather than serving an outage for minutes.
    """
    key = (round(lat, 4), round(lon, 4), start.isoformat(), end.isoformat())
    now = time.monotonic()
    with _cache_lock:
        kept = _cache.get(key)
    if kept is not None and now - kept[0] < WEATHER_CACHE_TTL:
        return kept[1]
    readings = _request(lat, lon, start, end)
    if readings is not None:
        _remember(key, now, readings)
    return readings
