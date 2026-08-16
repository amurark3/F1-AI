"""Tests for app.services.race_control.weather — the live forecast card.

This block is the fix for the worst item in the hardcoded-data audit: the
command center used to hardcode the weather to null, which pushed the frontend
onto an invented lookup table ("RAIN RISK ~20%") that was presented as real.

So the property under test is honesty, in both directions: when the
OpenWeatherMap feed answers, the card must carry *its* numbers and say so; when
there is no location, no key, or a failed call, the card must carry nulls and a
label that names the outage — never a plausible-looking number.
"""

from __future__ import annotations

import pytest

from app.services.race_control import weather as module

_LIVE_CURRENT = {
    "rain_probability_pct": 35,
    "track_temp_c": 41.5,
    "wind_speed_kph": 12.0,
    "humidity_pct": 60,
}


def _patch_feed(monkeypatch: pytest.MonkeyPatch, result) -> list[str]:
    """Replace the async OpenWeatherMap client; returns the locations it saw."""
    seen: list[str] = []

    async def _fetch(location: str):
        seen.append(location)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(module, "get_weather_for_circuit", _fetch)
    return seen


# ---------------------------------------------------------------------------
# offline block
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_offline_block_is_all_nulls_with_a_named_outage():
    block = module._offline_weather_block()

    assert block == {
        "rain_risk": None,
        "track_temp_c": None,
        "wind_kph": None,
        "confidence": module.WEATHER_FEED_OFFLINE,
    }
    assert block["confidence"] != module.WEATHER_FEED_LIVE, "offline must be distinguishable from live"


@pytest.mark.unit
@pytest.mark.parametrize(
    "race", [None, {}, {"location": None}, {"location": ""}], ids=["no-race", "no-location", "null", "blank"]
)
def test_weather_block_is_offline_without_a_circuit_location(race, monkeypatch):
    """No location means no query — the feed must not be called with an empty string."""
    seen = _patch_feed(monkeypatch, {"current": _LIVE_CURRENT})

    assert module.build_weather_block(race) == module._offline_weather_block()
    assert seen == []


# ---------------------------------------------------------------------------
# live feed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_weather_block_carries_the_live_reading_and_labels_its_source(monkeypatch):
    seen = _patch_feed(monkeypatch, {"current": _LIVE_CURRENT})

    block = module.build_weather_block({"location": "Monte-Carlo, Monaco"})

    assert block == {
        "rain_risk": 35,
        "track_temp_c": 41.5,
        "wind_kph": 12.0,
        "confidence": module.WEATHER_FEED_LIVE,
    }
    assert seen == ["Monte-Carlo, Monaco"]


@pytest.mark.unit
def test_weather_block_keeps_missing_live_fields_null_instead_of_defaulting_them(monkeypatch):
    """A partial forecast must show gaps, not zeros a strategist would read as dry."""
    _patch_feed(monkeypatch, {"current": {"track_temp_c": 30}})

    block = module.build_weather_block({"location": "Sakhir, Bahrain"})

    assert block == {
        "rain_risk": None,
        "track_temp_c": 30,
        "wind_kph": None,
        "confidence": module.WEATHER_FEED_LIVE,
    }


# ---------------------------------------------------------------------------
# degradation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_weather_block_falls_back_to_offline_when_the_forecast_call_raises(monkeypatch, capsys):
    _patch_feed(monkeypatch, ConnectionError("openweathermap unreachable"))

    block = module.build_weather_block({"location": "Monza, Italy"})

    assert block == module._offline_weather_block()
    assert "race_control.weather.failed" in capsys.readouterr().out
    # The upstream error text stays in the log, not on the strategist's screen.
    assert "openweathermap unreachable" not in block["confidence"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"error": "OpenWeatherMap API key not configured."},
        {"current": None},
        {},
        {"current": {}, "error": None},
        {"current": _LIVE_CURRENT, "error": "stale cache"},
    ],
    ids=["no-api-key", "null-current", "empty-payload", "empty-current", "errored-but-populated"],
)
def test_weather_block_is_offline_for_any_payload_the_feed_flags(payload, monkeypatch, capsys):
    """An ``error`` key wins even when a ``current`` block is present."""
    _patch_feed(monkeypatch, payload)

    assert module.build_weather_block({"location": "Sakhir, Bahrain"}) == module._offline_weather_block()
    assert "race_control.weather.offline" in capsys.readouterr().out
