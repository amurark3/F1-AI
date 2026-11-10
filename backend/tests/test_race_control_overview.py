"""Tests for app.services.race_control.overview — the command-center composer.

``build_overview`` is the single payload the Race Control page renders, and it
is assembled from feeds that fail independently: the schedule/standings
dashboard, the cached race prediction, the circuit's last edition (its measured
plan), the per-session forecast (which alone feeds the race-day card), and the circuit map. The risk is a partial outage arriving as a confident page:
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
from tests import sao_paulo_2025_support as r21

_PREDICTIONS = {
    "predictions": [
        {"driver": "VER", "position": 1},
        {"driver": "NOR", "position": 2},
        {"driver": "LEC", "position": 3},
        {"driver": "RUS", "position": 4},
    ]
}

# The 2025 São Paulo Grand Prix as the edition search returns it (captured 10 Nov 2026).
_REFERENCE = r21.reference()


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
def test_overview_feeds_the_edition_reference_into_the_strategy_context(monkeypatch):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=_REFERENCE)

    context = module.build_overview(2026)["strategy_context"]

    assert context["data_source"]["mode"] == "edition"
    assert (context["data_source"]["edition_year"], context["data_source"]["sample_size"]) == (2025, 17)
    assert context["plan"]["compounds"] == ["Medium", "Soft", "Medium"]
    assert context["pit_model"] == {"pit_lane_seconds": 23.5, "pit_lane_stops": 34}
    # Constructors reach the competitor table through the dashboard block.
    assert [row["team"] for row in context["competitors"]] == ["McLaren", "Ferrari"]


@pytest.mark.unit
def test_overview_flags_the_dry_plan_secondary_from_the_race_day_forecast(monkeypatch):
    _patch_feeds(monkeypatch, reference=_REFERENCE, sessions=_race_day(88))

    branch = module.build_overview(2026)["strategy_context"]["rain_branch"]

    assert branch["rain_pct"] == 88
    assert branch["note"].startswith(f"{session_weather.RACE_DAY_FORECAST}: 88% peak rain probability")


@pytest.mark.unit
def test_overview_strategy_segment_reads_the_race_day_forecast_for_the_rain_branch(monkeypatch):
    _patch_feeds(monkeypatch, reference=_REFERENCE, sessions=_race_day(88))
    monkeypatch.setattr(module, "_selected_race", lambda _year: _dashboard()["race"])
    monkeypatch.setattr(module, "_top_constructors", lambda _year: [])
    monkeypatch.setattr(module, "get_cached_race_prediction", lambda *_a: None)

    context = module.build_overview_strategy(2026)["strategy_context"]

    assert context["rain_branch"]["rain_pct"] == 88
    assert context["plan"]["stints"][0] == {"compound": "Medium", "start_lap": 1, "end_lap": 34}


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
    assert register["Elevated rain risk"]["detail"].startswith(
        f"{session_weather.RACE_DAY_FORECAST}: 55% peak rain probability in the race window"
    )


@pytest.mark.unit
def test_overview_workstreams_report_the_model_ready_with_an_edition_behind_the_plan(monkeypatch):
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
    # The rest of the desk still renders off the edition reference.
    assert payload["strategy_context"]["data_source"]["mode"] == "edition"
    assert [stream["status"] for stream in payload["workstreams"] if stream["id"] == "race-model"] == ["Waiting"]


@pytest.mark.unit
def test_overview_survives_a_failing_edition_reference_and_says_it_was_not_read(monkeypatch, capsys):
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=ConnectionError("openf1 unreachable"))

    payload = module.build_overview(2026)

    assert "race_control.strategy_reference.failed" in capsys.readouterr().out
    context = payload["strategy_context"]
    assert context["data_source"]["mode"] == "none"
    # A failed read is not "this circuit has no edition".
    assert context["primary_call"]["summary"].startswith("No baseline plan right now")
    assert context["plan"] is None


@pytest.mark.unit
def test_overview_has_no_plan_when_the_circuit_has_no_edition(monkeypatch):
    """A brand-new circuit returns no reference at all rather than raising."""
    _patch_feeds(monkeypatch, predictions=_PREDICTIONS, reference=None)

    context = module.build_overview(2026)["strategy_context"]

    assert context["data_source"]["mode"] == "none"
    assert context["primary_call"]["summary"].startswith("No baseline plan: this circuit has no completed race")


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
    register = {card["title"]: card for card in payload["risk_register"]}
    assert next(iter(register)) == "Safety car exposure"
    assert "Dry conditions expected" not in register
    unavailable = register["Race-day forecast unavailable"]
    assert unavailable["level"] == "Medium"
    assert unavailable["detail"].startswith("later ")
    assert "%" not in unavailable["detail"]


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
    assert payload["strategy_context"]["data_source"]["mode"] == "edition"


@pytest.mark.unit
def test_overview_skips_the_edition_lookup_for_an_event_with_no_location(monkeypatch):
    _patch_feeds(
        monkeypatch,
        dashboard=_dashboard(race={**_dashboard()["race"], "location": None}),
        predictions=_PREDICTIONS,
        reference=AssertionError("reference must not be requested without a location"),
    )

    payload = module.build_overview(2026)

    assert payload["strategy_context"]["data_source"]["mode"] == "none"
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
