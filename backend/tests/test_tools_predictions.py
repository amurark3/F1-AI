"""Tests for app.api.tools.predictions — the briefing the model reads out.

Both tools are pure presentation over a service call, and that is exactly where
a prediction turns into a false statement: a dropped confidence range reads as
certainty, a missing warning hides that the model ran on stale data, and an
absent accuracy line lets the assistant claim a track record it does not have.

The service boundary is mocked so the formatting is what is under test; the
private ``_*_lines`` helpers are driven directly because each owns one
"there is no data for this section" decision.
"""

from __future__ import annotations

import pytest

from app.api.tools import predictions as predictions_tool
from app.api.tools.predictions import (
    _distribution_lines,
    _historical_lines,
    _pit_stop_lines,
    _safety_car_lines,
    _stint_lines,
    _undercut_lines,
    get_pit_strategy,
    get_race_predictions,
)


def _driver(position: int, **fields) -> dict:
    """One predicted finisher; overrides go in ``fields``."""
    base = {
        "position": position,
        "driver_name": f"Driver {position}",
        "team": "Red Bull",
        "confidence_low": 60,
        "confidence_high": 80,
        "factors": ["strong quali pace", "good tyre life"],
    }
    return {**base, **fields}


def _install_prediction(monkeypatch, payload) -> None:
    """Replace the cached-prediction service; an exception payload is raised."""

    def _compute(year, round_num):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(predictions_tool, "get_or_compute_race_prediction", _compute)


def _install_strategy(monkeypatch, payload) -> None:
    def _analyze(year, round_num, driver_code):
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(predictions_tool, "analyze_pit_strategy", _analyze)


def _stint(number: int, **fields) -> dict:
    base = {
        "stint": number,
        "compound": "SOFT",
        "laps": "1-18",
        "stint_length": 18,
        "avg_lap_time": "1:34.221",
        "degradation_sec": 0.42,
        "fresh_tyres": True,
    }
    return {**base, **fields}


# ---------------------------------------------------------------------------
# get_race_predictions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_full_grid_prediction_leads_with_the_pick_and_the_podium(monkeypatch):
    _install_prediction(
        monkeypatch,
        {
            "grand_prix": "Monaco Grand Prix",
            "predictions": [_driver(i, driver_name=f"D{i}") for i in range(1, 8)],
            "data_sources": ["f1db", "fastf1"],
            "accuracy": {},
            "warnings": [],
        },
    )

    briefing = get_race_predictions.invoke({"year": 2026, "round_num": 4})

    assert briefing.startswith("### Race Prediction: Monaco Grand Prix 2026")
    assert "**D1** (Red Bull) is my top pick for the win with 60-80% confidence." in briefing
    assert "Predicted podium: D1, D2, D3" in briefing
    assert "**Data sources:** f1db, fastf1" in briefing


@pytest.mark.unit
def test_the_top_five_get_their_reasoning_and_the_rest_get_a_table(monkeypatch):
    _install_prediction(
        monkeypatch,
        {
            "predictions": [_driver(i) for i in range(1, 8)],
            "data_sources": ["f1db"],
        },
    )

    briefing = get_race_predictions.invoke({"year": 2026, "round_num": 4})

    assert "**P5. Driver 5** (Red Bull) [60-80% confidence]" in briefing
    assert "  Key factors: strong quali pace; good tyre life" in briefing
    assert "#### Positions 6-20" in briefing
    assert "| P6 | Driver 6 | Red Bull | 60-80% |" in briefing
    # A driver in the summary table must not also get a detail block.
    assert "**P6. Driver 6**" not in briefing


@pytest.mark.unit
def test_a_short_grid_omits_the_summary_table_entirely(monkeypatch):
    _install_prediction(monkeypatch, {"predictions": [_driver(i) for i in range(1, 4)], "data_sources": []})

    assert "#### Positions 6-20" not in get_race_predictions.invoke({"year": 2026, "round_num": 4})


@pytest.mark.unit
def test_the_measured_accuracy_is_quoted_when_races_have_been_scored(monkeypatch):
    """Without this line the assistant would present its record as unbounded."""
    _install_prediction(
        monkeypatch,
        {
            "predictions": [_driver(1)],
            "data_sources": ["f1db"],
            "accuracy": {
                "races_evaluated": 12,
                "recent_top3_pct": 66.7,
                "recent_top10_pct": 90.0,
                "avg_position_error": 2.4,
            },
        },
    )

    briefing = get_race_predictions.invoke({"year": 2026, "round_num": 4})

    assert "**Model accuracy** (last 12 races): Top-3 66.7%, Top-10 90.0%, Avg position error 2.4" in briefing


@pytest.mark.unit
def test_no_accuracy_claim_is_made_before_any_race_has_been_scored(monkeypatch):
    _install_prediction(
        monkeypatch,
        {"predictions": [_driver(1)], "data_sources": ["f1db"], "accuracy": {"races_evaluated": 0}},
    )

    assert "Model accuracy" not in get_race_predictions.invoke({"year": 2026, "round_num": 4})


@pytest.mark.unit
def test_service_warnings_are_surfaced_alongside_the_prediction(monkeypatch):
    """A prediction built on stale inputs must say so, not read as fresh."""
    _install_prediction(
        monkeypatch,
        {
            "predictions": [_driver(1)],
            "data_sources": ["f1db"],
            "warnings": ["qualifying data unavailable", "using last season's form"],
        },
    )

    briefing = get_race_predictions.invoke({"year": 2026, "round_num": 4})

    assert "**Note:** qualifying data unavailable; using last season's form" in briefing


@pytest.mark.unit
def test_an_empty_prediction_set_explains_itself_with_the_service_warnings(monkeypatch):
    _install_prediction(monkeypatch, {"predictions": [], "warnings": ["round 9 has not been scheduled"]})

    assert get_race_predictions.invoke({"year": 2026, "round_num": 9}) == (
        "Could not generate predictions for 2026 Round 9. round 9 has not been scheduled"
    )


@pytest.mark.unit
def test_an_empty_prediction_set_with_no_warnings_still_explains_itself(monkeypatch):
    _install_prediction(monkeypatch, {})

    assert get_race_predictions.invoke({"year": 2026, "round_num": 9}) == (
        "Could not generate predictions for 2026 Round 9. No driver data available."
    )


@pytest.mark.unit
def test_a_service_crash_becomes_a_message_the_model_can_relay(monkeypatch):
    _install_prediction(monkeypatch, RuntimeError("model artefact missing"))

    assert get_race_predictions.invoke({"year": 2026, "round_num": 4}) == (
        "Prediction analysis failed: model artefact missing"
    )


# ---------------------------------------------------------------------------
# Section helpers — each owns one "no data" decision
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("helper", "empty_input"),
    [
        (_stint_lines, []),
        (_pit_stop_lines, []),
        (_undercut_lines, []),
        (_distribution_lines, {}),
        (_historical_lines, {}),
        (_historical_lines, {"dominant_strategy": "1-stop", "editions": []}),
        (_safety_car_lines, {}),
    ],
)
def test_a_section_with_no_data_contributes_no_heading(helper, empty_input):
    """An empty heading would advertise analysis that was never done."""
    assert helper(empty_input) == []


@pytest.mark.unit
def test_stints_are_labelled_with_the_compound_colour_the_user_knows(monkeypatch):
    lines = _stint_lines([_stint(1, compound="MEDIUM"), _stint(2, compound="INTERMEDIATE")])

    assert "| 1 | MEDIUM (Yellow) |" in lines[3]
    assert "| 2 | INTER (Green) |" in lines[4]


@pytest.mark.unit
def test_an_unknown_compound_is_passed_through_rather_than_dropped():
    assert "| 1 | ULTRASOFT |" in _stint_lines([_stint(1, compound="ULTRASOFT")])[3]


@pytest.mark.unit
def test_degradation_carries_an_explicit_sign_so_improvement_is_visible():
    positive, negative = _stint_lines([_stint(1), _stint(2, degradation_sec=-0.15)])[3:5]

    assert "| +0.42s |" in positive
    assert "| -0.15s |" in negative


@pytest.mark.unit
def test_a_scrubbed_set_is_reported_as_not_fresh():
    assert "| No |" in _stint_lines([_stint(1, fresh_tyres=False)])[3]


@pytest.mark.unit
@pytest.mark.parametrize(("count", "expected"), [(1, "1 stop"), (2, "2 stops")])
def test_the_pit_stop_count_is_pluralised(count, expected):
    stops = [{"lap": 12 + i} for i in range(count)]

    assert _pit_stop_lines(stops)[0] == f"**Pit stops:** {expected}"


@pytest.mark.unit
def test_a_pit_stop_shows_the_position_held_going_in_when_it_is_known():
    lines = _pit_stop_lines([{"lap": 18, "position_before": 3}, {"lap": 34}])

    assert lines[1] == "  - Lap 18 (P3)"
    assert lines[2] == "  - Lap 34"


@pytest.mark.unit
def test_an_undercut_attempt_names_its_target_and_outcome():
    lines = _undercut_lines([{"type": "undercut", "target_driver": "LEC", "lap": 21, "result": "successful"}])

    assert lines[1] == "  - **Undercut** vs LEC (lap 21): successful"


@pytest.mark.unit
def test_the_strategy_distribution_pluralises_each_driver_count():
    lines = _distribution_lines({"1-stop": 14, "2-stop": 1})

    assert lines[1:] == ["  - 1-stop: 14 drivers", "  - 2-stop: 1 driver", ""]


@pytest.mark.unit
def test_historical_editions_are_listed_under_the_dominant_strategy():
    lines = _historical_lines(
        {
            "dominant_strategy": "1-stop",
            "editions": [{"year": 2024, "winner_strategy": "1-stop", "avg_stops": 1.2}],
        }
    )

    assert lines[1] == "**Dominant strategy:** 1-stop"
    assert lines[2] == "  - 2024: Winner used 1-stop (avg 1.2 stops)"


@pytest.mark.unit
def test_a_missing_dominant_strategy_is_reported_as_unknown():
    lines = _historical_lines({"editions": [{"year": 2023, "winner_strategy": "2-stop", "avg_stops": 2.0}]})

    assert lines[1] == "**Dominant strategy:** N/A"


@pytest.mark.unit
def test_the_safety_car_probability_carries_its_circuit_context():
    assert _safety_car_lines({"safety_car_probability": 78, "safety_car_context": "walls close on both sides"}) == [
        "**Safety car probability:** 78% - walls close on both sides"
    ]


# ---------------------------------------------------------------------------
# get_pit_strategy
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_driver_query_returns_stints_stops_and_undercuts(monkeypatch):
    _install_strategy(
        monkeypatch,
        {
            "grand_prix": "Monaco Grand Prix",
            "stints": [_stint(1)],
            "pit_stops": [{"lap": 18, "position_before": 2}],
            "undercut_overcut": [{"type": "overcut", "target_driver": "NOR", "lap": 22, "result": "failed"}],
            "safety_car_probability": 78,
            "safety_car_context": "street circuit",
        },
    )

    report = get_pit_strategy.invoke({"year": 2026, "round_num": 4, "driver_code": "VER"})

    assert report.startswith("### Pit Strategy: VER - Monaco Grand Prix 2026")
    assert "#### Stint Breakdown" in report
    assert "**Pit stops:** 1 stop" in report
    assert "#### Undercut/Overcut Analysis" in report
    assert "**Safety car probability:** 78% - street circuit" in report


@pytest.mark.unit
def test_omitting_the_driver_gives_the_circuit_level_view_instead(monkeypatch):
    """The per-driver sections would be meaningless without a driver to attribute them to."""
    _install_strategy(
        monkeypatch,
        {
            "grand_prix": "Italian Grand Prix",
            "strategy_distribution": {"1-stop": 18},
            "historical_strategies": {
                "dominant_strategy": "1-stop",
                "editions": [{"year": 2025, "winner_strategy": "1-stop", "avg_stops": 1.0}],
            },
        },
    )

    report = get_pit_strategy.invoke({"year": 2026, "round_num": 5})

    assert report.startswith("### Strategy Overview: Italian Grand Prix 2026")
    assert "#### Strategy Distribution" in report
    assert "#### Historical Context" in report
    assert "#### Stint Breakdown" not in report


@pytest.mark.unit
def test_an_unknown_grand_prix_falls_back_to_the_round_number(monkeypatch):
    _install_strategy(monkeypatch, {"strategy_distribution": {"1-stop": 2}})

    assert get_pit_strategy.invoke({"year": 2026, "round_num": 7}).startswith("### Strategy Overview: Round 7 2026")


@pytest.mark.unit
def test_an_analysis_error_is_returned_instead_of_an_empty_report(monkeypatch):
    _install_strategy(monkeypatch, {"error": "No lap data for 2026 Round 3."})

    assert get_pit_strategy.invoke({"year": 2026, "round_num": 3}) == "No lap data for 2026 Round 3."


@pytest.mark.unit
def test_a_strategy_crash_becomes_a_message_the_model_can_relay(monkeypatch):
    _install_strategy(monkeypatch, RuntimeError("fastf1 cache corrupt"))

    assert get_pit_strategy.invoke({"year": 2026, "round_num": 3}) == "Strategy analysis failed: fastf1 cache corrupt"
