"""Tests for the segmented Race Control overview.

The command centre used to arrive in one response, so the page waited on a
cold FastF1 telemetry load before it could show the race name. It is now built
from four segments the UI fetches in parallel.

The behaviour under test: the shell answers without touching telemetry or the
race model, each remaining segment carries its own slice, the strategy segment
reads a stored prediction rather than computing one, and the composite payload
still contains everything the segments do.
"""

import pytest

from app.services import race_control as rc

pytestmark = pytest.mark.unit

YEAR = 2026

RACE = {
    "round": 15,
    "name": "Dutch Grand Prix",
    "location": "Zandvoort, Netherlands",
    "country": "Netherlands",
    "status": "upcoming",
    "date": "2026-08-23",
    "sessions": {"Race": "2026-08-23T13:00:00+00:00"},
    "is_sprint": False,
    "days_until": 2,
    "circuit": {"circuit_name": "Circuit Zandvoort", "laps": 72, "circuit_type": "Permanent"},
    "race_session": "2026-08-23T13:00:00+00:00",
}

DRIVERS = [{"position": 1, "code": "NOR", "driver": "Lando Norris", "team": "McLaren", "points": 300, "wins": 7}]
CONSTRUCTORS = [
    {"position": 1, "team": "McLaren", "points": 500, "wins": 9},
    {"position": 2, "team": "Ferrari", "points": 460, "wins": 3},
]

PREDICTIONS = {
    "predictions": [
        {"driver_code": "NOR", "driver_name": "Lando Norris", "team": "McLaren", "confidence_low": 60, "confidence_high": 80},
        {"driver_code": "PIA", "driver_name": "Oscar Piastri", "team": "McLaren", "confidence_low": 50, "confidence_high": 70},
        {"driver_code": "LEC", "driver_name": "Charles Leclerc", "team": "Ferrari", "confidence_low": 40, "confidence_high": 60},
        {"driver_code": "VER", "driver_name": "Max Verstappen", "team": "Red Bull", "confidence_low": 30, "confidence_high": 50},
    ],
    "data_sources": ["trained_ml_model"],
}

REFERENCE = {
    "source_year": 2025,
    "sample_size": 20,
    "median_first_stop": 27,
    "first_stop_p25": 24,
    "first_stop_p75": 31,
    "most_common_stops": 1,
    "opening_compound": "Medium",
    "finishing_compound": "Hard",
    "pit_loss_seconds": 21.4,
}

WEATHER = {"rain_risk": 5, "track_temp_c": 35.8, "wind_kph": 30.6, "confidence": rc.WEATHER_FEED_LIVE}


class Calls:
    """Records which of the expensive inputs a segment actually reached for."""

    def __init__(self) -> None:
        self.computed_predictions = 0
        self.read_predictions = 0
        self.telemetry = 0
        self.weather = 0


@pytest.fixture
def calls(monkeypatch):
    recorder = Calls()

    def compute(year, round_num):
        recorder.computed_predictions += 1
        return PREDICTIONS

    def read(year, round_num):
        recorder.read_predictions += 1
        return PREDICTIONS

    def reference(location, year):
        recorder.telemetry += 1
        return REFERENCE

    def weather(race):
        recorder.weather += 1
        return WEATHER

    monkeypatch.setattr(rc, "season_events", lambda year: [RACE])
    monkeypatch.setattr(rc, "get_standings_snapshot", lambda year: (DRIVERS, CONSTRUCTORS))
    monkeypatch.setattr(rc, "get_or_compute_race_prediction", compute)
    monkeypatch.setattr(rc, "get_cached_race_prediction", read)
    monkeypatch.setattr(rc, "circuit_strategy_reference", reference)
    monkeypatch.setattr(rc, "build_weather_block", weather)
    return recorder


# -- shell ------------------------------------------------------------------

def test_shell_answers_without_telemetry_or_the_race_model(calls):
    shell = rc.build_overview_shell(YEAR)

    assert shell["race"]["name"] == "Dutch Grand Prix"
    assert shell["season"]["total_events"] == 1
    assert shell["championship"]["constructors"] == CONSTRUCTORS
    assert shell["live_status"]["connected"] is False
    # The whole point of the split: none of the slow inputs are touched.
    assert (calls.computed_predictions, calls.read_predictions, calls.telemetry, calls.weather) == (0, 0, 0, 0)


# -- weather ----------------------------------------------------------------

def test_weather_segment_carries_the_forecast_and_its_risk_register(calls):
    segment = rc.build_overview_weather(YEAR)

    assert segment["year"] == YEAR
    assert segment["weather"] == WEATHER
    assert [risk["title"] for risk in segment["risk_register"]] == [
        "Dry conditions expected",
        "Rival offset plans",
    ]


def test_weather_segment_grades_rival_risk_without_building_strategy_context(calls):
    rc.build_overview_weather(YEAR)

    assert calls.telemetry == 0
    assert calls.computed_predictions == 0


# -- predictions ------------------------------------------------------------

def test_predictions_segment_returns_the_projected_podium(calls):
    segment = rc.build_overview_predictions(YEAR)

    assert [row["driver_code"] for row in segment["predicted_podium"]] == ["NOR", "PIA", "LEC"]
    assert calls.computed_predictions == 1


def test_predictions_segment_survives_a_model_failure(calls, monkeypatch):
    def boom(year, round_num):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(rc, "get_or_compute_race_prediction", boom)

    assert rc.build_overview_predictions(YEAR)["predicted_podium"] == []


# -- strategy ---------------------------------------------------------------

def test_strategy_segment_reads_the_stored_prediction_rather_than_computing_one(calls):
    """Computing here would queue this segment behind a model run it barely uses."""
    segment = rc.build_overview_strategy(YEAR)

    assert calls.read_predictions == 1
    assert calls.computed_predictions == 0
    assert segment["strategy_context"]["data_source"] == {
        "mode": "telemetry",
        "edition_year": 2025,
        "sample_size": 20,
    }


def test_strategy_segment_carries_the_workstream_board(calls):
    segment = rc.build_overview_strategy(YEAR)

    assert [stream["id"] for stream in segment["workstreams"]] == [
        "weekend-brief",
        "race-model",
        "rival-watch",
        "live-control",
    ]


def test_strategy_segment_falls_back_to_heuristics_when_telemetry_fails(calls, monkeypatch):
    def boom(location, year):
        raise RuntimeError("session load failed")

    monkeypatch.setattr(rc, "circuit_strategy_reference", boom)

    context = rc.build_overview_strategy(YEAR)["strategy_context"]
    assert context["data_source"]["mode"] == "heuristic"


# -- composite --------------------------------------------------------------

def test_composite_still_carries_every_segment(calls):
    overview = rc.build_overview(YEAR)

    shell = rc.build_overview_shell(YEAR)
    weather = rc.build_overview_weather(YEAR)
    predictions = rc.build_overview_predictions(YEAR)
    strategy = rc.build_overview_strategy(YEAR)

    assert overview["race"] == shell["race"]
    assert overview["championship"] == shell["championship"]
    assert overview["live_status"] == shell["live_status"]
    assert overview["weather"] == weather["weather"]
    assert overview["risk_register"] == weather["risk_register"]
    assert overview["predicted_podium"] == predictions["predicted_podium"]
    assert overview["strategy_context"] == strategy["strategy_context"]
    assert overview["workstreams"] == strategy["workstreams"]


def test_a_season_with_no_events_still_produces_every_segment(calls, monkeypatch):
    monkeypatch.setattr(rc, "season_events", lambda year: [])

    assert rc.build_overview_shell(YEAR)["race"] is None
    assert rc.build_overview_predictions(YEAR)["predicted_podium"] == []
    assert rc.build_overview_weather(YEAR)["risk_register"] == []
    assert rc.build_overview_strategy(YEAR)["strategy_context"]["phase"] == "Pre-race build"
