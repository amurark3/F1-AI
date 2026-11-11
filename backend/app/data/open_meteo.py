"""Hourly weather from Open-Meteo, for the hours a race weekend's sessions run.

Open-Meteo is keyless and serves an hourly forecast from today to fifteen days
ahead, and the same hourly series for roughly three months back. That reach is
the point: OpenWeatherMap's free tier forecasts five days in three-hour steps,
so on the Tuesday before a race the Sunday is still out of range.

Hours are requested and returned in UTC, the clock the schedule's session times
use. A missing reading stays ``None`` — a gap must never read as 0 % rain.

The call is retried once on a 429, a 5xx or a timeout, and every failed attempt
is logged with its HTTP status or exception type. When it still fails, the
venue's last good series (``open_meteo_store``) is served, marked ``stored``
with the time it was fetched, so the page can say "as of" instead of going
blank or passing an old forecast off as new. The failed request is then not
sent again for ``FAILURE_COOLDOWN_SECONDS``: a feed that times out costs up to
17 s a call, and without the pause every page view would wait that long.

Weather data by Open-Meteo.com (CC BY 4.0).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
import threading
import time

import httpx
import structlog

from app.config import WEATHER_CACHE_TTL
from app.data.open_meteo_store import forecast_store, venue_key
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com"
# The furthest ahead Open-Meteo forecasts, in days after today; a request that
# reaches past it is refused outright rather than answered in part.
FORECAST_HORIZON_DAYS = 15
# How far back the forecast endpoint still serves its hourly series.
PAST_DAYS_LIMIT = 92
REQUEST_TIMEOUT_SECONDS = 8.0
# One retry, after a short pause, for the failures a second try can fix: a rate
# limit (429), a server error (5xx) or a timeout. Any other 4xx is final.
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.0
TOO_MANY_REQUESTS = 429
SERVER_ERROR = 500
# After a call fails (both attempts, or one a retry cannot fix), the same
# request is not sent again for this long: the stored series, or no forecast,
# is served meanwhile. While the feed times out each call costs 8 s + 1 s + 8 s,
# and without the pause every page view would wait that long and hold a thread.
FAILURE_COOLDOWN_SECONDS = 300.0
# Open-Meteo explains a refusal in a JSON ``reason``; logs keep this much of it.
REASON_LOG_CHARS = 200

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


@dataclass(frozen=True)
class HourlySeries:
    """One answer's hours and when Open-Meteo gave it.

    ``stored`` marks the venue's last good series, served because the live call
    failed; its ``fetched_at`` is what the page's "as of" label reports.
    """

    readings: tuple[HourlyReading, ...]
    fetched_at: datetime
    stored: bool = False


@dataclass(frozen=True)
class _Attempt:
    """One request's outcome: the decoded body, or a failure and whether a retry may fix it."""

    payload: object = None
    failed: bool = False
    retryable: bool = False


@dataclass(frozen=True)
class _Cooldown:
    """A request whose last call failed: when, and whether a skipped view has been logged since."""

    failed_at: float
    skip_logged: bool = False


@dataclass(frozen=True)
class _Recall:
    """What memory holds for a request: a fresh answer, or a cooldown that rules out calling."""

    series: HourlySeries | None = None
    cooling_down: bool = False
    first_skip: bool = False
    retry_in: float = 0.0


_CacheKey = tuple[float, float, str, str]
_cache: dict[_CacheKey, tuple[float, HourlySeries]] = {}
_failures: dict[_CacheKey, _Cooldown] = {}
_cache_lock = threading.Lock()
_sleep = time.sleep
_clock = time.monotonic


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


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


def _hourly_block(payload: object) -> dict | None:
    """The answer's ``hourly`` columns, or None when it has no list of hours."""
    if not isinstance(payload, dict):
        return None
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        return None
    return hourly


def parse_hourly(payload: object) -> tuple[HourlyReading, ...]:
    """Open-Meteo's column-per-variable answer as one reading per hour."""
    hourly = _hourly_block(payload)
    if hourly is None:
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


def _reason(response: httpx.Response) -> str | None:
    """The refusal's own explanation, when Open-Meteo sent one."""
    try:
        body = response.json()
    except ValueError:
        return None
    reason = body.get("reason") if isinstance(body, dict) else None
    return reason[:REASON_LOG_CHARS] if isinstance(reason, str) else None


def _failed(lat: float, lon: float, attempt: int, *, retryable: bool, **detail: object) -> _Attempt:
    logger.warning(
        "open_meteo.fetch_failed",
        lat=lat,
        lon=lon,
        attempt=attempt,
        retrying=retryable and attempt < MAX_ATTEMPTS,
        **detail,
    )
    return _Attempt(failed=True, retryable=retryable)


def _attempt(params: dict, lat: float, lon: float, attempt: int) -> _Attempt:
    try:
        with new_client() as client:
            response = client.get(OPEN_METEO_FORECAST_URL, params=params)
    except httpx.TimeoutException as exc:
        return _failed(lat, lon, attempt, retryable=True, error_type=type(exc).__name__, error=str(exc))
    except httpx.HTTPError as exc:
        return _failed(lat, lon, attempt, retryable=False, error_type=type(exc).__name__, error=str(exc))
    status = response.status_code
    if not response.is_success:
        transient = status == TOO_MANY_REQUESTS or status >= SERVER_ERROR
        return _failed(lat, lon, attempt, retryable=transient, status=status, reason=_reason(response))
    try:
        return _Attempt(payload=response.json())
    except ValueError as exc:
        return _failed(lat, lon, attempt, retryable=False, status=status, error_type=type(exc).__name__, error=str(exc))


def _request(lat: float, lon: float, start: date, end: date) -> tuple[dict, tuple[HourlyReading, ...]] | None:
    """Open-Meteo's ``hourly`` block and its readings; None when no good answer came."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    outcome = _attempt(params, lat, lon, 1)
    if outcome.failed and outcome.retryable:
        _sleep(RETRY_BACKOFF_SECONDS)
        outcome = _attempt(params, lat, lon, MAX_ATTEMPTS)
    if outcome.failed:
        return None
    hourly = _hourly_block(outcome.payload)
    readings = parse_hourly(outcome.payload)
    if hourly is None or not readings:
        logger.warning("open_meteo.empty_series", lat=lat, lon=lon)
        return None
    return hourly, readings


def _last_good(lat: float, lon: float, start: date, end: date) -> HourlySeries | None:
    """The venue's stored series, cut to the days asked for; None when it covers none of them."""
    stored = forecast_store.last_good(venue_key(lat, lon))
    if stored is None:
        return None
    readings = tuple(
        reading for reading in parse_hourly({"hourly": stored.hourly}) if start <= reading.time.date() <= end
    )
    if not readings:
        return None
    return HourlySeries(readings=readings, fetched_at=stored.fetched_at, stored=True)


def _prune(stamp: float) -> None:
    """Drop answers and cooldowns that have run out. Call under ``_cache_lock``."""
    for old in [old for old, (kept_at, _) in _cache.items() if stamp - kept_at >= WEATHER_CACHE_TTL]:
        del _cache[old]
    for old in [old for old, cooldown in _failures.items() if stamp - cooldown.failed_at >= FAILURE_COOLDOWN_SECONDS]:
        del _failures[old]


def _remember(key: _CacheKey, stamp: float, series: HourlySeries) -> None:
    """Keep a good answer; it ends any cooldown a concurrent view's failure started."""
    with _cache_lock:
        _prune(stamp)
        _failures.pop(key, None)
        _cache[key] = (stamp, series)


def _remember_failure(key: _CacheKey, stamp: float) -> None:
    with _cache_lock:
        _prune(stamp)
        _failures[key] = _Cooldown(failed_at=stamp)


def _recall(key: _CacheKey, now: float) -> _Recall:
    """A fresh answer for the request, or whether its cooldown rules out a call (the first skip is flagged)."""
    with _cache_lock:
        kept = _cache.get(key)
        if kept is not None and now - kept[0] < WEATHER_CACHE_TTL:
            return _Recall(series=kept[1])
        cooldown = _failures.get(key)
        if cooldown is None or now - cooldown.failed_at >= FAILURE_COOLDOWN_SECONDS:
            return _Recall()
        if not cooldown.skip_logged:
            _failures[key] = replace(cooldown, skip_logged=True)
    return _Recall(
        cooling_down=True,
        first_skip=not cooldown.skip_logged,
        retry_in=cooldown.failed_at + FAILURE_COOLDOWN_SECONDS - now,
    )


def _announced(lat: float, lon: float, series: HourlySeries | None) -> HourlySeries | None:
    """The stored series a failed call falls back on, logged; views in the cooldown get it silently."""
    if series is not None:
        logger.info("open_meteo.serving_stored", lat=lat, lon=lon, fetched_at=utc_isoformat(series.fetched_at))
    return series


def fetch_hourly(lat: float, lon: float, start: date, end: date) -> HourlySeries | None:
    """Every hour from ``start`` to ``end`` (UTC days, inclusive); None when there is none to give.

    A good answer is kept in memory for ``WEATHER_CACHE_TTL`` seconds and stored
    as the venue's last good series. A failure is not kept as an answer, but the
    same request is not sent again for ``FAILURE_COOLDOWN_SECONDS``. Until a call
    succeeds it is answered from the stored series, marked ``stored``, or None
    when the venue has never had a good answer for these days.
    """
    key = (round(lat, 4), round(lon, 4), start.isoformat(), end.isoformat())
    now = _clock()
    recall = _recall(key, now)
    if recall.series is not None:
        return recall.series
    if recall.cooling_down:
        if recall.first_skip:
            logger.info("open_meteo.fetch_skipped", lat=lat, lon=lon, retry_in_seconds=round(recall.retry_in))
        return _last_good(lat, lon, start, end)
    answer = _request(lat, lon, start, end)
    if answer is None:
        _remember_failure(key, _clock())
        return _announced(lat, lon, _last_good(lat, lon, start, end))
    hourly, readings = answer
    series = HourlySeries(readings=readings, fetched_at=_utcnow())
    _remember(key, now, series)
    forecast_store.keep(venue_key(lat, lon), series.fetched_at, hourly)
    return series
