"""Tests for app.api.tools.external — the two tools that leave the building.

Both reach a third party, so both are one outage away from breaking a chat turn.
The behaviours pinned here are the ones that keep an outage from becoming a
wrong answer:

* **A provider error is returned, not raised.** The agent loop turns an
  exception into a generic failure message; returning the reason lets the model
  say what went wrong or route around it.
* **A missing field renders as unknown.** Every weather field is optional in the
  upstream payload, and a blank cell in the table would read to the model as a
  measured zero.
* **The event-loop dance is exercised both ways.** ``get_weather_conditions`` is
  a sync tool wrapping an async fetch, and picks between ``asyncio.run`` and a
  worker thread depending on whether a loop is already running. The worker-thread
  branch only happens in production, so it is driven here from an async test.
"""

from __future__ import annotations

import pytest

from app.api.tools import external
from app.api.tools.external import get_weather_conditions, perform_web_search


def _weather(**fields) -> dict:
    """A full OpenWeatherMap-derived payload; overrides go in ``fields``."""
    base = {
        "circuit_name": "Circuit de Monaco",
        "current": {
            "conditions": "Light rain",
            "air_temp_c": 18.4,
            "track_temp_c": 24.1,
            "humidity_pct": 78,
            "wind_speed_kph": 12.0,
            "wind_direction": "NNE",
            "rain_probability_pct": 65,
        },
        "hourly_forecast": [
            {
                "time": "14:00",
                "temp_c": 18.0,
                "rain_probability_pct": 70,
                "wind_speed_kph": 13.0,
                "conditions": "Rain",
            }
        ],
        "track_context": "Overtaking is near impossible; track position is everything.",
        "strategy_impact": "Intermediates likely for the opening stint.",
    }
    return {**base, **fields}


def _install_weather(monkeypatch, payload) -> None:
    """Replace the async fetch; ``payload`` may be an exception to raise."""

    async def _fetch(location):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(external, "get_weather_for_circuit", _fetch)


class _FakeTavily:
    """Records the search kwargs so the advertised query shape can be asserted."""

    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _install_tavily(monkeypatch, response) -> _FakeTavily:
    client = _FakeTavily(response)
    # Seeds the memoised singleton so `get_tavily_client()` hands back the fake
    # instead of building a real one. monkeypatch restores it after the test.
    monkeypatch.setattr(external, "_tavily_client", client)
    return client


# ---------------------------------------------------------------------------
# get_weather_conditions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_full_forecast_renders_current_hourly_context_and_strategy(monkeypatch):
    _install_weather(monkeypatch, _weather())

    report = get_weather_conditions.invoke({"location": "Monaco"})

    assert report.startswith("### Weather: Circuit de Monaco (Monaco)")
    assert "- **Air temperature:** 18.4C" in report
    assert "| 14:00 | 18.0C | 70% | 13.0 km/h | Rain |" in report
    assert "**Track context:** Overtaking is near impossible; track position is everything." in report
    assert "**Strategy impact:** Intermediates likely for the opening stint." in report


@pytest.mark.unit
def test_an_upstream_error_is_returned_verbatim_for_the_model_to_relay(monkeypatch):
    _install_weather(monkeypatch, {"error": "OpenWeatherMap API key not configured."})

    assert get_weather_conditions.invoke({"location": "Monaco"}) == "OpenWeatherMap API key not configured."


@pytest.mark.unit
def test_missing_measurements_render_as_unknown_rather_than_blank(monkeypatch):
    """A blank cell would read to the model as a measured value of nothing."""
    _install_weather(monkeypatch, _weather(current={}, hourly_forecast=[], track_context="", strategy_impact=""))

    report = get_weather_conditions.invoke({"location": "Sakhir"})

    assert "- **Conditions:** Unknown" in report
    assert "- **Air temperature:** N/AC" in report
    assert "- **Rain probability:** N/A%" in report


@pytest.mark.unit
def test_optional_sections_are_omitted_when_the_provider_returns_none(monkeypatch):
    _install_weather(monkeypatch, _weather(hourly_forecast=[], track_context="", strategy_impact=""))

    report = get_weather_conditions.invoke({"location": "Sakhir"})

    assert "#### Hourly Forecast" not in report
    assert "**Track context:**" not in report
    assert "**Strategy impact:**" not in report


@pytest.mark.unit
def test_the_location_falls_back_to_the_query_when_the_circuit_is_unnamed(monkeypatch):
    payload = {k: v for k, v in _weather().items() if k != "circuit_name"}
    _install_weather(monkeypatch, payload)

    assert get_weather_conditions.invoke({"location": "Sakhir"}).startswith("### Weather: Sakhir (Sakhir)")


@pytest.mark.unit
def test_a_fetch_failure_becomes_a_message_not_an_exception(monkeypatch):
    """The agent loop would otherwise report a generic tool error to the model."""
    _install_weather(monkeypatch, RuntimeError("openweathermap timed out"))

    assert (
        get_weather_conditions.invoke({"location": "Monaco"}) == "Weather data fetch failed: openweathermap timed out"
    )


@pytest.mark.unit
async def test_the_fetch_is_offloaded_when_an_event_loop_is_already_running(monkeypatch):
    """In production the tool is called from a thread pool; here from the loop itself."""
    _install_weather(monkeypatch, _weather())

    report = get_weather_conditions.invoke({"location": "Monaco"})

    assert report.startswith("### Weather: Circuit de Monaco (Monaco)")


# ---------------------------------------------------------------------------
# perform_web_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_search_results_are_rendered_with_their_source_and_url(monkeypatch):
    _install_tavily(
        monkeypatch,
        {
            "results": [
                {"title": "Hamilton to Ferrari", "content": "Confirmed for 2025.", "url": "https://example.com/a"},
                {"title": "Sainz to Williams", "content": "Multi-year deal.", "url": "https://example.com/b"},
            ]
        },
    )

    answer = perform_web_search.invoke({"query": "f1 driver market"})

    assert answer == (
        "Source: Hamilton to Ferrari\nSnippet: Confirmed for 2025.\nURL: https://example.com/a\n\n"
        "Source: Sainz to Williams\nSnippet: Multi-year deal.\nURL: https://example.com/b"
    )


@pytest.mark.unit
def test_the_search_is_capped_at_three_basic_results(monkeypatch):
    """The cap is what keeps a search from swamping the model's context window."""
    client = _install_tavily(monkeypatch, {"results": []})

    perform_web_search.invoke({"query": "monaco gp result"})

    assert client.calls == [{"query": "monaco gp result", "search_depth": "basic", "max_results": 3}]


@pytest.mark.unit
def test_an_empty_result_set_says_so_instead_of_returning_nothing(monkeypatch):
    """An empty string would read to the model as a tool that returned no answer."""
    _install_tavily(monkeypatch, {"results": []})

    assert perform_web_search.invoke({"query": "who won"}) == "No search results found."


@pytest.mark.unit
def test_a_missing_results_key_is_treated_as_no_results(monkeypatch):
    _install_tavily(monkeypatch, {})

    assert perform_web_search.invoke({"query": "who won"}) == "No search results found."


@pytest.mark.unit
def test_a_provider_failure_is_reported_to_the_model(monkeypatch):
    _install_tavily(monkeypatch, RuntimeError("tavily 503"))

    assert perform_web_search.invoke({"query": "who won"}) == "Search failed: tavily 503"


@pytest.mark.unit
def test_a_malformed_result_row_fails_the_whole_search_rather_than_half_rendering(monkeypatch):
    """Pins current behaviour: one row missing 'url' loses the other rows too."""
    _install_tavily(monkeypatch, {"results": [{"title": "t", "content": "c"}]})

    assert perform_web_search.invoke({"query": "who won"}).startswith("Search failed:")
