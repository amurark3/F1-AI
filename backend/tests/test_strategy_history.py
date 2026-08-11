"""Tests for app.data.strategy.history — previous editions of the same circuit.

Both numbers this module produces are quoted as circuit facts ("2-stop
Medium-Hard", "safety cars in 3 of last 5"), so the tests guard the ways a
plausible-looking number could be built from the wrong sample:

* **A season that cannot be loaded must not enter the denominator.** A race
  with no track-status column is unknowable, not safety-car-free.
* **Circuit naming drifts between seasons.** An exact location miss falls back
  to a substring match rather than silently dropping the edition.
* **Everything is cached per circuit.** A stale cache would pin a wrong answer
  for the process lifetime, so the cache key and its reuse are pinned too.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.strategy import history as module
from tests.strategy_fixture import FakeSession, laps_frame, results_frame, schedule_frame, stint_rows


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both lookups memoise per circuit for the process lifetime."""
    for cache in (module._historical_cache, module._safety_car_cache):
        cache.clear()
    yield
    for cache in (module._historical_cache, module._safety_car_cache):
        cache.clear()


def _stub_seasons(
    monkeypatch: pytest.MonkeyPatch,
    *,
    schedules: dict[int, object],
    races: dict[int, object] | None = None,
    sessions: dict[int, object] | None = None,
) -> dict[str, list]:
    """Serve a schedule, race data and session per season year.

    Any value may be an exception, which is raised instead of returned. Returns
    a record of what was asked for.
    """
    seen: dict[str, list] = {"schedules": [], "races": [], "sessions": []}

    def _resolve(mapping: dict | None, key: int, default=None):
        value = (mapping or {}).get(key, default)
        if isinstance(value, BaseException):
            raise value
        return value

    def _get_event_schedule(year: int, include_testing: bool):
        seen["schedules"].append(year)
        return _resolve(schedules, year, pd.DataFrame(columns=["RoundNumber", "Location"]))

    def _load_race_data(year: int, round_num: int):
        seen["races"].append((year, round_num))
        return _resolve(races, year)

    def _get_session(year: int, round_num: int, identifier: str):
        seen["sessions"].append((year, round_num, identifier))
        return _resolve(sessions, year)

    monkeypatch.setattr(module.fastf1, "get_event_schedule", _get_event_schedule)
    monkeypatch.setattr(module.fastf1, "get_session", _get_session)
    monkeypatch.setattr(module, "_load_race_data", _load_race_data)
    return seen


def _race(laps: pd.DataFrame, results: pd.DataFrame | None = None) -> dict:
    return {"laps": laps, "results": results if results is not None else results_frame([("VER", 1)])}


def _two_stop_field() -> pd.DataFrame:
    return laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 15), ("HARD", 16, 35), ("MEDIUM", 36, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 16), ("HARD", 17, 36), ("MEDIUM", 37, 50)]),
    )


# ---------------------------------------------------------------------------
# _round_for_location
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_exact_location_match_wins():
    schedule = schedule_frame([(1, "Sakhir"), (7, "Monte Carlo"), (12, "Budapest")])

    assert module._round_for_location(schedule, "Monte Carlo") == 7


@pytest.mark.unit
def test_a_renamed_circuit_is_found_by_substring():
    """The stored location drifts ("Monte Carlo" vs "Monte Carlo, Monaco")."""
    schedule = schedule_frame([(1, "Sakhir"), (7, "Monte Carlo, Monaco")])

    assert module._round_for_location(schedule, "Monte Carlo") == 7


@pytest.mark.unit
def test_a_circuit_absent_from_the_season_has_no_round():
    schedule = schedule_frame([(1, "Sakhir"), (7, "Monte Carlo")])

    assert module._round_for_location(schedule, "Imola") is None


# ---------------------------------------------------------------------------
# _compound_sequence and _dominant_strategy
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_stint_list_is_condensed_to_compound_initials():
    stints = [{"compound": "MEDIUM"}, {"compound": "HARD"}, {"compound": "MEDIUM"}]

    assert module._compound_sequence(stints) == "M-H-M"


@pytest.mark.unit
def test_the_dominant_strategy_expands_the_most_common_sequence():
    sequences = ["M-H", "M-H", "S-H-M"]
    stop_counts = [1, 1, 2]

    assert module._dominant_strategy(sequences, stop_counts) == "1-stop Medium-Hard"


@pytest.mark.unit
def test_an_unrecognised_compound_initial_is_left_as_written():
    assert module._dominant_strategy(["X-H"], [1]) == "1-stop X-Hard"


@pytest.mark.unit
def test_sequences_without_stop_counts_default_to_a_single_stop():
    assert module._dominant_strategy(["M-H"], []) == "1-stop Medium-Hard"


@pytest.mark.unit
def test_no_sequences_at_all_says_so_rather_than_guessing():
    assert module._dominant_strategy([], []) == "Insufficient historical data"


# ---------------------------------------------------------------------------
# _winner_strategy and _field_strategies
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_winner_strategy_names_the_compounds_and_stop_count():
    laps = _two_stop_field()

    assert module._winner_strategy(laps, results_frame([("NOR", 2), ("VER", 1)])) == "M-H-M (2 stops)"


@pytest.mark.unit
def test_a_one_stop_winner_is_described_in_the_singular():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 25), ("HARD", 26, 50)]))

    assert module._winner_strategy(laps, results_frame([("VER", 1)])) == "M-H (1 stop)"


@pytest.mark.unit
def test_a_race_without_results_has_an_unknown_winner_strategy():
    laps = _two_stop_field()

    assert module._winner_strategy(laps, None) == "Unknown"
    assert module._winner_strategy(laps, pd.DataFrame()) == "Unknown"


@pytest.mark.unit
def test_a_winner_with_no_stint_data_is_unknown():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 50)]))

    assert module._winner_strategy(laps, results_frame([("LAW", 1)])) == "Unknown"


@pytest.mark.unit
def test_field_strategies_collect_one_entry_per_driver_with_stints():
    stop_counts, sequences = module._field_strategies(_two_stop_field())

    assert stop_counts == [2, 2]
    assert sequences == ["M-H-M", "M-H-M"]


@pytest.mark.unit
def test_drivers_without_stint_data_are_left_out_of_the_field_summary():
    rows = stint_rows("LAW", [("MEDIUM", 1, 10)])
    for row in rows:
        row["Stint"] = None
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 25), ("HARD", 26, 50)]), rows)

    stop_counts, sequences = module._field_strategies(laps)

    assert stop_counts == [1]
    assert sequences == ["M-H"]


# ---------------------------------------------------------------------------
# _get_historical_strategies
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_last_three_editions_are_summarised_newest_first(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(7, "Monte Carlo")])
    seen = _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule, 2021: schedule},
        races={
            2023: _race(_two_stop_field()),
            2022: _race(_two_stop_field()),
            2021: _race(_two_stop_field()),
        },
    )

    result = module._get_historical_strategies("Monte Carlo", 2024)

    assert [edition["year"] for edition in result["editions"]] == [2023, 2022, 2021]
    assert result["editions"][0] == {"year": 2023, "winner_strategy": "M-H-M (2 stops)", "avg_stops": 2.0}
    assert result["dominant_strategy"] == "2-stop Medium-Hard-Medium"
    assert seen["races"] == [(2023, 7), (2022, 7), (2021, 7)]


@pytest.mark.unit
def test_a_season_missing_the_circuit_is_skipped(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={
            2023: schedule_frame([(7, "Monte Carlo")]),
            2022: schedule_frame([(1, "Sakhir")]),
            2021: schedule_frame([(7, "Monte Carlo")]),
        },
        races={2023: _race(_two_stop_field()), 2021: _race(_two_stop_field())},
    )

    result = module._get_historical_strategies("Monte Carlo", 2024)

    assert [edition["year"] for edition in result["editions"]] == [2023, 2021]
    assert seen["races"] == [(2023, 7), (2021, 7)]


@pytest.mark.unit
def test_an_edition_whose_race_data_will_not_load_is_skipped(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule, 2021: schedule},
        races={2023: _race(_two_stop_field()), 2022: None, 2021: None},
    )

    result = module._get_historical_strategies("Monte Carlo", 2024)

    assert [edition["year"] for edition in result["editions"]] == [2023]


@pytest.mark.unit
def test_a_season_that_raises_is_logged_and_skipped(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: RuntimeError("network down"), 2022: schedule, 2021: schedule},
        races={2022: _race(_two_stop_field()), 2021: _race(_two_stop_field())},
    )

    result = module._get_historical_strategies("Monte Carlo", 2024)

    assert [edition["year"] for edition in result["editions"]] == [2022, 2021]


@pytest.mark.unit
def test_an_edition_with_no_stint_data_reports_zero_average_stops(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = stint_rows("VER", [("MEDIUM", 1, 20)])
    for row in rows:
        row["Stint"] = None
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule_frame([(7, "Monte Carlo")])},
        races={2023: _race(laps_frame(rows))},
    )

    result = module._get_historical_strategies("Monte Carlo", 2024)

    assert result["editions"][0]["avg_stops"] == 0
    assert result["dominant_strategy"] == "Insufficient historical data"


@pytest.mark.unit
def test_a_circuit_with_no_loadable_history_says_so(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(monkeypatch, schedules={})

    result = module._get_historical_strategies("Imola", 2024)

    assert result == {"dominant_strategy": "Insufficient historical data", "editions": []}


@pytest.mark.unit
def test_a_repeat_request_is_served_from_the_cache(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2023: schedule_frame([(7, "Monte Carlo")])},
        races={2023: _race(_two_stop_field())},
    )

    first = module._get_historical_strategies("Monte Carlo", 2024)
    second = module._get_historical_strategies("Monte Carlo", 2024)

    assert first is second
    assert seen["races"] == [(2023, 7)]


# ---------------------------------------------------------------------------
# _had_safety_car
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("status", ["4", "6", "14", "2456"])
def test_any_lap_carrying_a_safety_car_code_marks_the_race(status: str):
    laps = pd.DataFrame({"TrackStatus": ["1", status, "1"]})

    assert module._had_safety_car(laps) is True


@pytest.mark.unit
def test_a_race_run_entirely_under_green_had_no_safety_car():
    laps = pd.DataFrame({"TrackStatus": ["1", "2", "1", None]})

    assert module._had_safety_car(laps) is False


# ---------------------------------------------------------------------------
# _calculate_safety_car_probability
# ---------------------------------------------------------------------------


def _sc_session(statuses: list[str]) -> FakeSession:
    return FakeSession(laps=pd.DataFrame({"TrackStatus": statuses, "LapNumber": range(len(statuses))}))


@pytest.mark.unit
def test_the_probability_is_the_share_of_editions_that_saw_a_safety_car(
    monkeypatch: pytest.MonkeyPatch,
):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule, 2021: schedule},
        sessions={
            2023: _sc_session(["1", "4"]),
            2022: _sc_session(["1", "1"]),
            2021: _sc_session(["1", "6"]),
        },
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert probability == 67
    assert context == "Monte Carlo has had safety cars in 2 of last 3 races"


@pytest.mark.unit
def test_a_race_without_track_status_is_left_out_of_the_sample(
    monkeypatch: pytest.MonkeyPatch,
):
    """Unknowable is not the same as safety-car-free."""
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule},
        sessions={
            2023: _sc_session(["1", "4"]),
            2022: FakeSession(laps=pd.DataFrame({"LapNumber": [1, 2]})),
        },
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert probability == 100
    assert context == "Monte Carlo has had safety cars in 1 of last 1 races"


@pytest.mark.unit
@pytest.mark.parametrize("laps", [None, pd.DataFrame()])
def test_an_edition_with_no_laps_is_skipped(monkeypatch: pytest.MonkeyPatch, laps):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule},
        sessions={2023: FakeSession(laps=laps), 2022: _sc_session(["1", "4"])},
    )

    probability, _ = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert probability == 100


@pytest.mark.unit
def test_only_exact_location_matches_are_sampled_for_safety_cars(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule_frame([(7, "Monte Carlo, Monaco")])},
        sessions={2023: _sc_session(["1", "4"])},
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert probability == 50
    assert context == "Insufficient data for Monte Carlo safety car history"


@pytest.mark.unit
def test_a_season_that_raises_is_skipped(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2023: schedule, 2022: schedule},
        sessions={2023: RuntimeError("session unavailable"), 2022: _sc_session(["1", "4"])},
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert probability == 100
    assert context == "Monte Carlo has had safety cars in 1 of last 1 races"


@pytest.mark.unit
def test_the_search_stops_at_the_2018_data_floor(monkeypatch: pytest.MonkeyPatch):
    """FastF1 lap data does not go back past 2018, so 2024 sees five editions."""
    schedule = schedule_frame([(7, "Monte Carlo")])
    years = range(2015, 2025)
    seen = _stub_seasons(
        monkeypatch,
        schedules=dict.fromkeys(years, schedule),
        sessions={year: _sc_session(["1", "4"]) for year in years},
    )

    _, context = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert context == "Monte Carlo has had safety cars in 5 of last 5 races"
    assert seen["schedules"] == [2023, 2022, 2021, 2020, 2019]


@pytest.mark.unit
def test_sampling_stops_once_enough_editions_have_been_read(
    monkeypatch: pytest.MonkeyPatch,
):
    """Far enough from the data floor, the eight-edition sample limit binds."""
    schedule = schedule_frame([(7, "Monte Carlo")])
    years = range(2020, 2040)
    seen = _stub_seasons(
        monkeypatch,
        schedules=dict.fromkeys(years, schedule),
        sessions={year: _sc_session(["1", "4"]) for year in years},
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2035)

    assert probability == 100
    assert context == "Monte Carlo has had safety cars in 8 of last 8 races"
    assert len(seen["sessions"]) == 8


@pytest.mark.unit
def test_a_circuit_with_no_assessable_history_reports_a_neutral_fifty(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_seasons(monkeypatch, schedules={})

    probability, context = module._calculate_safety_car_probability("Imola", 2024)

    assert probability == 50
    assert context == "Insufficient data for Imola safety car history"


@pytest.mark.unit
def test_the_safety_car_answer_is_cached_per_circuit(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2023: schedule_frame([(7, "Monte Carlo")])},
        sessions={2023: _sc_session(["1", "4"])},
    )

    first = module._calculate_safety_car_probability("Monte Carlo", 2024)
    second = module._calculate_safety_car_probability("Monte Carlo", 2024)

    assert first == second
    assert len(seen["sessions"]) == 1
