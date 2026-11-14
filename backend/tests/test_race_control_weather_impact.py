"""Tests for app.services.race_control.weather_impact — the prediction's race-day weather call.

Until 11 Nov 2026 every prediction said ``"weather_impact": "dry"``, a
placeholder. That included R20 São Paulo, which ran under an 88–92 % forecast
for the race window. The call now reads the race-day forecast the risk register
grades, with the register's own cut-offs, so the two can never disagree:

* ``wet`` at or above ``RAIN_RISK_HIGH``, ``mixed`` from ``RAIN_RISK_MODERATE``,
  ``dry`` below it — and ``dry`` only with a real Open-Meteo race-window reading;
* ``unknown`` whenever there is no reading: the feed is down (OpenWeatherMap is
  never asked instead), the race is past the forecast horizon, or the venue or
  race session is unknown;
* point in time: a call computed once the race has started may not read the
  hours that already ran (Open-Meteo's model record of what happened), so it is
  ``unknown`` and Open-Meteo is not even asked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from app.data import weather as owm
from app.data.open_meteo import HourlyReading, HourlySeries
from app.services.race_control import session_weather, weather_impact as module
from app.services.race_control.risk import RAIN_RISK_HIGH, RAIN_RISK_MODERATE

# FastF1's schedule row for São Paulo 2026 (R20), the shape `_load_event_context`
# hands compute: naive UTC timestamps, one name and start per session slot.
SAO_PAULO_ROW = pd.Series(
    {
        "RoundNumber": 20,
        "EventName": "São Paulo Grand Prix",
        "Location": "São Paulo",
        "Country": "Brazil",
        "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp("2026-11-06 14:30"),
        "Session2": "Sprint Qualifying",
        "Session2DateUtc": pd.Timestamp("2026-11-06 18:30"),
        "Session3": "Sprint",
        "Session3DateUtc": pd.Timestamp("2026-11-07 14:00"),
        "Session4": "Qualifying",
        "Session4DateUtc": pd.Timestamp("2026-11-07 18:00"),
        "Session5": "Race",
        "Session5DateUtc": pd.Timestamp("2026-11-08 17:00"),
    }
)
RACE_START = datetime(2026, 11, 8, 17, tzinfo=UTC)
# Saturday evening, after qualifying: when R20's post-qualifying call was computed.
SATURDAY = datetime(2026, 11, 7, 21, tzinfo=UTC)
# Open-Meteo's rain probability for 15:00-20:00 UTC on race day, as it answered
# on 6 Nov 2026 (STATUS.md log). The race runs 17:00-19:00: 92 % then 90 %.
R20_RACE_DAY_RAIN = {15: 94.0, 16: 93.0, 17: 92.0, 18: 90.0, 19: 88.0, 20: 86.0}


def _series(race_day: dict[int, float | None], *, otherwise: float | None = 30.0, **series) -> HourlySeries:
    """Three days of hours from Friday; race-day hours read ``race_day`` (by UTC hour), the rest ``otherwise``."""
    start = datetime(2026, 11, 6, tzinfo=UTC)
    hours = (start + timedelta(hours=offset) for offset in range(72))
    readings = tuple(
        HourlyReading(
            time=moment,
            temperature_c=21.0,
            humidity_pct=80.0,
            rain_probability_pct=race_day.get(moment.hour, otherwise) if moment.day == 8 else otherwise,
            precipitation_mm=0.0,
            weather_code=61,
            cloud_cover_pct=100.0,
            wind_kph=14.0,
            wind_direction_deg=150.0,
            is_day=True,
        )
        for moment in hours
    )
    return HourlySeries(readings=readings, **{"fetched_at": SATURDAY, **series})


def _race_window(rain: float) -> dict[int, float]:
    """Race-day hours where the two race hours (17:00, 18:00 UTC) read ``rain``."""
    return {17: rain, 18: rain}


@pytest.fixture
def open_meteo(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Serve the weekend forecast a series (or an outage); returns every request made."""
    asked: list[tuple] = []
    served: dict[str, HourlySeries | None] = {"series": None}

    def fetch(*args) -> HourlySeries | None:
        asked.append(args)
        return served["series"]

    def install(series: HourlySeries | None) -> list[tuple]:
        served["series"] = series
        return asked

    monkeypatch.setattr(session_weather, "fetch_hourly", fetch)
    return install


# ---------------------------------------------------------------------------
# The grade: the risk register's cut-offs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_r20_race_window_forecast_makes_the_call_wet(open_meteo):
    asked = open_meteo(_series(R20_RACE_DAY_RAIN))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_WET
    # The weekend is read the way the Command Center reads it (venue + every
    # session's window), so both share one cached Open-Meteo answer.
    assert asked == [(-23.7036, -46.6997, date(2026, 11, 6), date(2026, 11, 8))]


@pytest.mark.unit
def test_a_medium_race_window_reading_makes_the_call_mixed(open_meteo):
    open_meteo(_series(_race_window(30.0), otherwise=5.0))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_MIXED


@pytest.mark.unit
def test_a_low_real_reading_makes_the_call_dry_whatever_the_rest_of_the_day_does(open_meteo):
    # Morning storms, a dry race window: the call is about the race.
    open_meteo(_series({**_race_window(10.0), 12: 95.0, 13: 95.0}, otherwise=5.0))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_DRY


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rain_pct", "impact"),
    [
        (100, module.WEATHER_WET),
        (RAIN_RISK_HIGH, module.WEATHER_WET),
        (RAIN_RISK_HIGH - 1, module.WEATHER_MIXED),
        (RAIN_RISK_MODERATE, module.WEATHER_MIXED),
        (RAIN_RISK_MODERATE - 1, module.WEATHER_DRY),
        (0, module.WEATHER_DRY),
    ],
)
def test_the_cut_offs_are_the_risk_registers(rain_pct, impact):
    assert module.rain_impact(rain_pct) == impact


@pytest.mark.unit
def test_the_stored_copy_from_before_the_race_is_a_forecast_the_call_had(open_meteo):
    open_meteo(_series(R20_RACE_DAY_RAIN, fetched_at=datetime(2026, 11, 7, 14, 5, tzinfo=UTC), stored=True))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_WET


# ---------------------------------------------------------------------------
# No reading: "unknown", never "dry"
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_feed_down_is_unknown_and_openweathermap_is_never_asked(open_meteo, monkeypatch: pytest.MonkeyPatch):
    owm_asked: list[str] = []

    async def current_conditions(location: str) -> dict:
        owm_asked.append(location)
        return {"current": {"rain_probability_pct": 5, "track_temp_c": 29, "wind_speed_kph": 13}}

    monkeypatch.setattr(owm, "get_weather_for_circuit", current_conditions)
    asked = open_meteo(None)

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_UNKNOWN
    assert len(asked) == 1
    assert owm_asked == []


@pytest.mark.unit
def test_a_race_window_with_no_rain_reading_is_unknown(open_meteo):
    open_meteo(_series(_race_window(None), otherwise=None))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY) == module.WEATHER_UNKNOWN


@pytest.mark.unit
def test_a_race_past_the_forecast_horizon_is_unknown_without_a_call(open_meteo):
    asked = open_meteo(_series(R20_RACE_DAY_RAIN))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=datetime(2026, 10, 1, tzinfo=UTC)) == module.WEATHER_UNKNOWN
    assert asked == []


@pytest.mark.unit
def test_an_unknown_venue_is_unknown_without_a_call(open_meteo):
    asked = open_meteo(_series(R20_RACE_DAY_RAIN))
    row = SAO_PAULO_ROW.copy()
    row["Location"] = "Atlantis"
    row["Country"] = "Nowhere"

    assert module.race_weather_impact(row, now=SATURDAY) == module.WEATHER_UNKNOWN
    assert asked == []


@pytest.mark.unit
def test_no_schedule_row_or_no_race_session_is_unknown(open_meteo):
    asked = open_meteo(_series(R20_RACE_DAY_RAIN))
    no_race = SAO_PAULO_ROW.copy()
    no_race["Session5"] = None
    no_race["Session5DateUtc"] = pd.NaT

    assert module.race_weather_impact(None, now=SATURDAY) == module.WEATHER_UNKNOWN
    assert module.race_weather_impact(no_race, now=SATURDAY) == module.WEATHER_UNKNOWN
    assert asked == []


# ---------------------------------------------------------------------------
# Point in time
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "computed_at",
    [RACE_START, RACE_START + timedelta(hours=1), datetime(2026, 11, 11, 9, tzinfo=UTC)],
    ids=["lights-out", "mid-race", "recompute-three-days-later"],
)
def test_a_call_computed_once_the_race_has_started_is_unknown_and_asks_nothing(open_meteo, computed_at):
    # Open-Meteo still answers 88-92 % for those hours, but after the start it is
    # the model's record of the race, not a forecast the call could have had.
    asked = open_meteo(_series(R20_RACE_DAY_RAIN))

    assert module.race_weather_impact(SAO_PAULO_ROW, now=computed_at) == module.WEATHER_UNKNOWN
    assert asked == []


@pytest.mark.unit
def test_a_stored_copy_fetched_after_the_start_is_never_read_as_a_forecast():
    # A payload whose stored series was stamped after lights out (another clock,
    # another process): the call cannot show it had that forecast first.
    payload = {
        "status": "ready",
        "note": None,
        "as_of": "2026-11-08T17:30:00Z",
        "as_of_label": "as of 17:30 UTC",
        "sessions": [
            {
                "name": "Race",
                "phase": "upcoming",
                "forecast": {"rain_probability_pct": 92, "track_temp_c": 24.0, "wind_kph": 14.0},
                "forecast_opens": None,
            }
        ],
    }

    assert module.weather_impact(payload, RACE_START) == module.WEATHER_UNKNOWN
    assert module.weather_impact({**payload, "as_of": "2026-11-08T16:59:00Z"}, RACE_START) == module.WEATHER_WET


@pytest.mark.unit
def test_every_call_logs_what_it_read_or_why_it_could_not(open_meteo, monkeypatch: pytest.MonkeyPatch):
    logged: list[dict] = []
    monkeypatch.setattr(module.logger, "info", lambda event, **fields: logged.append({"event": event, **fields}))
    open_meteo(_series(R20_RACE_DAY_RAIN))

    module.race_weather_impact(SAO_PAULO_ROW, now=SATURDAY)
    module.race_weather_impact(SAO_PAULO_ROW, now=RACE_START)

    assert logged == [
        {
            "event": "predictions.weather_impact",
            "impact": "wet",
            "rain_pct": 92,
            "source": "Race-day forecast (Open-Meteo)",
        },
        {
            "event": "predictions.weather_impact",
            "impact": "unknown",
            "reason": "computed after the race started; its forecast is no longer a forecast",
        },
    ]
