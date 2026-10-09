"""Tests for app.data.strategy.pit — the pit-strategy entry point.

``analyze_pit_strategy`` answers two different questions from one loader: a
field-wide view of the race, or one driver's stints. What the tests guard:

* **A race that has not run must say so.** Returning an empty overview would
  read as "nobody pitted" rather than "no data".
* **An unknown driver must be named, with the alternatives.** Silently falling
  back to the circuit overview would answer a question nobody asked.
* **Historical lookups are best-effort.** They reach the network; a failure
  degrades that section only, leaving the race's own stint data intact.
"""

from __future__ import annotations

import pytest

from app.data.strategy import pit as module
from tests.strategy_fixture import laps_frame, results_frame, stint_rows

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _field() -> object:
    """Three cars: two on the same one-stop, one on a two-stop."""
    return laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 22), ("HARD", 23, 50)]),
        stint_rows("LEC", [("SOFT", 1, 14), ("MEDIUM", 15, 32), ("HARD", 33, 50)]),
    )


@pytest.fixture
def race(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub the loader and both historical sections; tests override entries."""
    state: dict = {
        "race_data": {
            "laps": _field(),
            "results": results_frame([("VER", 1), ("NOR", 2), ("LEC", 3)]),
            "event_name": "Monaco Grand Prix",
            "location": "Monte Carlo",
        },
        "historical": {"dominant_strategy": "1-stop Medium-Hard", "editions": [{"year": 2023}]},
        "safety_car": (60, "Monte Carlo has had safety cars in 3 of last 5 races"),
    }

    def _resolve(key: str):
        value = state[key]
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(module, "_load_race_data", lambda year, rnd: _resolve("race_data"))
    monkeypatch.setattr(module, "_get_historical_strategies", lambda location, year: _resolve("historical"))
    monkeypatch.setattr(module, "_calculate_safety_car_probability", lambda location, year: _resolve("safety_car"))
    return state


# ---------------------------------------------------------------------------
# _circuit_overview
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_overview_counts_how_many_cars_ran_each_strategy():
    overview = module._circuit_overview(_field())

    assert overview["strategy_distribution"] == {
        "1-stop (MEDIUM-HARD)": 2,
        "2-stop (SOFT-MEDIUM-HARD)": 1,
    }
    assert [driver["driver"] for driver in overview["drivers"]] == ["VER", "NOR", "LEC"]
    assert overview["drivers"][0] == {
        "driver": "VER",
        "strategy": "1-stop (MEDIUM-HARD)",
        "num_stops": 1,
        "first_stop_lap": 21,
    }


@pytest.mark.unit
def test_the_most_used_strategy_is_listed_first():
    laps = laps_frame(
        stint_rows("LEC", [("SOFT", 1, 14), ("MEDIUM", 15, 32), ("HARD", 33, 50)]),
        stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 22), ("HARD", 23, 50)]),
    )

    distribution = module._circuit_overview(laps)["strategy_distribution"]

    assert list(distribution) == ["1-stop (MEDIUM-HARD)", "2-stop (SOFT-MEDIUM-HARD)"]


@pytest.mark.unit
def test_the_first_stop_window_summarises_when_the_field_pitted():
    window = module._circuit_overview(_field())["first_stop_window"]

    # First stops on laps 15, 21 and 23.
    assert window == {"sample_size": 3, "p25": 18.0, "median": 21.0, "p75": 22.0}


@pytest.mark.unit
def test_the_stop_count_summary_reports_the_field_norm():
    summary = module._circuit_overview(_field())["stop_count_summary"]

    assert summary == {"sample_size": 3, "median": 1.0, "most_common": 1}


@pytest.mark.unit
def test_a_driver_who_never_pitted_still_appears_without_a_stop_lap():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 50)]))

    overview = module._circuit_overview(laps)

    assert overview["drivers"][0]["first_stop_lap"] is None
    assert overview["first_stop_window"] == {
        "sample_size": 0,
        "p25": None,
        "median": None,
        "p75": None,
    }
    assert overview["stop_count_summary"]["most_common"] == 0


@pytest.mark.unit
def test_drivers_without_stint_data_are_left_out_of_the_overview():
    rows = stint_rows("LAW", [("MEDIUM", 1, 10)])
    for row in rows:
        row["Stint"] = None
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]), rows)

    overview = module._circuit_overview(laps)

    assert [driver["driver"] for driver in overview["drivers"]] == ["VER"]
    assert overview["stop_count_summary"]["sample_size"] == 1


@pytest.mark.unit
def test_a_field_with_no_stint_data_summarises_nothing():
    rows = stint_rows("VER", [("MEDIUM", 1, 10)])
    for row in rows:
        row["Stint"] = None

    overview = module._circuit_overview(laps_frame(rows))

    assert overview["drivers"] == []
    assert overview["compound_summary"] == []
    assert overview["stop_count_summary"] == {"sample_size": 0, "median": None, "most_common": None}


@pytest.mark.unit
def test_the_overview_carries_a_per_compound_summary():
    summary = module._circuit_overview(_field())["compound_summary"]

    assert [row["compound"] for row in summary] == ["HARD", "MEDIUM", "SOFT"]
    assert next(row for row in summary if row["compound"] == "HARD")["sample_size"] == 3


# ---------------------------------------------------------------------------
# degrading sections
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_failing_history_lookup_degrades_to_a_placeholder(race):
    race["historical"] = RuntimeError("network down")

    assert module._historical_strategies_section("Monte Carlo", 2024) == {
        "dominant_strategy": "Data unavailable",
        "editions": [],
    }


@pytest.mark.unit
def test_a_failing_safety_car_lookup_degrades_to_a_neutral_fifty(race):
    race["safety_car"] = RuntimeError("network down")

    assert module._safety_car_section("Monte Carlo", 2024) == (
        50,
        "Unable to calculate safety car probability",
    )


@pytest.mark.unit
def test_working_lookups_are_passed_through_untouched(race):
    assert module._historical_strategies_section("Monte Carlo", 2024) == race["historical"]
    assert module._safety_car_section("Monte Carlo", 2024) == race["safety_car"]


# ---------------------------------------------------------------------------
# analyze_pit_strategy
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_race_without_data_returns_an_explicit_error(race):
    race["race_data"] = None

    result = module.analyze_pit_strategy(2026, 3)

    assert result["year"] == 2026
    assert result["round"] == 3
    assert "Race data not available for 2026 Round 3" in result["error"]
    assert "stints" not in result


@pytest.mark.unit
def test_without_a_driver_the_whole_field_is_summarised(race):
    result = module.analyze_pit_strategy(2024, 7)

    assert result["grand_prix"] == "Monaco Grand Prix"
    assert result["driver"] is None
    assert list(result["strategy_distribution"]) == ["1-stop (MEDIUM-HARD)", "2-stop (SOFT-MEDIUM-HARD)"]
    assert result["historical_strategies"] == race["historical"]
    assert result["safety_car_probability"] == 60
    assert result["safety_car_context"].startswith("Monte Carlo has had safety cars")
    assert "stints" not in result


@pytest.mark.unit
def test_naming_a_driver_returns_that_drivers_stints_and_stops(race):
    result = module.analyze_pit_strategy(2024, 7, "LEC")

    assert result["driver"] == "LEC"
    assert [stint["compound"] for stint in result["stints"]] == ["SOFT", "MEDIUM", "HARD"]
    assert [stop["lap"] for stop in result["pit_stops"]] == [15, 33]
    assert "strategy_distribution" not in result


@pytest.mark.unit
def test_a_named_driver_gets_an_undercut_analysis_against_their_neighbours(race):
    result = module.analyze_pit_strategy(2024, 7, "VER")

    assert result["undercut_overcut"] == [
        {"type": "undercut", "target_driver": "NOR", "lap": 21, "result": "gained position over NOR"}
    ]


@pytest.mark.unit
def test_an_unknown_driver_is_rejected_with_the_available_list(race):
    result = module.analyze_pit_strategy(2024, 7, "ZZZ")

    assert result["grand_prix"] == "Monaco Grand Prix"
    assert result["error"] == ("Driver 'ZZZ' not found in race data. Available: LEC, NOR, VER")
    assert "stints" not in result
    assert "historical_strategies" not in result


@pytest.mark.unit
def test_the_historical_sections_are_attached_to_a_driver_view_too(race):
    result = module.analyze_pit_strategy(2024, 7, "VER")

    assert result["historical_strategies"] == race["historical"]
    assert result["safety_car_probability"] == 60
