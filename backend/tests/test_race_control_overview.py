"""Tests for app.services.race_control.overview — the command-center composer.

``build_overview`` is the single payload the Race Control page renders, and it
is assembled from feeds that fail independently: the schedule/standings
dashboard, the cached race prediction, the circuit telemetry reference, the
per-session forecast (which alone feeds the race-day card), and the circuit map. The risk is a partial outage arriving as a confident page:
a dead prediction service or an unraced circuit must degrade the blocks that
depend on it (and say so through ``data_source.mode``, the workstream statuses
and the risk register) without blanking or faking the rest.

The blocks themselves are tested in their own modules; what is pinned here is
the wiring — which feed reaches which block, and what survives when one dies.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data import weather as owm
from app.services.race_control import overview as module, session_weather

_PREDICTIONS = {
    "predictions": [
        {"driver": "VER", "position": 1},
        {"driver": "NOR", "position": 2},
        {"driver": "LEC", "position": 3},
        {"driver": "RUS", "position": 4},
    ]
}

_REFERENCE = {
    "pit_loss_seconds": 20.5,
    "median_first_stop": 21,
    "first_stop_p25": 17,
    "first_stop_p75": 26,
    "opening_compound": "Medium",
    "finishing_compound": "Hard",
    "most_common_stops": 1,
    "source_year": 2025,
    "sample_size": 19,
}


# No session has a forecast, so the summary card has no number, only the forecast's note.
_NO_SESSION_FORECAST = {"status": "pending", "note": "later", "sessions": []}
_NO_FORECAST_CARD = {"rain_risk": None, "track_temp_c": None, "wind_kph": None, "confidence": "later"}


def _race_day(rain: int) -> dict:
    return {
        "status": "ready",
        "note": None,
        "sessions": [
            {
                "name": "Race",
                "phase": "upcoming",
                "forecast": {"rain_probability_pct": rain, "track_temp_c": 31.0, "wind_kph": 14.0},
            }
        ],
    }


_RACE_DAY_FORECAST = _race_day(55)
_CIRCUIT = {"record": {"circuit_id": "monaco"}, "lap_record": None, "map": None}


def _dashboard(**fields) -> dict:
    race = {
        "round": 4,
        "name": "Monaco Grand Prix",
        "location": "Monaco, Monaco",
        "status": "upcoming",
        "days_until": 3,
        "is_sprint": False,
        "circuit": {"laps": 78, "circuit_type": "Street circuit"},
    }
    base = {
        "year": 2026,
        "focus": "Race-week strategy lock",
        "race": race,
        "season": {"total_events": 24, "completed_events": 3, "upcoming_events": 21},
        "championship": {
            "drivers": [{"position": 1, "code": "VER"}],
            "constructors": [
                {"position": 1, "team": "McLaren", "points": 300.0},
                {"position": 2, "team": "Ferrari", "points": 290.0},
            ],
        },
    }
    return {**base, **fields}


def _patch_feeds(monkeypatch: pytest.MonkeyPatch, **feeds) -> None:
    """Stub the boundaries ``build_overview`` composes.

    Each value is returned as-is, or raised when it is an exception — that is
    how the "one feed is down" cases are driven.
    """

    def _serve(value):
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(module, "build_strategy_dashboard", lambda _year: _serve(feeds.get("dashboard", _dashboard())))
    monkeypatch.setattr(module, "get_or_compute_race_prediction", lambda *_a: _serve(feeds.get("predictions")))
    monkeypatch.setattr(module, "circuit_strategy_reference", lambda *_a: _serve(feeds.get("reference")))
    monkeypatch.setattr(
        module, "build_session_weather", lambda _race: _serve(feeds.get("sessions", _NO_SESSION_FORECAST))
    )
    monkeypatch.setattr(module, "build_circuit_segment", lambda _year, _race: _serve(feeds.get("circuit", _CIRCUIT)))


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overview_keeps_every_dashboard_key_and_adds_the_command_center_blocks(monkeypatch):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=_REFERENCE)

    payload = module.build_overview(2026)

    assert payload["year"] == 2026
    assert payload["focus"] == "Race-week strategy lock"
    assert payload["season"]["total_events"] == 24
    assert set(payload) >= {
        "predicted_podium",
        "strategy_context",
        "weather",
        "session_weather",
        "circuit",
        "risk_register",
        "workstreams",
        "live_status",
    }
    assert payload["circuit"] == _CIRCUIT


@pytest.mark.unit
def test_overview_publishes_only_the_top_three_of_the_predicted_order(monkeypatch):
    """The panel is a podium — a fourth row would read as a predicted P4."""
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS)

    assert [row["driver"] for row in module.build_overview(2026)["predicted_podium"]] == ["VER", "NOR", "LEC"]


@pytest.mark.unit
def test_overview_feeds_the_telemetry_reference_into_the_strategy_context(monkeypatch):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=_REFERENCE)

    context = module.build_overview(2026)["strategy_context"]

    assert context["data_source"] == {"mode": "telemetry", "edition_year": 2025, "sample_size": 19}
    assert context["pit_model"]["pit_loss_seconds"] == 20.5
    # Constructors reach the competitor table through the dashboard block.
    assert [row["team"] for row in context["competitors"]] == ["McLaren", "Ferrari"]


@pytest.mark.unit
def test_overview_derives_the_risk_register_from_the_race_day_forecast(monkeypatch):
    _patch_feeds(monkeypatch, sessions=_race_day(70))

    payload = module.build_overview(2026)

    assert payload["weather"]["rain_risk"] == 70
    assert payload["weather"]["confidence"] == session_weather.RACE_DAY_FORECAST
    register = {card["title"]: card for card in payload["risk_register"]}
    assert register["Elevated rain risk"]["level"] == "High"
    # A 10-point constructor gap is the closest-rival input, not a fixed card.
    assert "Ferrari" in register["Rival offset plans"]["detail"]


@pytest.mark.unit
def test_the_race_day_forecast_feeds_the_summary_card(monkeypatch):
    _patch_feeds(monkeypatch, sessions=_RACE_DAY_FORECAST)

    payload = module.build_overview(2026)

    assert payload["weather"] == {
        "rain_risk": 55,
        "track_temp_c": 31.0,
        "wind_kph": 14.0,
        "confidence": session_weather.RACE_DAY_FORECAST,
    }
    assert payload["session_weather"] == _RACE_DAY_FORECAST
    register = {card["title"]: card for card in payload["risk_register"]}
    assert "55%" in register["Elevated rain risk"]["detail"]


@pytest.mark.unit
def test_overview_workstreams_report_the_model_as_telemetry_backed(monkeypatch):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=_REFERENCE)

    statuses = {stream["id"]: stream["status"] for stream in module.build_overview(2026)["workstreams"]}

    assert statuses["race-model"] == "Ready"
    assert statuses["rival-watch"] == "Active", "a 10-point rival is a live threat, not a watch item"


# ---------------------------------------------------------------------------
# degradation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overview_survives_a_failing_prediction_service(monkeypatch, capsys):
    _patch_feeds(monkeypatch, predictions=RuntimeError("model artefact missing"), reference=_REFERENCE)

    payload = module.build_overview(2026)

    assert payload["predicted_podium"] == []
    assert "race_control.predictions.failed" in capsys.readouterr().out
    # The rest of the desk still renders off the telemetry reference.
    assert payload["strategy_context"]["data_source"]["mode"] == "telemetry"
    assert [stream["status"] for stream in payload["workstreams"] if stream["id"] == "race-model"] == ["Waiting"]


@pytest.mark.unit
def test_overview_survives_a_failing_telemetry_reference(monkeypatch, capsys):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=ConnectionError("fastf1 cache corrupt"))

    payload = module.build_overview(2026)

    assert "race_control.strategy_reference.failed" in capsys.readouterr().out
    assert payload["strategy_context"]["data_source"]["mode"] == "heuristic"
    assert payload["strategy_context"]["stint_windows"]["modeled"] is True


@pytest.mark.unit
def test_overview_marks_the_strategy_context_heuristic_when_no_edition_has_been_run(monkeypatch):
    """A brand-new circuit returns no reference at all rather than raising."""
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=None)

    assert module.build_overview(2026)["strategy_context"]["data_source"]["mode"] == "heuristic"


@pytest.mark.unit
def test_overview_shows_the_forecasts_note_rather_than_current_conditions(monkeypatch):
    """6 Nov 2026: with the forecast down, the card showed OpenWeatherMap's 5 % before a ~90 % race."""
    _patch_feeds(monkeypatch)
    asked: list[str] = []

    async def current_conditions(location: str) -> dict:
        asked.append(location)
        return {"current": {"rain_probability_pct": 5, "track_temp_c": 29, "wind_speed_kph": 13}}

    monkeypatch.setattr(owm, "get_weather_for_circuit", current_conditions)

    payload = module.build_overview(2026)

    assert payload["weather"] == _NO_FORECAST_CARD
    assert asked == []
    assert [card["title"] for card in payload["risk_register"]][:1] == ["Safety car exposure"]
    assert "Weather feed offline" in [card["title"] for card in payload["risk_register"]]


# ---------------------------------------------------------------------------
# no event selected
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overview_skips_both_lookups_when_the_season_has_no_selected_race(monkeypatch):
    _patch_feeds(
        monkeypatch,
        dashboard=_dashboard(race=None),
        predictions=AssertionError("prediction must not be requested without a race"),
        reference=AssertionError("reference must not be requested without a race"),
    )

    payload = module.build_overview(2026)

    assert payload["predicted_podium"] == []
    assert payload["weather"] == _NO_FORECAST_CARD
    assert payload["risk_register"] == [], "no event means nothing to grade a risk against"
    assert payload["live_status"] == {"connected": False, "label": "Standby", "session": None}


@pytest.mark.unit
def test_overview_skips_the_prediction_for_an_event_with_no_round_number(monkeypatch):
    _patch_feeds(
        monkeypatch,
        dashboard=_dashboard(race={**_dashboard()["race"], "round": None}),
        predictions=AssertionError("prediction must not be requested without a round"),
        reference=_REFERENCE,
    )

    payload = module.build_overview(2026)

    assert payload["predicted_podium"] == []
    assert payload["strategy_context"]["data_source"]["mode"] == "telemetry"


@pytest.mark.unit
def test_overview_skips_the_telemetry_lookup_for_an_event_with_no_location(monkeypatch):
    _patch_feeds(
        monkeypatch,
        dashboard=_dashboard(race={**_dashboard()["race"], "location": None}),
        predictions=_PREDICTIONS,
        reference=AssertionError("reference must not be requested without a location"),
    )

    payload = module.build_overview(2026)

    assert payload["strategy_context"]["data_source"]["mode"] == "heuristic"
    assert payload["weather"] == _NO_FORECAST_CARD


@pytest.mark.unit
def test_overview_reports_an_empty_championship_as_no_competitors(monkeypatch):
    _patch_feeds(monkeypatch, dashboard=_dashboard(championship={}))

    payload = module.build_overview(2026)

    assert payload["strategy_context"]["competitors"] == []
    assert [stream["status"] for stream in payload["workstreams"] if stream["id"] == "rival-watch"] == ["Standby"]


# ---------------------------------------------------------------------------
# live status
# ---------------------------------------------------------------------------


def _race_started(offset: timedelta) -> dict[str, str]:
    """A race session that started ``offset`` ago (negative: still to come)."""
    return {"Race": (datetime.now(UTC) - offset).isoformat()}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "sessions", "live_status"),
    [
        (
            "in_progress",
            _race_started(timedelta(minutes=30)),
            {"connected": True, "label": "Race in progress", "session": "Race"},
        ),
        (
            "in_progress",
            _race_started(timedelta(hours=-12)),
            {"connected": False, "label": "Standby", "session": None},
        ),
        ("upcoming", _race_started(timedelta(days=-3)), {"connected": False, "label": "Standby", "session": None}),
        ("completed", _race_started(timedelta(days=3)), {"connected": False, "label": "Standby", "session": None}),
    ],
    ids=["live", "between-sessions", "upcoming", "completed"],
)
def test_overview_connects_the_live_banner_only_during_a_session(status, sessions, live_status, monkeypatch):
    race = {**_dashboard()["race"], "status": status, "sessions": sessions}
    _patch_feeds(monkeypatch, dashboard=_dashboard(race=race))

    payload = module.build_overview(2026)

    assert payload["live_status"] == live_status
    assert payload["strategy_context"]["phase"] == ("Live race desk" if live_status["connected"] else "Pre-race build")
