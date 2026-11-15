"""Tests for app.data.strategy.history — previous editions of the same circuit.

Both numbers this module produces are quoted as circuit facts ("2-stop
Medium-Hard", "safety car in 2 of 3 races since 2023"), so the tests guard the ways a
plausible-looking number could be built from the wrong sample:

* **A season that cannot be read must not enter the denominator.** A race
  OpenF1 cannot answer for is unknowable, not safety-car-free, and it is
  named in the answer and never cached as if it had been read.
* **Circuit naming drifts between seasons.** An exact location miss falls back
  to a substring match rather than silently dropping the edition.
* **Everything is cached per circuit.** A stale cache would pin a wrong answer
  for the process lifetime, so the cache key and its reuse are pinned too.
"""

from __future__ import annotations

from dataclasses import replace
import json
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from app.data.f1db_calendar import CalendarUnavailableError
from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.race_control import neutralised_windows
from app.data.strategy import history as module
from tests.roster_support import SAO_PAULO
from tests.strategy_fixture import laps_frame, results_frame, schedule_frame, stint_rows
from tests.strategy_openf1_support import race_session_laps

if TYPE_CHECKING:
    from app.data.openf1.session_laps import SessionLaps


@pytest.fixture(autouse=True)
def _no_fastf1(no_fastf1):
    """The pit-strategy history reads OpenF1 and f1db only."""


def _quiet_race() -> SessionLaps:
    """São Paulo 2026's race (R20): race control never deployed a safety car."""
    messages = json.loads((SAO_PAULO / "openf1_race_control_race.json").read_text())
    return replace(race_session_laps(), windows=neutralised_windows(messages))


def _safety_car_race() -> SessionLaps:
    """São Paulo 2025's race (R21): a safety car, then a virtual safety car."""
    return race_session_laps()


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
    """Serve a schedule, race data and OpenF1 race laps per season year.

    Any value may be an exception, which is raised instead of returned. Returns
    a record of what was asked for.
    """
    seen: dict[str, list] = {"schedules": [], "races": [], "sessions": []}

    def _resolve(mapping: dict | None, key: int, default=None):
        value = (mapping or {}).get(key, default)
        if isinstance(value, BaseException):
            raise value
        return value

    def _season_schedule(year: int):
        seen["schedules"].append(year)
        return _resolve(schedules, year, pd.DataFrame(columns=["RoundNumber", "Location"]))

    def _load_race_data(year: int, round_num: int):
        seen["races"].append((year, round_num))
        return _resolve(races, year)

    def _load_session_laps(year: int, round_num: int, code: str):
        seen["sessions"].append((year, round_num, code))
        return _resolve(sessions, year)

    monkeypatch.setattr(module, "season_schedule", _season_schedule)
    monkeypatch.setattr(module, "load_session_laps", _load_session_laps)
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
def test_a_winner_fastf1_sent_without_a_code_has_an_unknown_strategy():
    laps = _two_stop_field()
    results = pd.DataFrame([{"Abbreviation": float("nan"), "Position": 1.0}])

    assert module._winner_strategy(laps, results) == "Unknown"


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
        schedules={2025: schedule, 2024: schedule, 2023: schedule},
        races={
            2025: _race(_two_stop_field()),
            2024: _race(_two_stop_field()),
            2023: _race(_two_stop_field()),
        },
    )

    result = module._get_historical_strategies("Monte Carlo", 2026)

    assert [edition["year"] for edition in result["editions"]] == [2025, 2024, 2023]
    assert result["editions"][0] == {"year": 2025, "winner_strategy": "M-H-M (2 stops)", "avg_stops": 2.0}
    assert result["dominant_strategy"] == "2-stop Medium-Hard-Medium"
    assert result["missing_years"] == []
    assert seen["races"] == [(2025, 7), (2024, 7), (2023, 7)]


@pytest.mark.unit
def test_the_history_stops_at_openf1s_first_season(monkeypatch: pytest.MonkeyPatch):
    """Races before 2023 are not asked for: a cold FastF1 cache cannot load them."""
    schedule = schedule_frame([(7, "Monte Carlo")])
    seen = _stub_seasons(
        monkeypatch,
        schedules=dict.fromkeys(range(2018, 2026), schedule),
        races={year: _race(_two_stop_field()) for year in range(2018, 2026)},
    )

    result = module._get_historical_strategies("Monte Carlo", 2025)

    assert [edition["year"] for edition in result["editions"]] == [2024, 2023]
    assert seen["schedules"] == [2024, 2023]


@pytest.mark.unit
def test_a_season_missing_the_circuit_is_skipped_and_not_reported_missing(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={
            2025: schedule_frame([(7, "Monte Carlo")]),
            2024: schedule_frame([(1, "Sakhir")]),
            2023: schedule_frame([(7, "Monte Carlo")]),
        },
        races={2025: _race(_two_stop_field()), 2023: _race(_two_stop_field())},
    )

    result = module._get_historical_strategies("Monte Carlo", 2026)

    assert [edition["year"] for edition in result["editions"]] == [2025, 2023]
    assert result["missing_years"] == []
    assert seen["races"] == [(2025, 7), (2023, 7)]


@pytest.mark.unit
def test_an_edition_whose_race_data_will_not_load_is_reported_missing_and_not_cached(
    monkeypatch: pytest.MonkeyPatch,
):
    schedule = schedule_frame([(7, "Monte Carlo")])
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule, 2024: schedule, 2023: schedule},
        races={2025: _race(_two_stop_field()), 2024: None, 2023: None},
    )

    result = module._get_historical_strategies("Monte Carlo", 2026)
    module._get_historical_strategies("Monte Carlo", 2026)

    assert [edition["year"] for edition in result["editions"]] == [2025]
    assert result["missing_years"] == [2024, 2023]
    assert module._historical_cache == {}
    assert len(seen["races"]) == 6


@pytest.mark.unit
def test_a_season_the_calendar_cannot_list_is_reported_missing(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(7, "Monte Carlo")])
    _stub_seasons(
        monkeypatch,
        schedules={2025: CalendarUnavailableError("no 2025"), 2024: schedule, 2023: schedule},
        races={2024: _race(_two_stop_field()), 2023: _race(_two_stop_field())},
    )

    result = module._get_historical_strategies("Monte Carlo", 2026)

    assert [edition["year"] for edition in result["editions"]] == [2024, 2023]
    assert result["missing_years"] == [2025]


@pytest.mark.unit
def test_an_edition_with_no_stint_data_reports_zero_average_stops(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = stint_rows("VER", [("MEDIUM", 1, 20)])
    for row in rows:
        row["Stint"] = None
    _stub_seasons(
        monkeypatch,
        schedules={2025: schedule_frame([(7, "Monte Carlo")])},
        races={2025: _race(laps_frame(rows))},
    )

    result = module._get_historical_strategies("Monte Carlo", 2026)

    assert result["editions"][0]["avg_stops"] == 0
    assert result["dominant_strategy"] == "Insufficient historical data"


@pytest.mark.unit
def test_a_circuit_with_no_history_says_so(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(monkeypatch, schedules={})

    result = module._get_historical_strategies("Imola", 2026)

    assert result == {"dominant_strategy": "Insufficient historical data", "editions": [], "missing_years": []}


@pytest.mark.unit
def test_a_repeat_request_is_served_from_the_cache(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule_frame([(7, "Monte Carlo")])},
        races={2025: _race(_two_stop_field())},
    )

    first = module._get_historical_strategies("Monte Carlo", 2026)
    second = module._get_historical_strategies("Monte Carlo", 2026)

    assert first is second
    assert seen["races"] == [(2025, 7)]


# ---------------------------------------------------------------------------
# _race_had_safety_car
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_race_with_a_safety_car_window_had_one(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(monkeypatch, schedules={}, sessions={2025: _safety_car_race()})

    assert module._race_had_safety_car(2025, 21) is True


@pytest.mark.unit
def test_a_virtual_safety_car_alone_counts(monkeypatch: pytest.MonkeyPatch):
    race = _safety_car_race()
    virtual_only = replace(race, windows=tuple(w for w in race.windows if w.kind == "vsc"))
    _stub_seasons(monkeypatch, schedules={}, sessions={2025: virtual_only})

    assert module._race_had_safety_car(2025, 21) is True


@pytest.mark.unit
def test_a_race_that_stayed_green_had_none(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(monkeypatch, schedules={}, sessions={2026: _quiet_race()})

    assert module._race_had_safety_car(2026, 20) is False


@pytest.mark.unit
def test_a_red_flag_alone_is_not_a_safety_car(monkeypatch: pytest.MonkeyPatch):
    red_only = replace(race_session_laps(), windows=(replace(_safety_car_race().windows[0], kind="red"),))
    _stub_seasons(monkeypatch, schedules={}, sessions={2025: red_only})

    assert module._race_had_safety_car(2025, 21) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "race", [None, OpenF1UnavailableError("429 Retry-After 30"), "no laps"], ids=["unmatched", "unavailable", "no-laps"]
)
def test_a_race_that_cannot_be_read_is_unknown_not_quiet(monkeypatch: pytest.MonkeyPatch, race):
    if race == "no laps":
        race = replace(_quiet_race(), laps=())
    _stub_seasons(monkeypatch, schedules={}, sessions={2025: race})

    assert module._race_had_safety_car(2025, 21) is None


# ---------------------------------------------------------------------------
# _calculate_safety_car_probability
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_probability_is_the_share_of_races_since_2023_that_saw_a_safety_car(
    monkeypatch: pytest.MonkeyPatch,
):
    schedule = schedule_frame([(21, "São Paulo")])
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule, 2024: schedule, 2023: schedule},
        sessions={2025: _safety_car_race(), 2024: _quiet_race(), 2023: _safety_car_race()},
    )

    probability, context = module._calculate_safety_car_probability("São Paulo", 2026)

    assert probability == 67
    assert context == "São Paulo had a safety car or virtual safety car in 2 of 3 races since 2023 (2023, 2024, 2025)"
    assert seen["sessions"] == [(2025, 21, "R"), (2024, 21, "R"), (2023, 21, "R")]


@pytest.mark.unit
def test_a_single_race_sample_is_worded_in_the_singular(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(
        monkeypatch, schedules={2025: schedule_frame([(21, "São Paulo")])}, sessions={2025: _safety_car_race()}
    )

    probability, context = module._calculate_safety_car_probability("São Paulo", 2026)

    assert probability == 100
    assert context == "São Paulo had a safety car or virtual safety car in 1 of 1 race since 2023 (2025)"


@pytest.mark.unit
def test_the_search_stops_at_2023_where_openf1_begins(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(21, "São Paulo")])
    years = range(2015, 2026)
    seen = _stub_seasons(
        monkeypatch,
        schedules=dict.fromkeys(years, schedule),
        sessions={year: _safety_car_race() for year in years},
    )

    _, context = module._calculate_safety_car_probability("São Paulo", 2026)

    assert "3 of 3 races since 2023" in context
    assert seen["schedules"] == [2025, 2024, 2023]


@pytest.mark.unit
def test_a_race_that_cannot_be_read_is_named_not_counted_and_the_answer_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
):
    schedule = schedule_frame([(21, "São Paulo")])
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule, 2024: schedule, 2023: schedule},
        sessions={2025: _safety_car_race(), 2024: OpenF1UnavailableError("live"), 2023: _quiet_race()},
    )

    probability, context = module._calculate_safety_car_probability("São Paulo", 2026)
    module._calculate_safety_car_probability("São Paulo", 2026)

    assert probability == 50
    assert context == (
        "São Paulo had a safety car or virtual safety car in 1 of 2 races since 2023 (2023, 2025); "
        "2024 could not be read"
    )
    assert module._safety_car_cache == {}
    assert len(seen["sessions"]) == 6


@pytest.mark.unit
def test_a_season_the_calendar_cannot_list_is_named_as_unread(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(21, "São Paulo")])
    _stub_seasons(
        monkeypatch,
        schedules={2025: CalendarUnavailableError("no 2025"), 2024: schedule, 2023: schedule},
        sessions={2024: _safety_car_race(), 2023: _safety_car_race()},
    )

    probability, context = module._calculate_safety_car_probability("São Paulo", 2026)

    assert probability == 100
    assert context.endswith("2 of 2 races since 2023 (2023, 2024); 2025 could not be read")


@pytest.mark.unit
def test_only_exact_location_matches_are_sampled_for_safety_cars(
    monkeypatch: pytest.MonkeyPatch,
):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule_frame([(7, "Monte Carlo, Monaco")])},
        sessions={2025: _safety_car_race()},
    )

    probability, context = module._calculate_safety_car_probability("Monte Carlo", 2026)

    assert probability == 50
    assert context == "Insufficient data for Monte Carlo safety car history (no race since 2023 could be read)"
    assert seen["sessions"] == []
    # Nothing was unreadable, only absent, so the answer stands.
    assert "Monte Carlo" in module._safety_car_cache


@pytest.mark.unit
def test_the_safety_car_answer_is_cached_per_circuit(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2025: schedule_frame([(21, "São Paulo")])},
        sessions={2025: _safety_car_race()},
    )

    first = module._calculate_safety_car_probability("São Paulo", 2026)
    second = module._calculate_safety_car_probability("São Paulo", 2026)

    assert first == second
    assert len(seen["sessions"]) == 1
