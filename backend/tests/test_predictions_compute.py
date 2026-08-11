"""Tests for app.data.predictions.compute — the prediction pipeline.

``compute_race_predictions`` orchestrates a stack of loaders that are each
allowed to fail. The behaviour worth guarding is what happens *around* those
failures:

* **A degraded load must degrade the prediction, not kill it.** A schedule that
  will not load, a missing qualifying session, absent standings — each drops a
  signal and records a warning, and the grid is still predicted.
* **Weights must renormalise when a signal is missing.** They are shares of one
  whole; if a missing signal simply vanished, every score would shrink toward
  zero and the ranking would silently change character.
* **No entered driver may be dropped.** A driver without a qualifying time is
  back-filled from the championship entry list, flagged, and still predicted.

Every loader is stubbed at compute's own module namespace — this file tests the
orchestration, not the loaders, which have their own suites.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from app.data.predictions import compute as module
from app.data.predictions.driver_score import DriverScore

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _schedule(rows: list[dict]) -> pd.DataFrame:
    """A schedule frame in the shape ``_load_event_context`` filters on."""
    return pd.DataFrame(rows, columns=["RoundNumber", "EventName", "Location"])


def _quali(code: str, position: int, *, team: str = "Red Bull") -> dict:
    return {
        "driver_code": code,
        "driver_name": f"{code} Driver",
        "team": team,
        "position": position,
    }


def _scored(code: str, score: float, *, team: str = "Red Bull", factors: list[str] | None = None) -> dict:
    return {
        "driver_code": code,
        "driver_name": f"{code} Driver",
        "team": team,
        "score": score,
        "confidence_low": max(1, int(score) - 2),
        "confidence_high": int(score) + 2,
        "factors": factors or [],
        "model_attribution": None,
    }


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub every loader compute calls; tests override individual entries.

    The returned dict is the control surface: mutate a key before calling
    ``compute_race_predictions`` to change what that stage produces. Callables
    are invoked, exceptions raised, everything else returned as-is.
    """
    state: dict[str, Any] = {
        "schedule": _schedule([{"RoundNumber": 5, "EventName": "Monaco Grand Prix", "Location": "Monte Carlo"}]),
        "qualifying_has_occurred": True,
        "qualifying": [_quali("VER", 1), _quali("NOR", 2, team="McLaren")],
        "practice": [],
        "constructor_standings": [{"team": "Red Bull", "position": 1}],
        "driver_standings": {"VER": 1, "NOR": 2},
        "circuit_history": {"VER": [1, 2]},
        "sprint_result": [],
        "adaptive_corrections": {},
        "grid_deltas": {"VER": 1.5},
        "recent_sprint_form": {},
        "roster": [],
        "risk_predictions": [{"driver_code": "VER", "dnf_risk": 0.1}],
        "accuracy": {"total": 3},
        "review": {"status": "ok"},
        "saved": [],
        "save_error": None,
        "scores": {},
    }

    def _resolve(key: str, *args):
        value = state[key]
        if isinstance(value, BaseException):
            raise value
        return value(*args) if callable(value) else value

    monkeypatch.setattr(module.fastf1, "get_event_schedule", lambda year, include_testing: _resolve("schedule"))
    monkeypatch.setattr(module, "_qualifying_has_occurred", lambda row: _resolve("qualifying_has_occurred"))
    monkeypatch.setattr(module, "_load_qualifying", lambda year, rnd: _resolve("qualifying"))
    monkeypatch.setattr(module, "_load_practice", lambda year, rnd: _resolve("practice"))
    monkeypatch.setattr(module, "_load_constructor_standings", lambda year: _resolve("constructor_standings"))
    monkeypatch.setattr(module, "_load_driver_standings", lambda year: _resolve("driver_standings"))
    monkeypatch.setattr(module, "_load_circuit_history", lambda year, rnd, key: _resolve("circuit_history"))
    monkeypatch.setattr(module, "_load_sprint_result", lambda year, rnd: _resolve("sprint_result"))
    monkeypatch.setattr(module, "_adaptive_position_corrections", lambda: _resolve("adaptive_corrections"))
    monkeypatch.setattr(module, "_load_grid_to_finish_delta", lambda year, rnd, key: _resolve("grid_deltas"))
    monkeypatch.setattr(module, "_load_recent_sprint_form", lambda year, rnd: _resolve("recent_sprint_form"))
    monkeypatch.setattr(module, "driver_standings_detailed", lambda year: _resolve("roster"))
    monkeypatch.setattr(module, "get_accuracy_stats", lambda: _resolve("accuracy"))
    monkeypatch.setattr(module, "get_prediction_review", lambda year, rnd: _resolve("review"))
    monkeypatch.setattr(
        module,
        "_compute_risk_predictions",
        lambda predictions, by_code, year, rnd: _resolve("risk_predictions"),
    )

    def _score_driver(driver, signals):
        state.setdefault("signals", []).append(signals)
        override = state["scores"].get(driver["driver_code"])
        if override is not None:
            return override
        return DriverScore(
            scored=_scored(
                driver["driver_code"],
                float(driver.get("position", 10)),
                team=driver.get("team", ""),
            ),
            used_model=False,
            used_adaptive=False,
            used_recent_form=False,
        )

    def _save(year, round_num, result):
        if state["save_error"] is not None:
            raise state["save_error"]
        state["saved"].append((year, round_num, result))

    monkeypatch.setattr(module, "score_driver", _score_driver)
    monkeypatch.setattr(module, "save_prediction", _save)
    return state


# ---------------------------------------------------------------------------
# _load_event_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_event_context_reads_the_name_and_circuit_from_the_schedule(pipeline):
    context = module._load_event_context(2024, 5)

    assert context.gp_name == "Monaco Grand Prix"
    assert context.circuit_key == "Monte Carlo"
    assert context.event_row is not None
    assert context.warnings == []


@pytest.mark.unit
def test_an_unlisted_round_falls_back_to_round_identifiers(pipeline):
    pipeline["schedule"] = _schedule([])

    context = module._load_event_context(2024, 5)

    assert context.gp_name == "Round 5"
    assert context.circuit_key == "round_5"
    assert context.event_row is None
    assert context.warnings == []


@pytest.mark.unit
def test_a_schedule_failure_degrades_to_round_identifiers_with_a_warning(pipeline):
    pipeline["schedule"] = RuntimeError("network down")

    context = module._load_event_context(2024, 5)

    assert context.gp_name == "Round 5"
    assert context.circuit_key == "round_5"
    assert context.warnings == ["Could not load event schedule: network down"]


# ---------------------------------------------------------------------------
# _load_session_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_qualifying_is_used_when_it_has_run(pipeline):
    session = module._load_session_data(2024, 5, event_row=object())

    assert session.quali_data == pipeline["qualifying"]
    assert session.is_pre_qualifying is False
    assert session.data_sources == ["qualifying"]
    assert session.warnings == []


@pytest.mark.unit
def test_practice_pace_stands_in_for_a_missing_qualifying_session(pipeline):
    pipeline["qualifying"] = []
    pipeline["practice"] = [_quali("VER", 1)]

    session = module._load_session_data(2024, 5, event_row=object())

    assert session.quali_data == pipeline["practice"]
    assert session.is_pre_qualifying is True
    assert session.data_sources == ["practice"]
    assert session.warnings == ["Qualifying data unavailable; using practice session pace as proxy"]


@pytest.mark.unit
def test_no_session_data_at_all_falls_back_to_history(pipeline):
    pipeline["qualifying"] = []
    pipeline["practice"] = []

    session = module._load_session_data(2024, 5, event_row=object())

    assert session.quali_data is None
    assert session.is_pre_qualifying is True
    assert session.warnings == ["No qualifying or practice data available; using historical data only"]


@pytest.mark.unit
def test_a_weekend_that_has_not_started_is_never_probed(pipeline):
    """Probing FastF1 for an unrun session is a slow failure, so it is skipped."""
    pipeline["qualifying_has_occurred"] = False
    pipeline["qualifying"] = AssertionError("qualifying must not be loaded")
    pipeline["practice"] = AssertionError("practice must not be loaded")

    session = module._load_session_data(2024, 5, event_row=object())

    assert session.quali_data is None
    assert session.warnings == ["Race weekend has not started; using historical form only"]


@pytest.mark.unit
def test_without_an_event_row_the_sessions_are_attempted_anyway(pipeline):
    """No schedule row means no session time to check — try the load instead."""
    pipeline["qualifying_has_occurred"] = AssertionError("must not be consulted")

    session = module._load_session_data(2024, 5, event_row=None)

    assert session.data_sources == ["qualifying"]


# ---------------------------------------------------------------------------
# _load_supporting_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_supporting_data_records_a_source_for_every_feed_that_answered(pipeline):
    pipeline["sprint_result"] = [{"driver_code": "VER", "position": 1}]
    pipeline["adaptive_corrections"] = {"VER": {"correction": 1.0, "samples": 4}}

    support = module._load_supporting_data(2024, 5, "Monte Carlo")

    assert support.data_sources == [
        "constructor_standings",
        "driver_standings",
        "circuit_history",
        "sprint_result",
        "adaptive_history",
    ]
    assert support.warnings == []
    assert support.sprint_positions == {"VER": 1}
    assert support.had_sprint is True
    assert support.grid_deltas == {"VER": 1.5}


@pytest.mark.unit
def test_missing_constructor_standings_are_the_only_feed_that_warns(pipeline):
    pipeline["constructor_standings"] = []
    pipeline["driver_standings"] = {}
    pipeline["circuit_history"] = {}

    support = module._load_supporting_data(2024, 5, "Monte Carlo")

    assert support.warnings == ["Constructor standings unavailable"]
    assert support.data_sources == []
    assert support.had_sprint is False
    assert support.sprint_positions == {}


# ---------------------------------------------------------------------------
# _build_roster
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_driver_without_a_qualifying_time_is_added_behind_the_slowest_qualifier(pipeline):
    pipeline["roster"] = [
        {"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 1},
        {"code": "NOR", "name": "Lando Norris", "team": "McLaren", "position": 2},
        {"code": "LAW", "name": "Liam Lawson", "team": "RB", "position": 15},
    ]

    roster = module._build_roster(2024, [_quali("VER", 1), _quali("NOR", 2)])

    assert [driver["driver_code"] for driver in roster.drivers] == ["VER", "NOR", "LAW"]
    assert roster.drivers[-1] == {
        "driver_code": "LAW",
        "driver_name": "Liam Lawson",
        "team": "RB",
        "position": 3,
        "no_qualifying_time": True,
    }
    assert roster.warnings == [
        "1 entered driver(s) had no qualifying time; included from championship entry list at back of grid"
    ]
    assert roster.data_sources == ["championship_position"]


@pytest.mark.unit
def test_back_filled_drivers_keep_championship_order(pipeline):
    pipeline["roster"] = [
        {"code": "LAW", "name": "Liam Lawson", "team": "RB", "position": 15},
        {"code": "HUL", "name": "Nico Hulkenberg", "team": "Sauber", "position": 9},
    ]

    roster = module._build_roster(2024, [_quali("VER", 1)])

    assert [driver["driver_code"] for driver in roster.drivers] == ["VER", "HUL", "LAW"]
    assert [driver["position"] for driver in roster.drivers] == [1, 2, 3]


@pytest.mark.unit
def test_with_no_session_at_all_the_whole_roster_is_predicted_without_a_warning(pipeline):
    pipeline["roster"] = [
        {"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 1},
        {"code": "NOR", "name": "Lando Norris", "team": "McLaren", "position": 2},
    ]

    roster = module._build_roster(2024, None)

    assert [driver["position"] for driver in roster.drivers] == [1, 2]
    assert roster.warnings == []
    assert roster.data_sources == ["championship_position"]


@pytest.mark.unit
def test_a_complete_qualifying_field_needs_no_back_filling(pipeline):
    pipeline["roster"] = [{"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 1}]

    roster = module._build_roster(2024, [_quali("VER", 1)])

    assert [driver["driver_code"] for driver in roster.drivers] == ["VER"]
    assert roster.warnings == []
    assert roster.data_sources == []


@pytest.mark.unit
def test_an_empty_entry_list_leaves_the_session_field_untouched(pipeline):
    pipeline["roster"] = []

    roster = module._build_roster(2024, [_quali("VER", 1)])

    assert [driver["driver_code"] for driver in roster.drivers] == ["VER"]
    assert roster.warnings == []


@pytest.mark.unit
def test_a_failing_entry_list_warns_but_keeps_the_qualifiers(pipeline):
    pipeline["roster"] = RuntimeError("f1db unavailable")

    roster = module._build_roster(2024, [_quali("VER", 1)])

    assert [driver["driver_code"] for driver in roster.drivers] == ["VER"]
    assert roster.warnings == ["Could not load full-grid roster: f1db unavailable"]


# ---------------------------------------------------------------------------
# _active_weights
# ---------------------------------------------------------------------------


def _session(*, quali: bool, pre: bool) -> module.SessionData:
    return module.SessionData(quali_data=[_quali("VER", 1)] if quali else None, is_pre_qualifying=pre)


def _support(**kwargs) -> module.SupportingData:
    return module.SupportingData(**kwargs)


@pytest.mark.unit
def test_a_full_signal_set_keeps_the_configured_proportions():
    weights = module._active_weights(
        _session(quali=True, pre=False),
        _support(
            circuit_history={"VER": [1]},
            constructor_standings=[{"team": "Red Bull"}],
            grid_deltas={"VER": 1.0},
        ),
    )

    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights == pytest.approx(
        {
            "qualifying": 0.35,
            "recent_form": 0.25,
            "circuit_history": 0.20,
            "team_strength": 0.15,
            "grid_delta": 0.05,
        }
    )


@pytest.mark.unit
def test_missing_signals_are_redistributed_rather_than_dropped():
    weights = module._active_weights(_session(quali=True, pre=False), _support())

    assert set(weights) == {"qualifying", "recent_form"}
    assert sum(weights.values()) == pytest.approx(1.0)
    # 0.35 : 0.25 preserved as a ratio.
    assert weights["qualifying"] / weights["recent_form"] == pytest.approx(0.35 / 0.25)


@pytest.mark.unit
def test_a_sprint_weekend_leans_on_race_pace_and_discounts_qualifying():
    weights = module._active_weights(
        _session(quali=True, pre=False),
        _support(had_sprint=True),
    )

    raw_total = 0.30 + 0.20 + 0.25
    assert weights["sprint"] == pytest.approx(0.30 / raw_total)
    assert weights["qualifying"] == pytest.approx(0.20 / raw_total)
    assert weights["sprint"] > weights["qualifying"]


@pytest.mark.unit
def test_practice_pace_carries_far_less_weight_than_real_qualifying():
    weights = module._active_weights(_session(quali=True, pre=True), _support())

    assert weights["qualifying"] == pytest.approx(0.10 / 0.35)
    assert weights["recent_form"] > weights["qualifying"]


@pytest.mark.unit
def test_recent_form_takes_the_whole_weight_when_it_is_the_only_signal():
    weights = module._active_weights(_session(quali=False, pre=True), _support())

    assert weights == {"recent_form": 1.0}


@pytest.mark.unit
def test_a_zero_total_is_returned_unnormalised_rather_than_dividing_by_zero(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(module, "RECENT_FORM_WEIGHT", 0.0)

    assert module._active_weights(_session(quali=False, pre=True), _support()) == {"recent_form": 0.0}


# ---------------------------------------------------------------------------
# _rank
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ranking_puts_the_lowest_score_on_pole_and_numbers_from_one():
    ranked = module._rank([_scored("NOR", 4.2), _scored("VER", 1.1), _scored("LEC", 2.6)])

    assert [row["driver_code"] for row in ranked] == ["VER", "LEC", "NOR"]
    assert [row["position"] for row in ranked] == [1, 2, 3]
    assert "score" not in ranked[0]
    assert ranked[0]["model_attribution"] is None


@pytest.mark.unit
def test_ranking_an_empty_field_returns_nothing():
    assert module._rank([]) == []


# ---------------------------------------------------------------------------
# compute_race_predictions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_healthy_weekend_predicts_the_full_grid_and_saves_it(pipeline):
    result = module.compute_race_predictions(2024, 5)

    assert result["year"] == 2024
    assert result["round"] == 5
    assert result["grand_prix"] == "Monaco Grand Prix"
    assert result["logic_version"] == module.PREDICTION_LOGIC_VERSION
    assert result["accuracy"] == {"total": 3}
    assert result["prediction_review"] == {"status": "ok"}
    assert [row["driver_code"] for row in result["predictions"]] == ["VER", "NOR"]
    assert result["prediction_phase"] == "post_qualifying"
    assert result["risk_predictions"] == pipeline["risk_predictions"]
    assert result["weather_impact"] == "dry"
    assert result["wet_scenario"] is None
    assert result["warnings"] is None
    assert pipeline["saved"] == [(2024, 5, result)]


@pytest.mark.unit
def test_data_sources_are_deduplicated_and_sorted(pipeline):
    pipeline["adaptive_corrections"] = {"VER": {"correction": 1.0, "samples": 3}}
    pipeline["scores"] = {
        "VER": DriverScore(
            scored=_scored("VER", 1.0),
            used_model=True,
            used_adaptive=True,
            used_recent_form=True,
        )
    }

    result = module.compute_race_predictions(2024, 5)

    assert result["data_sources"] == [
        "adaptive_history",
        "circuit_history",
        "constructor_standings",
        "driver_standings",
        "last_5_races",
        "qualifying",
        "trained_ml_model",
    ]


@pytest.mark.unit
def test_optional_sources_are_not_advertised_when_no_driver_used_them(pipeline):
    result = module.compute_race_predictions(2024, 5)

    assert "last_5_races" not in result["data_sources"]
    assert "trained_ml_model" not in result["data_sources"]
    assert "adaptive_history" not in result["data_sources"]


@pytest.mark.unit
def test_every_stage_warning_reaches_the_response(pipeline):
    pipeline["schedule"] = RuntimeError("network down")
    pipeline["qualifying"] = []
    pipeline["practice"] = []
    pipeline["constructor_standings"] = []
    pipeline["roster"] = [{"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 1}]

    result = module.compute_race_predictions(2024, 5)

    assert result["warnings"] == [
        "Could not load event schedule: network down",
        "No qualifying or practice data available; using historical data only",
        "Constructor standings unavailable",
    ]
    assert result["grand_prix"] == "Round 5"
    assert result["prediction_phase"] == "pre_qualifying"


@pytest.mark.unit
def test_an_empty_grid_returns_an_explicit_no_data_response(pipeline):
    pipeline["qualifying"] = []
    pipeline["practice"] = []
    pipeline["roster"] = []

    result = module.compute_race_predictions(2024, 5)

    assert result["predictions"] == []
    assert result["risk_predictions"] == []
    assert result["weather_impact"] == "unknown"
    assert result["warnings"][-1] == "No driver data available for predictions"
    assert "prediction_phase" not in result
    assert pipeline["saved"] == []


@pytest.mark.unit
def test_the_signals_handed_to_the_scorer_carry_the_loaded_context(pipeline):
    pipeline["sprint_result"] = [{"driver_code": "VER", "position": 2}]
    pipeline["adaptive_corrections"] = {"VER": {"correction": -1.0, "samples": 5}}
    pipeline["recent_sprint_form"] = {"VER": [1, 2]}

    module.compute_race_predictions(2024, 5)

    signals = pipeline["signals"][0]
    assert signals.year == 2024
    assert signals.round_num == 5
    assert signals.had_sprint is True
    assert signals.sprint_positions == {"VER": 2}
    assert signals.recent_sprint_form == {"VER": [1, 2]}
    assert signals.adaptive_corrections == {"VER": {"correction": -1.0, "samples": 5}}
    assert signals.circuit_history == {"VER": [1, 2]}
    assert signals.grid_deltas == {"VER": 1.5}
    assert signals.is_pre_qualifying is False
    assert signals.ml_blend_weight == module.ML_BLEND_WEIGHT
    assert signals.adaptive_weight == module.ADAPTIVE_CORRECTION_WEIGHT
    assert sum(signals.active_weights.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_a_failed_save_is_logged_without_losing_the_prediction(pipeline):
    pipeline["save_error"] = RuntimeError("store offline")

    result = module.compute_race_predictions(2024, 5)

    assert [row["driver_code"] for row in result["predictions"]] == ["VER", "NOR"]
    assert pipeline["saved"] == []


@pytest.mark.unit
def test_risk_predictions_receive_the_ranked_grid_keyed_by_driver(pipeline, monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def _risk(predictions, by_code, year, round_num):
        seen.update({"predictions": predictions, "by_code": by_code, "year": year, "round": round_num})
        return []

    monkeypatch.setattr(module, "_compute_risk_predictions", _risk)

    module.compute_race_predictions(2024, 5)

    assert [row["driver_code"] for row in seen["predictions"]] == ["VER", "NOR"]
    assert set(seen["by_code"]) == {"VER", "NOR"}
    assert seen["by_code"]["VER"]["score"] == 1.0
    assert (seen["year"], seen["round"]) == (2024, 5)
