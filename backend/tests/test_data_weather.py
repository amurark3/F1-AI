"""Tests for app.data.weather — the OpenWeatherMap boundary and its fallbacks.

Weather drives every wet-race call the product makes: rain probability decides
whether a strategy is "dual dry/wet scenarios" or "standard dry", and track
temperature drives the degradation story. Three things can go wrong and all
three are covered here:

1. **The key is missing.** That is the default in this suite (conftest clears
   ``OPENWEATHERMAP_API_KEY``), and the module must degrade to an explicit
   error rather than invent numbers.
2. **The premium One Call 3.0 endpoint is unavailable.** The module silently
   falls back to the free 2.5 endpoint, which has no ``pop`` field — so the
   rain probability it reports is a *heuristic derived from a weather code*,
   not an observation. The tests below pin what is and is not distinguishable
   between the two paths.
3. **The TTL cache serves stale data.** A cached forecast that outlives the
   session it was fetched for is worse than no forecast.

The HTTP boundary is replaced with a scripted ``httpx.AsyncClient``; the
autouse socket blocker in conftest guarantees no real request escapes.
"""

from __future__ import annotations

import json
import time

import pytest

from app.data import weather

# A stand-in credential. Assertions check this exact value never reaches a
# caller-visible payload — not the word "key", which is a legitimate field name.
_API_KEY = "owm-unit-test-0a1b2c3d"


# ---------------------------------------------------------------------------
# Fixtures and scripted HTTP boundary
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_weather_cache():
    """The TTL cache is a process global — leaking it across tests hides bugs."""
    weather._weather_cache.clear()
    yield
    weather._weather_cache.clear()


@pytest.fixture
def with_api_key(monkeypatch):
    """Give the module a key, since conftest clears the real environment one."""
    monkeypatch.setattr(weather, "OPENWEATHERMAP_API_KEY", _API_KEY)
    return _API_KEY


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self.text = text
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _install_client(monkeypatch, *responses):
    """Swap ``httpx.AsyncClient`` for one that replays ``responses`` in order.

    An ``Exception`` instance in the queue is raised instead of returned, which
    is how transport failures are simulated. Returns the recorded call list.
    """
    calls: list[dict] = []
    queue = list(responses)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, url, params=None, timeout=None):
            calls.append({"url": url, "params": params, "timeout": timeout})
            nxt = queue.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

    monkeypatch.setattr(weather.httpx, "AsyncClient", lambda *_a, **_k: _Client())
    return calls


def _onecall_payload(**overrides) -> dict:
    """A One Call 3.0 body: 22C, light cloud, a wet third hour."""
    payload = {
        "current": {
            "temp": 22.4,
            "humidity": 55,
            "wind_speed": 5.0,
            "wind_deg": 90,
            "clouds": 20,
            "weather": [{"description": "scattered clouds"}],
        },
        "hourly": [
            {"dt": 0, "temp": 22.0, "pop": 0.1, "wind_speed": 5.0, "weather": [{"description": "clear sky"}]},
            {"dt": 3600, "temp": 23.0, "pop": 0.2, "wind_speed": 6.0, "weather": [{"description": "few clouds"}]},
            {"dt": 7200, "temp": 21.0, "pop": 0.55, "wind_speed": 7.0, "weather": [{"description": "light rain"}]},
            {"dt": 10800, "temp": 20.0, "pop": 0.3, "wind_speed": 8.0, "weather": [{"description": "light rain"}]},
            {"dt": 14400, "temp": 19.0, "pop": 0.9, "wind_speed": 9.0, "weather": [{"description": "heavy rain"}]},
        ],
    }
    payload.update(overrides)
    return payload


def _current_payload(**overrides) -> dict:
    """A 2.5 current-weather body: 30C, clear, calm."""
    payload = {
        "main": {"temp": 30.2, "humidity": 40},
        "wind": {"speed": 2.5, "deg": 180},
        "clouds": {"all": 0},
        "weather": [{"id": 800, "description": "clear sky"}],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# _degrees_to_direction
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        (0, "N"),
        (22.5, "NNE"),
        (90, "E"),
        (180, "S"),
        (247.5, "WSW"),
        (270, "W"),
        (350, "N"),  # wraps past the top of the compass rather than indexing off the end
        (360, "N"),
    ],
)
def test_degrees_to_direction_maps_the_compass_rose(degrees, expected):
    assert weather._degrees_to_direction(degrees) == expected


# ---------------------------------------------------------------------------
# _estimate_track_temp
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("clouds", "expected"),
    [
        (0, 40.0),  # full sun: +20C over air temp
        (50, 32.5),
        (100, 25.0),  # overcast: only +5C
    ],
)
def test_estimate_track_temp_scales_with_sun_exposure(clouds, expected):
    assert weather._estimate_track_temp(20.0, clouds) == expected


@pytest.mark.unit
def test_estimate_track_temp_never_cools_the_track_below_air_temp():
    """Cloud cover above 100% (bad feed) must not produce a sub-air-temp track."""
    assert weather._estimate_track_temp(20.0, 250) == 25.0


# ---------------------------------------------------------------------------
# _get_track_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_track_context_flags_street_circuit_drainage():
    context = weather._get_track_context("Monaco")

    assert "Street circuit" in context
    assert "Safety Car" in context


@pytest.mark.unit
def test_track_context_flags_high_altitude_thin_air():
    assert "altitude" in weather._get_track_context("Mexico City")


@pytest.mark.unit
def test_track_context_flags_desert_track_evolution():
    context = weather._get_track_context("Sakhir")

    assert "Desert circuit" in context
    assert "Track evolution" in context


@pytest.mark.unit
def test_track_context_combines_street_and_desert_for_jeddah():
    """Jeddah is street, desert *and* coastal; the coastal note is the low-value
    one and is deliberately suppressed once a sharper context exists."""
    context = weather._get_track_context("Jeddah")

    assert "Street circuit" in context
    assert "Desert circuit" in context
    assert "Coastal" not in context
    assert ". " in context, "multiple contexts are joined into one sentence run"


@pytest.mark.unit
def test_track_context_falls_back_to_coastal_wind_note():
    assert weather._get_track_context("Zandvoort").startswith("Coastal location")


@pytest.mark.unit
@pytest.mark.parametrize("location", ["Silverstone", "Nowhere At All"], ids=["plain-circuit", "unknown-circuit"])
def test_track_context_is_empty_when_nothing_notable_applies(location):
    assert weather._get_track_context(location) == ""


# ---------------------------------------------------------------------------
# _assess_strategy_impact
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pops", "expected_fragment"),
    [
        ([10, 45, 5], "High rain probability"),
        ([10, 25], "Moderate rain risk"),
        ([0, 19], "Low rain probability"),
        ([40], "High rain probability"),  # exactly on the 40% boundary
        ([20], "Moderate rain risk"),  # exactly on the 20% boundary
    ],
)
def test_assess_strategy_impact_uses_the_wettest_hour(pops, expected_fragment):
    forecasts = [{"rain_probability_pct": pop} for pop in pops]

    assert expected_fragment in weather._assess_strategy_impact(forecasts)


@pytest.mark.unit
def test_assess_strategy_impact_reports_missing_data_rather_than_dry():
    """No forecast is not the same as a dry forecast — it must not read as one."""
    assert weather._assess_strategy_impact([]) == "No forecast data available"


@pytest.mark.unit
def test_assess_strategy_impact_treats_a_missing_pop_field_as_dry():
    assert "Low rain" in weather._assess_strategy_impact([{"time": "14:00"}])


# ---------------------------------------------------------------------------
# _fetch_onecall / _fetch_current_weather
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_fetch_onecall_sends_the_key_and_returns_the_body(monkeypatch, with_api_key):
    calls = _install_client(monkeypatch, _FakeResponse(200, {"current": {"temp": 9.0}}))

    async with weather.httpx.AsyncClient() as client:
        result = await weather._fetch_onecall(43.7, 7.4, client)

    assert result == {"current": {"temp": 9.0}}
    assert calls[0]["url"].endswith("/data/3.0/onecall")
    assert calls[0]["params"]["appid"] == with_api_key
    assert calls[0]["params"]["exclude"] == "minutely,daily,alerts"


@pytest.mark.unit
@pytest.mark.parametrize(
    "scripted",
    [_FakeResponse(401, text="Invalid API key"), RuntimeError("connection reset")],
    ids=["http-error", "transport-error"],
)
async def test_fetch_onecall_returns_none_on_any_failure(monkeypatch, scripted):
    _install_client(monkeypatch, scripted)

    async with weather.httpx.AsyncClient() as client:
        assert await weather._fetch_onecall(43.7, 7.4, client) is None


@pytest.mark.unit
async def test_fetch_current_weather_targets_the_free_endpoint(monkeypatch, with_api_key):
    calls = _install_client(monkeypatch, _FakeResponse(200, _current_payload()))

    async with weather.httpx.AsyncClient() as client:
        result = await weather._fetch_current_weather(43.7, 7.4, client)

    assert result["main"]["temp"] == 30.2
    assert calls[0]["url"].endswith("/data/2.5/weather")
    assert calls[0]["params"]["units"] == "metric"


@pytest.mark.unit
@pytest.mark.parametrize(
    "scripted",
    [_FakeResponse(429, text="rate limited"), RuntimeError("connection reset")],
    ids=["http-error", "transport-error"],
)
async def test_fetch_current_weather_returns_none_on_any_failure(monkeypatch, scripted):
    _install_client(monkeypatch, scripted)

    async with weather.httpx.AsyncClient() as client:
        assert await weather._fetch_current_weather(43.7, 7.4, client) is None


# ---------------------------------------------------------------------------
# _build_from_onecall
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_from_onecall_converts_units_and_caps_the_forecast():
    current, hourly = weather._build_from_onecall(_onecall_payload(), "Monaco")

    assert current["air_temp_c"] == 22.4
    assert current["wind_speed_kph"] == 18.0  # 5 m/s -> km/h
    assert current["wind_direction"] == "E"
    assert current["rain_probability_pct"] == 10  # taken from the first hourly pop
    assert current["conditions"] == "Scattered clouds"
    assert len(hourly) == 4, "only the next four hours span a session"
    assert hourly[2]["rain_probability_pct"] == 55
    assert hourly[0]["time"] == "00:00"


@pytest.mark.unit
def test_build_from_onecall_survives_an_empty_body():
    """A 200 with no payload must produce zeros, not a KeyError mid-request."""
    current, hourly = weather._build_from_onecall({}, "Monaco")

    assert current["air_temp_c"] == 0.0
    assert current["rain_probability_pct"] == 0
    assert current["conditions"] == "Unknown"
    assert hourly == []


# ---------------------------------------------------------------------------
# _build_from_current
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("weather_id", "clouds", "expected_pct"),
    [
        (502, 90, 80),  # heavy rain
        (601, 50, 60),  # snow
        (741, 10, 30),  # fog
        (800, 90, 20),  # clear code but near-total cloud
        (800, 10, 5),  # clear
    ],
)
def test_build_from_current_infers_rain_probability_from_the_weather_code(weather_id, clouds, expected_pct):
    """The free endpoint has no ``pop`` — this number is inferred, not observed."""
    payload = _current_payload(weather=[{"id": weather_id, "description": "x"}], clouds={"all": clouds})

    current, hourly = weather._build_from_current(payload, "Monaco")

    assert current["rain_probability_pct"] == expected_pct
    assert hourly == [], "the 2.5 endpoint carries no hourly forecast"


@pytest.mark.unit
def test_build_from_current_converts_wind_and_estimates_track_temp():
    current, _ = weather._build_from_current(_current_payload(), "Sakhir")

    assert current["wind_speed_kph"] == 9.0  # 2.5 m/s
    assert current["wind_direction"] == "S"
    assert current["track_temp_c"] == 50.2  # clear sky over 30.2C air


@pytest.mark.unit
def test_build_from_current_handles_a_missing_weather_block():
    current, _ = weather._build_from_current(_current_payload(weather=[]), "Monaco")

    assert current["conditions"] == "Unknown"
    assert current["rain_probability_pct"] == 5


# ---------------------------------------------------------------------------
# get_weather_for_circuit — no key / unknown circuit
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_weather_without_a_key_errors_instead_of_inventing_conditions():
    """conftest clears the key, so this is the default deployment-misconfig path."""
    result = await weather.get_weather_for_circuit("Monaco")

    assert "OPENWEATHERMAP_API_KEY" in result["error"]
    assert "current" not in result, "a missing key must not yield fabricated conditions"
    assert "hourly_forecast" not in result


@pytest.mark.unit
async def test_get_weather_without_a_key_is_not_cached():
    """Caching the error would keep the failure alive after the key is fixed."""
    await weather.get_weather_for_circuit("Monaco")

    assert weather._weather_cache == {}


@pytest.mark.unit
async def test_get_weather_rejects_an_unknown_circuit_with_the_valid_options(with_api_key):
    result = await weather.get_weather_for_circuit("Nurburgring")

    assert "not found in circuit database" in result["error"]
    assert "Monaco" in result["error"]


@pytest.mark.unit
async def test_get_weather_reads_the_key_from_the_environment_at_import(monkeypatch, reload_module):
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", _API_KEY)
    reload_module("app.config")
    reloaded = reload_module("app.data.weather")

    assert reloaded.OPENWEATHERMAP_API_KEY == _API_KEY


# ---------------------------------------------------------------------------
# get_weather_for_circuit — the One Call path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_weather_builds_a_full_report_from_one_call(monkeypatch, with_api_key):
    calls = _install_client(monkeypatch, _FakeResponse(200, _onecall_payload()))

    result = await weather.get_weather_for_circuit("Monaco")

    assert result["circuit_name"] == "Circuit de Monaco"
    assert result["current"]["air_temp_c"] == 22.4
    assert len(result["hourly_forecast"]) == 4
    assert "Street circuit" in result["track_context"]
    # A 55% hour is over the 40% line, so both dry and wet plans are needed.
    assert "High rain probability" in result["strategy_impact"]
    assert len(calls) == 1, "One Call succeeded, so the 2.5 fallback must not fire"


@pytest.mark.unit
async def test_get_weather_never_returns_the_api_key_to_the_caller(monkeypatch, with_api_key):
    _install_client(monkeypatch, _FakeResponse(200, _onecall_payload()))

    result = await weather.get_weather_for_circuit("Monaco")

    assert with_api_key not in json.dumps(result)


# ---------------------------------------------------------------------------
# get_weather_for_circuit — the 2.5 fallback path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_weather_falls_back_to_the_free_endpoint(monkeypatch, with_api_key):
    calls = _install_client(
        monkeypatch,
        _FakeResponse(401, text="One Call 3.0 requires a subscription"),
        _FakeResponse(200, _current_payload(weather=[{"id": 500, "description": "light rain"}])),
    )

    result = await weather.get_weather_for_circuit("Monaco")

    assert len(calls) == 2
    assert calls[1]["url"].endswith("/data/2.5/weather")
    assert result["current"]["conditions"] == "Light rain"
    # With no hourly data the impact is assessed off the current conditions,
    # whose 80% is itself inferred from the weather code rather than measured.
    assert "High rain probability" in result["strategy_impact"]


@pytest.mark.unit
async def test_get_weather_fallback_is_only_distinguishable_by_an_empty_forecast(monkeypatch, with_api_key):
    """Documents a real gap: the fallback's ``rain_probability_pct`` is a guess
    derived from a weather code, but it is reported in the same field, with the
    same shape, as the One Call ``pop``. The one signal a caller gets that the
    reading is second-hand is that ``hourly_forecast`` is empty.
    """
    _install_client(
        monkeypatch,
        _FakeResponse(500, text="upstream down"),
        _FakeResponse(200, _current_payload()),
    )

    result = await weather.get_weather_for_circuit("Monaco")

    assert result["hourly_forecast"] == []
    assert set(result["current"]) == {
        "air_temp_c",
        "track_temp_c",
        "humidity_pct",
        "wind_speed_kph",
        "wind_direction",
        "rain_probability_pct",
        "conditions",
    }


@pytest.mark.unit
async def test_get_weather_errors_when_both_endpoints_fail(monkeypatch, with_api_key):
    _install_client(
        monkeypatch,
        _FakeResponse(500, text="upstream down"),
        _FakeResponse(500, text="upstream down"),
    )

    result = await weather.get_weather_for_circuit("Monaco")

    assert "Failed to fetch weather data" in result["error"]
    assert result["circuit_name"] == "Circuit de Monaco"
    assert "current" not in result
    assert weather._weather_cache == {}, "a failed fetch must not poison the cache"


# ---------------------------------------------------------------------------
# get_weather_for_circuit — the TTL cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_weather_serves_a_fresh_cache_entry_without_calling_out(monkeypatch, with_api_key):
    calls = _install_client(monkeypatch, _FakeResponse(200, _onecall_payload()))

    first = await weather.get_weather_for_circuit("Monaco")
    second = await weather.get_weather_for_circuit("Monaco")

    assert second is first
    assert len(calls) == 1


@pytest.mark.unit
async def test_get_weather_refetches_once_the_entry_outlives_its_ttl(monkeypatch, with_api_key):
    """A forecast older than the TTL is worse than none — sessions move on."""
    stale = {"location": "Monaco", "current": {"air_temp_c": -99.0}}
    weather._weather_cache["Monaco"] = (time.time() - weather.WEATHER_CACHE_TTL - 1, stale)
    calls = _install_client(monkeypatch, _FakeResponse(200, _onecall_payload()))

    result = await weather.get_weather_for_circuit("Monaco")

    assert result["current"]["air_temp_c"] == 22.4
    assert len(calls) == 1
    assert weather._weather_cache["Monaco"][1] is result


@pytest.mark.unit
async def test_get_weather_caches_each_circuit_separately(monkeypatch, with_api_key):
    _install_client(
        monkeypatch,
        _FakeResponse(200, _onecall_payload()),
        _FakeResponse(200, _onecall_payload()),
    )

    await weather.get_weather_for_circuit("Monaco")
    await weather.get_weather_for_circuit("Sakhir")

    assert set(weather._weather_cache) == {"Monaco", "Sakhir"}
