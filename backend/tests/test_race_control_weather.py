"""Tests for app.services.race_control.weather: the race-day weather card.

The card used to fall back on OpenWeatherMap's current conditions whenever the
race session had no Open-Meteo forecast. Those conditions are the next three
hours, not race day: on 6 Nov 2026 the card read 5 % rain while Open-Meteo
forecast ~90 % for the São Paulo race window.

So the property under test is that the card carries the race session's forecast
or no number at all. With no forecast it says why, in the forecast's own words,
and no OpenWeatherMap reading can reach it by any path.
"""

from __future__ import annotations

import pytest

from app.data import weather as owm
from app.services.race_control import weather as module
from app.services.race_control.session_weather import NOTE_OFFLINE, NOTE_PENDING, RACE_DAY_FORECAST

pytestmark = pytest.mark.unit

RACE_FORECAST = {"rain_probability_pct": 92, "track_temp_c": 24.1, "wind_kph": 18.0}


def _weekend(status: str = "ready", note: str | None = None, race: dict | None = None, **extra) -> dict:
    sessions = [{"name": "Qualifying", "phase": "upcoming", "forecast": RACE_FORECAST, "forecast_opens": None}]
    if race is not None:
        sessions.append({"name": "Race", "phase": "upcoming", "forecast_opens": None, **race})
    return {"status": status, "note": note, "sessions": sessions, **extra}


def _blank(reason: str) -> dict:
    return {"rain_risk": None, "track_temp_c": None, "wind_kph": None, "confidence": reason}


def test_the_card_reads_the_race_sessions_forecast():
    card = module.build_weather_block(_weekend(race={"forecast": RACE_FORECAST}))

    assert card == {"rain_risk": 92, "track_temp_c": 24.1, "wind_kph": 18.0, "confidence": RACE_DAY_FORECAST}


@pytest.mark.parametrize(
    ("status", "note"),
    [("unavailable", NOTE_OFFLINE), ("pending", NOTE_PENDING)],
    ids=["feed-down", "beyond-horizon"],
)
def test_with_no_race_day_forecast_the_card_carries_the_forecasts_note_and_no_number(status, note):
    card = module.build_weather_block(_weekend(status, note, race={"forecast": None}))

    assert card == _blank(note)


def test_a_race_past_the_horizon_says_the_day_its_forecast_opens():
    weekend = _weekend(race={"forecast": None, "forecast_opens": "2026-11-05"})

    assert module.build_weather_block(weekend) == _blank("The race-day forecast opens on 5 Nov.")


@pytest.mark.parametrize(
    "race",
    [None, {"forecast": {**RACE_FORECAST, "rain_probability_pct": None}}],
    ids=["no-race-session", "no-rain-reading"],
)
def test_a_weekend_with_no_race_rain_reading_says_so_without_a_number(race):
    assert module.build_weather_block(_weekend(race=race)) == _blank(module.NOTE_NO_RACE_READING)


def test_no_openweathermap_reading_ever_reaches_the_card(monkeypatch):
    """Even with OpenWeatherMap answering, a weekend with no race forecast shows no number."""
    asked: list[str] = []

    async def current_conditions(location: str) -> dict:
        asked.append(location)
        return {"current": {"rain_probability_pct": 5, "track_temp_c": 29, "wind_speed_kph": 13}}

    monkeypatch.setattr(owm, "get_weather_for_circuit", current_conditions)

    card = module.build_weather_block(_weekend("unavailable", NOTE_OFFLINE, race={"forecast": None}))

    assert card == _blank(NOTE_OFFLINE)
    assert asked == []
    assert not hasattr(module, "get_weather_for_circuit")
