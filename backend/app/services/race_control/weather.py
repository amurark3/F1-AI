"""The race-day weather card: the race session's Open-Meteo forecast, or the reason there is none.

Until 9 Nov 2026 the card fell back on OpenWeatherMap's current conditions
whenever the race had no forecast. Their rain figure is the next three hours,
not race day: on 6 Nov the card read 5 % while Open-Meteo forecast ~90 % for the
São Paulo race window. No OpenWeatherMap reading reaches this card any more (the
chat weather tool still uses it). With no race-day forecast the card carries no
number, only the reason, in the weekend forecast's own words where it has them.
"""

from __future__ import annotations

from datetime import date

from app.services.race_control.session_weather import race_day_block, race_row

NOTE_NO_RACE_READING = "The race-day forecast has no rain reading."


def _opens_on(value: object) -> str | None:
    """The day a race past the forecast horizon gets its forecast, as the card prints it."""
    if not isinstance(value, str):
        return None
    day = date.fromisoformat(value)
    return f"The race-day forecast opens on {day.day} {day:%b}."


def _reason(session_weather: dict) -> str:
    """Why there is no race-day number: the race's horizon, the forecast's note, or no reading."""
    race = race_row(session_weather)
    opens = _opens_on(race.get("forecast_opens")) if race else None
    return opens or session_weather.get("note") or NOTE_NO_RACE_READING


def build_weather_block(session_weather: dict) -> dict:
    """The card's numbers from the race session's forecast; with none, null numbers and the reason."""
    return race_day_block(session_weather) or {
        "rain_risk": None,
        "track_temp_c": None,
        "wind_kph": None,
        "confidence": _reason(session_weather),
    }
