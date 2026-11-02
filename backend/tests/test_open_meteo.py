"""Tests for app.data.open_meteo: the hourly series behind per-session weather.

Two properties matter. A gap in the feed must stay a gap — a missing rain
probability read as 0 % is a dry call nobody made. And the request must never
ask for days Open-Meteo refuses to serve, which it answers with a 400 rather
than a partial series.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from app.data import open_meteo as module
from app.data.open_meteo import HourlyReading, fetch_hourly, forecast_window, parse_hourly

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 1)

PAYLOAD = {
    "hourly": {
        "time": ["2026-11-08T17:00", "2026-11-08T18:00", "not-a-time", 7],
        "temperature_2m": [24.5, 23.0, 1.0, 1.0],
        "relative_humidity_2m": [60, None, 1, 1],
        "precipitation_probability": [35, 70],
        "precipitation": [0.0, 1.2, 0, 0],
        "weather_code": [3, 61, 0, 0],
        "cloud_cover": [80, 100, 0, 0],
        "wind_speed_10m": [12.4, "fast", 0, 0],
        "wind_direction_10m": [270, 290, 0, 0],
        "is_day": [1, 0, 1, 1],
    }
}


def test_hours_are_read_in_utc_and_gaps_stay_none():
    readings = parse_hourly(PAYLOAD)

    assert readings == (
        HourlyReading(
            time=datetime(2026, 11, 8, 17, tzinfo=UTC),
            temperature_c=24.5,
            humidity_pct=60.0,
            rain_probability_pct=35.0,
            precipitation_mm=0.0,
            weather_code=3,
            cloud_cover_pct=80.0,
            wind_kph=12.4,
            wind_direction_deg=270.0,
            is_day=True,
        ),
        HourlyReading(
            time=datetime(2026, 11, 8, 18, tzinfo=UTC),
            temperature_c=23.0,
            humidity_pct=None,
            rain_probability_pct=70.0,
            precipitation_mm=1.2,
            weather_code=61,
            cloud_cover_pct=100.0,
            wind_kph=None,
            wind_direction_deg=290.0,
            is_day=False,
        ),
    )


def test_a_boolean_is_not_mistaken_for_a_reading():
    readings = parse_hourly({"hourly": {"time": ["2026-11-08T17:00"], "temperature_2m": [True], "is_day": [None]}})

    assert readings[0].temperature_c is None
    assert readings[0].is_day is None
    assert readings[0].weather_code is None


@pytest.mark.parametrize(
    "payload",
    [None, [], {"hourly": None}, {"hourly": {"time": "x"}}, {"hourly": {"time": []}}],
    ids=["null", "list", "no-hourly", "times-not-list", "no-hours"],
)
def test_an_unusable_payload_has_no_hours(payload):
    assert parse_hourly(payload) == ()


# -- forecast window -------------------------------------------------------------


def test_a_weekend_inside_the_horizon_is_requested_whole():
    assert forecast_window(date(2026, 11, 6), date(2026, 11, 8), TODAY) == (date(2026, 11, 6), date(2026, 11, 8))


def test_a_weekend_straddling_the_horizon_is_cut_at_its_edge():
    assert forecast_window(date(2026, 11, 14), date(2026, 11, 18), TODAY) == (date(2026, 11, 14), date(2026, 11, 16))


def test_a_weekend_straddling_the_archive_edge_is_cut_at_its_edge():
    assert forecast_window(date(2026, 7, 30), date(2026, 8, 2), TODAY) == (date(2026, 8, 1), date(2026, 8, 2))


@pytest.mark.parametrize(
    ("first", "last"),
    [(date(2026, 11, 20), date(2026, 11, 22)), (date(2026, 3, 6), date(2026, 3, 8))],
    ids=["beyond-horizon", "beyond-archive"],
)
def test_a_weekend_entirely_out_of_range_is_not_requested(first, last):
    assert forecast_window(first, last, TODAY) is None


# -- fetch -----------------------------------------------------------------------


@pytest.fixture
def open_meteo(monkeypatch):
    monkeypatch.setattr(module, "_cache", {})
    calls: list[httpx.Request] = []

    def install(handler):
        def recorded(request):
            calls.append(request)
            return handler(request)

        monkeypatch.setattr(module, "new_client", lambda: httpx.Client(transport=httpx.MockTransport(recorded)))
        return calls

    return install


WEEKEND = (date(2026, 11, 6), date(2026, 11, 8))


def test_the_series_is_requested_in_utc_for_the_weekend_and_kept(open_meteo):
    calls = open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))

    first = fetch_hourly(-23.7036, -46.6997, *WEEKEND)

    assert first == parse_hourly(PAYLOAD)
    assert fetch_hourly(-23.7036, -46.6997, *WEEKEND) == first
    assert len(calls) == 1
    params = calls[0].url.params
    assert str(calls[0].url).startswith(module.OPEN_METEO_FORECAST_URL)
    assert params["timezone"] == "GMT"
    assert params["wind_speed_unit"] == "kmh"
    assert (params["start_date"], params["end_date"]) == ("2026-11-06", "2026-11-08")
    assert params["hourly"] == ",".join(module.HOURLY_VARIABLES)


def test_an_expired_series_is_fetched_again_and_old_entries_pruned(open_meteo, monkeypatch):
    calls = open_meteo(lambda request: httpx.Response(200, json=PAYLOAD))
    clock = iter([1000.0, 1000.0 + module.WEATHER_CACHE_TTL + 1])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))

    fetch_hourly(1.0, 2.0, *WEEKEND)
    fetch_hourly(1.0, 2.0, *WEEKEND)

    assert len(calls) == 2
    assert len(module._cache) == 1


@pytest.mark.parametrize(
    "respond",
    [
        lambda: httpx.Response(400, json={"error": True, "reason": "out of allowed range"}),
        lambda: httpx.Response(200, content=b"<html>"),
        lambda: httpx.Response(200, json={"hourly": {"time": []}}),
    ],
    ids=["refused", "not-json", "empty"],
)
def test_a_failed_or_empty_answer_is_none_and_not_kept(open_meteo, respond, capsys):
    calls = open_meteo(lambda request: respond())

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert len(calls) == 2
    assert "open_meteo." in capsys.readouterr().out


def test_a_transport_failure_is_none(open_meteo, capsys):
    def boom(request):
        raise httpx.ConnectError("down", request=request)

    open_meteo(boom)

    assert fetch_hourly(1.0, 2.0, *WEEKEND) is None
    assert "open_meteo.fetch_failed" in capsys.readouterr().out


def test_the_default_client_has_a_timeout():
    with module.new_client() as client:
        assert client.timeout.read == module.REQUEST_TIMEOUT_SECONDS
