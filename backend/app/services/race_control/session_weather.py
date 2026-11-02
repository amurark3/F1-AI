"""Weather for each session of the selected weekend, from Open-Meteo's hourly series.

Each session is read off the hours it runs through, not off a single snapshot,
so a race that starts dry and turns wet in its second hour reads as wet: rain
probability and wind take the worst hour, temperatures the average, and the
condition the most severe WMO code in the window.

What the payload will not do is invent a reading. A session past the forecast
horizon says when its forecast opens; an outage or an unknown venue leaves every
session blank with a note naming why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING

from app.api.circuits import get_circuit_gps
from app.data.open_meteo import (
    FORECAST_HORIZON_DAYS,
    OPEN_METEO_ATTRIBUTION,
    fetch_hourly,
    forecast_window,
)
from app.data.weather import estimate_track_temp
from app.utils.f1_values import utc_isoformat

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from app.data.open_meteo import HourlyReading

SESSION_WEATHER_SOURCE = "Open-Meteo hourly forecast"
RACE_SESSION = "Race"
RACE_DAY_FORECAST = "Race-day forecast (Open-Meteo)"
RACE_DAY_RECORD = "Race-day model reading (Open-Meteo)"

# How long each session runs, so its forecast spans the hours it is on track.
# A Grand Prix is scheduled for two hours; every other session fits in one.
SESSION_MINUTES = {"Race": 120, "Sprint Qualifying": 45, "Sprint Shootout": 45}
DEFAULT_SESSION_MINUTES = 60
HOUR = timedelta(hours=1)
# Cloud cover assumed when the sun cannot heat the track: at night, or when the
# feed leaves cloud blank (the estimate then errs cool rather than hot).
NO_SUN_CLOUD_PCT = 100.0

STATUS_READY = "ready"
STATUS_PENDING = "pending"
STATUS_UNAVAILABLE = "unavailable"

NOTE_NO_SCHEDULE = "Session times are not published yet."
NOTE_NO_VENUE = "The circuit's location is unknown, so no forecast can be placed."
NOTE_PENDING = f"Forecasts open {FORECAST_HORIZON_DAYS} days before each session."
NOTE_ARCHIVED = "This weekend is older than the forecast archive."
NOTE_OFFLINE = "The forecast feed is unavailable right now."

# WMO weather interpretation codes, as Open-Meteo reports them.
WMO_CONDITIONS: dict[int, tuple[str, str]] = {
    0: ("clear", "Clear sky"),
    1: ("clear", "Mainly clear"),
    2: ("partly_cloudy", "Partly cloudy"),
    3: ("cloudy", "Overcast"),
    45: ("fog", "Fog"),
    48: ("fog", "Freezing fog"),
    51: ("drizzle", "Light drizzle"),
    53: ("drizzle", "Drizzle"),
    55: ("drizzle", "Dense drizzle"),
    56: ("drizzle", "Freezing drizzle"),
    57: ("drizzle", "Freezing drizzle"),
    61: ("rain", "Light rain"),
    63: ("rain", "Rain"),
    65: ("rain", "Heavy rain"),
    66: ("rain", "Freezing rain"),
    67: ("rain", "Freezing rain"),
    71: ("snow", "Light snow"),
    73: ("snow", "Snow"),
    75: ("snow", "Heavy snow"),
    77: ("snow", "Snow grains"),
    80: ("rain", "Rain showers"),
    81: ("rain", "Heavy showers"),
    82: ("rain", "Violent showers"),
    85: ("snow", "Snow showers"),
    86: ("snow", "Heavy snow showers"),
    95: ("storm", "Thunderstorm"),
    96: ("storm", "Thunderstorm with hail"),
    99: ("storm", "Thunderstorm with heavy hail"),
}
UNKNOWN_CONDITION = ("unknown", "Unclassified")


@dataclass(frozen=True)
class SessionSlot:
    name: str
    start: datetime
    end: datetime


def describe_code(code: int | None) -> tuple[str, str]:
    """A WMO code as the condition the UI draws and the label it prints."""
    return UNKNOWN_CONDITION if code is None else WMO_CONDITIONS.get(code, UNKNOWN_CONDITION)


def _present(values: Iterable[float | int | None]) -> list[float]:
    return [float(value) for value in values if value is not None]


def _mean(values: Iterable[float | None]) -> float | None:
    present = _present(values)
    return fmean(present) if present else None


def _peak(values: Iterable[float | int | None]) -> float | None:
    present = _present(values)
    return max(present) if present else None


def _total(values: Iterable[float | None]) -> float | None:
    present = _present(values)
    return sum(present) if present else None


def _rounded(value: float | None, digits: int | None = None) -> float | int | None:
    if value is None:
        return None
    return round(value) if digits is None else round(value, digits)


def _track_estimate(air: float | None, cloud: float | None, is_day: bool | None) -> float | None:
    if air is None:
        return None
    sky = cloud if is_day and cloud is not None else NO_SUN_CLOUD_PCT
    return estimate_track_temp(air, sky)


def summarise_window(readings: Sequence[HourlyReading], start: datetime, end: datetime) -> dict | None:
    """The session's weather from every hour it overlaps; None when no hour does."""
    hours = [reading for reading in readings if reading.time < end and reading.time + HOUR > start]
    if not hours:
        return None
    first = hours[0]
    air = _mean(reading.temperature_c for reading in hours)
    cloud = _mean(reading.cloud_cover_pct for reading in hours)
    code = _peak(reading.weather_code for reading in hours)
    condition, label = describe_code(None if code is None else int(code))
    return {
        "condition": condition,
        "label": label,
        "is_day": first.is_day,
        "air_temp_c": _rounded(air, 1),
        "track_temp_c": _track_estimate(air, cloud, first.is_day),
        "rain_probability_pct": _rounded(_peak(reading.rain_probability_pct for reading in hours)),
        "precipitation_mm": _rounded(_total(reading.precipitation_mm for reading in hours), 1),
        "wind_kph": _rounded(_peak(reading.wind_kph for reading in hours), 1),
        "wind_direction_deg": _rounded(first.wind_direction_deg),
        "humidity_pct": _rounded(_mean(reading.humidity_pct for reading in hours)),
        "cloud_cover_pct": _rounded(cloud),
    }


def _start_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def session_slots(race: dict | None) -> tuple[SessionSlot, ...]:
    """The weekend's sessions in running order, each with the window it is on track."""
    sessions = (race or {}).get("sessions")
    if not isinstance(sessions, dict):
        return ()
    slots = []
    for name, value in sessions.items():
        start = _start_time(value)
        if start is not None:
            minutes = SESSION_MINUTES.get(name, DEFAULT_SESSION_MINUTES)
            slots.append(SessionSlot(name=name, start=start, end=start + timedelta(minutes=minutes)))
    return tuple(sorted(slots, key=lambda slot: slot.start))


def _phase(slot: SessionSlot, now: datetime) -> str:
    if now >= slot.end:
        return "done"
    if now >= slot.start:
        return "live"
    return "upcoming"


def _forecast_opens(slot: SessionSlot, now: datetime) -> str | None:
    """The day a session beyond the horizon gets its forecast; None once it has one."""
    if slot.start.date() <= now.date() + timedelta(days=FORECAST_HORIZON_DAYS):
        return None
    return (slot.start.date() - timedelta(days=FORECAST_HORIZON_DAYS)).isoformat()


def _session_row(slot: SessionSlot, readings: Sequence[HourlyReading], now: datetime) -> dict:
    opens = _forecast_opens(slot, now)
    return {
        "name": slot.name,
        "starts_at": utc_isoformat(slot.start),
        "ends_at": utc_isoformat(slot.end),
        "phase": _phase(slot, now),
        "forecast": None if opens else summarise_window(readings, slot.start, slot.end),
        "forecast_opens": opens,
    }


def _weekend_readings(
    race: dict, slots: Sequence[SessionSlot], now: datetime
) -> tuple[tuple[HourlyReading, ...], str, str | None]:
    """The hourly series for the weekend, or the status and note explaining its absence."""
    coords = get_circuit_gps(race.get("location") or "")
    if coords is None:
        return (), STATUS_UNAVAILABLE, NOTE_NO_VENUE
    first = slots[0].start.date()
    window = forecast_window(first, max(slot.end for slot in slots).date(), now.date())
    if window is None:
        return (), *((STATUS_PENDING, NOTE_PENDING) if first > now.date() else (STATUS_UNAVAILABLE, NOTE_ARCHIVED))
    readings = fetch_hourly(*coords, *window)
    if readings is None:
        return (), STATUS_UNAVAILABLE, NOTE_OFFLINE
    return readings, STATUS_READY, None


def _payload(status: str, note: str | None, sessions: list[dict]) -> dict:
    return {
        "status": status,
        "note": note,
        "source": SESSION_WEATHER_SOURCE,
        "attribution": OPEN_METEO_ATTRIBUTION,
        "sessions": sessions,
    }


def build_session_weather(race: dict | None, now: datetime | None = None) -> dict:
    """Every session of ``race`` with the weather for its window, or a reason there is none."""
    moment = now or datetime.now(UTC)
    slots = session_slots(race)
    if not race or not slots:
        return _payload(STATUS_UNAVAILABLE, NOTE_NO_SCHEDULE, [])
    readings, status, note = _weekend_readings(race, slots, moment)
    sessions = [_session_row(slot, readings, moment) for slot in slots]
    if status == STATUS_READY and not any(row["forecast"] for row in sessions):
        status, note = STATUS_UNAVAILABLE, NOTE_OFFLINE
    return _payload(status, note, sessions)


def race_day_block(session_weather: dict) -> dict | None:
    """The summary card's numbers from the Race session; None without a race-day rain reading."""
    race = next((row for row in session_weather.get("sessions", []) if row["name"] == RACE_SESSION), None)
    forecast = race["forecast"] if race else None
    if not forecast or forecast.get("rain_probability_pct") is None:
        return None
    return {
        "rain_risk": forecast["rain_probability_pct"],
        "track_temp_c": forecast["track_temp_c"],
        "wind_kph": forecast["wind_kph"],
        "confidence": RACE_DAY_RECORD if race["phase"] == "done" else RACE_DAY_FORECAST,
    }
