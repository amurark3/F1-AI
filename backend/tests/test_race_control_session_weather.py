"""Tests for app.services.race_control.session_weather: weather per session.

Each session is read off the hours it actually runs through, so a race that
starts dry and turns wet in its second hour reads as wet. Past the forecast
horizon a session says when its forecast opens rather than showing a number,
and an outage leaves every session blank rather than plausibly dry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.data.open_meteo import HourlyReading
from app.services.race_control import session_weather as module
from app.services.race_control.session_weather import (
    build_session_weather,
    describe_code,
    race_day_block,
    session_slots,
    summarise_window,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)

RACE = {
    "location": "São Paulo, Brazil",
    "sessions": {
        "Practice 1": "2026-11-06T14:30:00Z",
        "Sprint Qualifying": "2026-11-06T18:30:00Z",
        "Sprint": "2026-11-07T14:00:00Z",
        "Qualifying": "2026-11-07T18:00:00Z",
        "Race": "2026-11-08T17:00:00Z",
    },
}


def hour(stamp: str, **readings) -> HourlyReading:
    values = {
        "temperature_c": 20.0,
        "humidity_pct": 50.0,
        "rain_probability_pct": 10.0,
        "precipitation_mm": 0.0,
        "weather_code": 1,
        "cloud_cover_pct": 0.0,
        "wind_kph": 10.0,
        "wind_direction_deg": 90.0,
        "is_day": True,
    }
    return HourlyReading(time=datetime.fromisoformat(stamp).replace(tzinfo=UTC), **{**values, **readings})


def weekend_series() -> tuple[HourlyReading, ...]:
    start = datetime(2026, 11, 6, tzinfo=UTC)
    return tuple(hour((start + timedelta(hours=offset)).isoformat()[:16]) for offset in range(72))


@pytest.fixture
def feed(monkeypatch):
    calls: list[tuple] = []

    def install(result):
        def fetch(*args):
            calls.append(args)
            return result

        monkeypatch.setattr(module, "fetch_hourly", fetch)
        return calls

    return install


# -- conditions ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, ("clear", "Clear sky")),
        (2, ("partly_cloudy", "Partly cloudy")),
        (3, ("cloudy", "Overcast")),
        (45, ("fog", "Fog")),
        (53, ("drizzle", "Drizzle")),
        (63, ("rain", "Rain")),
        (81, ("rain", "Heavy showers")),
        (73, ("snow", "Snow")),
        (95, ("storm", "Thunderstorm")),
        (42, ("unknown", "Unclassified")),
        (None, ("unknown", "Unclassified")),
    ],
)
def test_wmo_codes_map_to_a_condition_and_label(code, expected):
    assert describe_code(code) == expected


# -- one session window ----------------------------------------------------------

RACE_START = datetime(2026, 11, 8, 17, tzinfo=UTC)
RACE_END = RACE_START + timedelta(hours=2)


def test_a_session_reads_its_worst_hour_for_rain_and_its_average_for_temperature():
    readings = (
        hour("2026-11-08T16:00", rain_probability_pct=90.0, weather_code=95),
        hour("2026-11-08T17:00", temperature_c=24.0, rain_probability_pct=20.0, cloud_cover_pct=40.0),
        hour(
            "2026-11-08T18:00",
            temperature_c=22.0,
            rain_probability_pct=65.0,
            precipitation_mm=1.25,
            weather_code=61,
            wind_kph=18.4,
            wind_direction_deg=200.0,
            humidity_pct=71.0,
            cloud_cover_pct=100.0,
        ),
        hour("2026-11-08T19:00", rain_probability_pct=99.0, weather_code=99),
    )

    assert summarise_window(readings, RACE_START, RACE_END) == {
        "condition": "rain",
        "label": "Light rain",
        "is_day": True,
        "air_temp_c": 23.0,
        "track_temp_c": 32.5,
        "rain_probability_pct": 65,
        "precipitation_mm": 1.2,
        "wind_kph": 18.4,
        "wind_direction_deg": 90,
        "humidity_pct": 60,
        "cloud_cover_pct": 70,
    }


def test_a_session_starting_mid_hour_includes_the_hour_it_starts_in():
    readings = (hour("2026-11-06T14:00", rain_probability_pct=40.0), hour("2026-11-06T15:00"))
    start = datetime(2026, 11, 6, 14, 30, tzinfo=UTC)

    window = summarise_window(readings, start, start + timedelta(hours=1))

    assert window is not None
    assert window["rain_probability_pct"] == 40


def test_a_night_session_gets_no_sun_heating_on_its_track_estimate():
    readings = (hour("2026-11-21T04:00", temperature_c=15.0, cloud_cover_pct=0.0, is_day=False),)
    start = datetime(2026, 11, 21, 4, tzinfo=UTC)

    window = summarise_window(readings, start, start + timedelta(hours=1))

    assert window is not None
    assert window["is_day"] is False
    assert window["track_temp_c"] == 20.0


def test_blank_readings_stay_blank_instead_of_reading_as_dry():
    blank = {
        "temperature_c": None,
        "humidity_pct": None,
        "rain_probability_pct": None,
        "precipitation_mm": None,
        "weather_code": None,
        "cloud_cover_pct": None,
        "wind_kph": None,
        "wind_direction_deg": None,
        "is_day": None,
    }
    window = summarise_window((hour("2026-11-08T17:00", **blank),), RACE_START, RACE_END)

    assert window == {
        "condition": "unknown",
        "label": "Unclassified",
        "is_day": None,
        "air_temp_c": None,
        "track_temp_c": None,
        "rain_probability_pct": None,
        "precipitation_mm": None,
        "wind_kph": None,
        "wind_direction_deg": None,
        "humidity_pct": None,
        "cloud_cover_pct": None,
    }


def test_a_window_with_no_hours_has_no_forecast():
    assert summarise_window((hour("2026-11-06T10:00"),), RACE_START, RACE_END) is None


# -- slots -----------------------------------------------------------------------


def test_slots_run_in_start_order_with_each_sessions_length_and_skip_bad_times():
    race = {"sessions": {"Race": "2026-11-08T17:00:00Z", "Sprint Qualifying": "2026-11-06T18:30", "Bad": "soon"}}

    slots = session_slots(race)

    assert [(slot.name, slot.start.isoformat(), slot.end.isoformat()) for slot in slots] == [
        ("Sprint Qualifying", "2026-11-06T18:30:00+00:00", "2026-11-06T19:15:00+00:00"),
        ("Race", "2026-11-08T17:00:00+00:00", "2026-11-08T19:00:00+00:00"),
    ]


@pytest.mark.parametrize("race", [None, {}, {"sessions": None}, {"sessions": {"Race": 5}}])
def test_no_usable_schedule_has_no_slots(race):
    assert session_slots(race) == ()


# -- the weekend -----------------------------------------------------------------


def test_every_session_gets_its_forecast_from_one_weekend_request(feed):
    calls = feed(weekend_series())

    payload = build_session_weather(RACE, now=NOW)

    assert payload["status"] == "ready"
    assert payload["note"] is None
    assert payload["source"] == module.SESSION_WEATHER_SOURCE
    assert payload["attribution"] == module.OPEN_METEO_ATTRIBUTION
    assert [row["name"] for row in payload["sessions"]] == list(RACE["sessions"])
    assert all(row["forecast"] is not None and row["phase"] == "upcoming" for row in payload["sessions"])
    assert all(row["forecast_opens"] is None for row in payload["sessions"])
    assert payload["sessions"][-1]["starts_at"] == "2026-11-08T17:00:00Z"
    assert payload["sessions"][-1]["ends_at"] == "2026-11-08T19:00:00Z"
    assert calls == [(-23.7036, -46.6997, date(2026, 11, 6), date(2026, 11, 8))]


def test_sessions_are_marked_done_live_or_upcoming_against_the_clock(feed):
    feed(weekend_series())

    payload = build_session_weather(RACE, now=datetime(2026, 11, 7, 14, 20, tzinfo=UTC))

    assert [row["phase"] for row in payload["sessions"]] == ["done", "done", "live", "upcoming", "upcoming"]


def test_a_weekend_beyond_the_horizon_says_when_each_forecast_opens_without_asking(feed):
    calls = feed(weekend_series())

    payload = build_session_weather(RACE, now=datetime(2026, 10, 1, tzinfo=UTC))

    assert payload["status"] == "pending"
    assert payload["note"] == module.NOTE_PENDING
    assert [row["forecast_opens"] for row in payload["sessions"]][::4] == ["2026-10-22", "2026-10-24"]
    assert all(row["forecast"] is None for row in payload["sessions"])
    assert calls == []


def test_a_weekend_straddling_the_horizon_forecasts_what_it_can(feed):
    calls = feed(weekend_series())

    payload = build_session_weather(RACE, now=datetime(2026, 10, 23, tzinfo=UTC))

    assert payload["status"] == "ready"
    assert [row["forecast"] is not None for row in payload["sessions"]] == [True, True, True, True, False]
    assert payload["sessions"][-1]["forecast_opens"] == "2026-10-24"
    assert calls[0][2:] == (date(2026, 11, 6), date(2026, 11, 7))


def test_a_weekend_older_than_the_archive_is_unavailable_without_asking(feed):
    calls = feed(weekend_series())

    payload = build_session_weather(RACE, now=datetime(2027, 6, 1, tzinfo=UTC))

    assert (payload["status"], payload["note"]) == ("unavailable", module.NOTE_ARCHIVED)
    assert [row["phase"] for row in payload["sessions"]] == ["done"] * 5
    assert calls == []


def test_an_unknown_venue_lists_the_sessions_blank_without_asking(feed):
    calls = feed(weekend_series())

    payload = build_session_weather({**RACE, "location": "Atlantis, Nowhere"}, now=NOW)

    assert (payload["status"], payload["note"]) == ("unavailable", module.NOTE_NO_VENUE)
    assert len(payload["sessions"]) == 5
    assert all(row["forecast"] is None for row in payload["sessions"])
    assert calls == []


def test_a_feed_outage_lists_the_sessions_blank(feed):
    feed(None)

    payload = build_session_weather(RACE, now=NOW)

    assert (payload["status"], payload["note"]) == ("unavailable", module.NOTE_OFFLINE)
    assert all(row["forecast"] is None for row in payload["sessions"])


def test_a_series_that_misses_every_session_is_an_outage_not_a_forecast(feed):
    feed((hour("2026-11-06T00:00"),))

    payload = build_session_weather(RACE, now=NOW)

    assert (payload["status"], payload["note"]) == ("unavailable", module.NOTE_OFFLINE)


@pytest.mark.parametrize("race", [None, {"location": "São Paulo, Brazil", "sessions": {}}])
def test_no_schedule_has_no_sessions(feed, race):
    calls = feed(weekend_series())

    payload = build_session_weather(race, now=NOW)

    assert (payload["status"], payload["note"], payload["sessions"]) == ("unavailable", module.NOTE_NO_SCHEDULE, [])
    assert calls == []


def test_the_clock_defaults_to_now(feed):
    feed(weekend_series())

    assert build_session_weather({**RACE, "location": "Atlantis, Nowhere"})["status"] == "unavailable"


# -- race-day summary ------------------------------------------------------------


def test_the_race_session_feeds_the_summary_card(feed):
    feed(weekend_series())

    block = race_day_block(build_session_weather(RACE, now=NOW))

    assert block == {
        "rain_risk": 10,
        "track_temp_c": 40.0,
        "wind_kph": 10.0,
        "confidence": module.RACE_DAY_FORECAST,
    }


def test_a_race_already_run_is_labelled_a_model_reading_not_a_forecast(feed):
    feed(weekend_series())

    block = race_day_block(build_session_weather(RACE, now=datetime(2026, 11, 9, tzinfo=UTC)))

    assert block is not None
    assert block["confidence"] == module.RACE_DAY_RECORD


@pytest.mark.parametrize(
    "payload",
    [
        {"sessions": []},
        {"sessions": [{"name": "Race", "phase": "upcoming", "forecast": None}]},
        {"sessions": [{"name": "Race", "phase": "upcoming", "forecast": {"rain_probability_pct": None}}]},
    ],
    ids=["no-race", "no-forecast", "no-rain-reading"],
)
def test_no_race_reading_means_no_summary(payload):
    assert race_day_block(payload) is None
