"""Tests for driver form signals (app.data.predictions.form).

Form is the signal that must agree between training and serving. The training
pipeline accumulates a season chronologically; this module queries it live. If
the two disagree — by a round, by a window length, by which source they read —
the model is served a feature distribution it never saw, and the resulting
error is invisible because every number still looks plausible.

What the assertions guard:

* **No leakage.** Recent form and sprint form may only see rounds *strictly
  before* the one being predicted. Including the current round would feed the
  model the result it is being asked to predict.
* **The rolling window is exactly five races**, and a driver with barely any
  history is padded from last season rather than scored on one race.
* **Circuit history follows the calendar, not the round number.** Rounds move
  between seasons (Miami added, China returning), so "round 6 last year" is a
  different race — the lookup is by location, and a venue that was not on a past
  calendar contributes nothing rather than the wrong race.
* **A pit-lane start never counts as a 19-place gain**, which would otherwise
  dominate a circuit's overtaking average.

f1db is a real seeded SQLite file here so the results SQL runs; FastF1 is mocked
at ``get_session``/``get_event_schedule`` because those are network loads.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data import f1db_results
from app.data.predictions import form as form_module
from app.data.predictions.form import (
    _find_round_for_location,
    _finish_positions,
    _grid_to_finish_deltas,
    _load_circuit_history,
    _load_grid_to_finish_delta,
    _load_recent_form,
    _load_recent_sprint_form,
    _season_race_positions,
)

# In the seeded database every round finishes VER P1, LEC P2, NOR P3 (retired
# but classified), across 2025 rounds 1-2 and 2026 rounds 1-2.
CIRCUIT = "monza"


@pytest.fixture(autouse=True)
def _clear_caches():
    """Every lookup in this module memoises for the process lifetime."""
    caches = (
        form_module._season_results_cache,
        form_module._recent_form_cache,
        form_module._recent_sprint_form_cache,
        form_module._circuit_history_cache,
        form_module._grid_delta_cache,
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


class _FakeSession:
    """A loaded FastF1 race session whose classification is scripted."""

    def __init__(self, results: pd.DataFrame | None) -> None:
        self.results = results

    def load(self, **_kwargs: object) -> None:
        return None


@pytest.fixture
def fastf1_calendar(monkeypatch):
    """Script the event schedule per season and the race session per (year, round).

    Returns the two mutable dicts plus the request log, so a test can assert
    *which* race was loaded — the thing calendar drift gets wrong.
    """
    schedules: dict[int, pd.DataFrame] = {}
    races: dict[tuple[int, int], object] = {}
    loaded: list[tuple[int, int]] = []

    def _get_event_schedule(year: int, include_testing: bool = True):
        value = schedules.get(year)
        if value is None:
            raise ValueError(f"no schedule for {year}")
        if isinstance(value, Exception):
            raise value
        return value

    def _get_session(year: int, round_num: int, name: str):
        loaded.append((year, round_num))
        value = races.get((year, round_num))
        if isinstance(value, Exception):
            raise value
        return value if value is not None else _FakeSession(results=None)

    monkeypatch.setattr(form_module.fastf1, "get_event_schedule", _get_event_schedule)
    monkeypatch.setattr(form_module.fastf1, "get_session", _get_session)
    return {"schedules": schedules, "races": races, "loaded": loaded}


def _schedule(**round_by_location: int) -> pd.DataFrame:
    return pd.DataFrame([{"Location": location, "RoundNumber": rnd} for location, rnd in round_by_location.items()])


def _results(**position_by_code: int) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Abbreviation": code, "Position": pos, "GridPosition": pos} for code, pos in position_by_code.items()]
    )


# ---------------------------------------------------------------------------
# Season results from f1db
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_season_maps_each_raced_round_to_its_finishing_order(fake_f1db):
    positions = _season_race_positions(2026)

    # Round 3 is scheduled but unraced, so it contributes no entry at all — an
    # empty round would otherwise read as a race where nobody finished.
    assert sorted(positions) == [1, 2]
    assert positions[1] == {"VER": 1, "LEC": 2, "NOR": 3}


@pytest.mark.integration
def test_a_season_is_queried_from_f1db_only_once(fake_f1db, monkeypatch):
    first = _season_race_positions(2026)

    def _explode(year):
        raise AssertionError("the season was re-queried instead of served from cache")

    monkeypatch.setattr(f1db_results, "race_schedule", _explode)

    assert _season_race_positions(2026) is first


@pytest.mark.unit
def test_an_f1db_outage_yields_an_empty_season_rather_than_failing_the_prediction(monkeypatch):
    def _fail(year):
        raise RuntimeError("f1db unavailable")

    monkeypatch.setattr(f1db_results, "race_schedule", _fail)

    assert _season_race_positions(2026) == {}


# ---------------------------------------------------------------------------
# Recent form
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_recent_form_only_sees_rounds_before_the_one_being_predicted(fake_f1db):
    before_round_three = _load_recent_form("VER", 2026, 3)

    # 2026 rounds 1 and 2 only. Round 3 is what is being predicted.
    assert before_round_three == [1, 1]


@pytest.mark.integration
def test_a_driver_with_a_single_result_this_season_is_padded_from_last_year(fake_f1db):
    # One race is not a form read; scoring a driver on it would swing wildly.
    assert _load_recent_form("VER", 2026, 2) == [1, 1, 1]


@pytest.mark.integration
def test_round_one_of_a_season_falls_back_entirely_to_the_previous_one(fake_f1db):
    assert _load_recent_form("LEC", 2026, 1) == [2, 2]


@pytest.mark.integration
def test_a_driver_who_has_never_raced_has_no_form_at_all(fake_f1db):
    # The scorer turns this into the midfield default rather than a P1 guess.
    assert _load_recent_form("ZZZ", 2026, 3) == []


@pytest.mark.unit
def test_only_the_last_five_races_count_toward_recent_form(monkeypatch):
    season = {rnd: {"VER": rnd} for rnd in range(1, 10)}
    monkeypatch.setattr(form_module, "_season_race_positions", lambda year: season if year == 2026 else {})

    # A driver's form is his current car and current run of results, so a race
    # eight rounds ago must not still be voting.
    assert _load_recent_form("VER", 2026, 9) == [4, 5, 6, 7, 8]


@pytest.mark.unit
def test_padding_from_last_season_is_also_capped_at_five_races(monkeypatch):
    previous = {rnd: {"VER": rnd} for rnd in range(1, 10)}
    monkeypatch.setattr(form_module, "_season_race_positions", lambda year: previous if year == 2025 else {})

    assert _load_recent_form("VER", 2026, 1) == [5, 6, 7, 8, 9]


@pytest.mark.integration
def test_recent_form_is_computed_once_per_driver_and_round(fake_f1db):
    first = _load_recent_form("VER", 2026, 3)

    assert _load_recent_form("VER", 2026, 3) is first


# ---------------------------------------------------------------------------
# Sprint form
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sprint_form_reports_earlier_sprints_of_this_season_in_order(fake_f1db):
    # The seeded season runs one sprint, at round 1: LEC won it from VER.
    assert _load_recent_sprint_form(2026, 3) == {"LEC": [1], "VER": [2]}


@pytest.mark.integration
def test_the_current_weekends_sprint_is_not_folded_into_sprint_form(fake_f1db):
    # It is fed separately as the sprint_position feature; counting it twice
    # would double-weight the strongest signal in the model.
    assert _load_recent_sprint_form(2026, 1) == {}


@pytest.mark.integration
def test_a_season_with_no_sprints_yet_reports_nothing_rather_than_zeroes(fake_f1db):
    assert _load_recent_sprint_form(2025, 3) == {}


@pytest.mark.integration
def test_sprint_form_queries_the_season_once_and_re_filters_per_round(fake_f1db, monkeypatch):
    _load_recent_sprint_form(2026, 3)

    def _explode(year):
        raise AssertionError("the sprint season was re-queried instead of re-filtered")

    monkeypatch.setattr(f1db_results, "race_schedule", _explode)

    assert _load_recent_sprint_form(2026, 2) == {"LEC": [1], "VER": [2]}


@pytest.mark.unit
def test_an_f1db_outage_costs_the_sprint_signal_not_the_prediction(monkeypatch):
    def _fail(year):
        raise RuntimeError("f1db unavailable")

    monkeypatch.setattr(f1db_results, "race_schedule", _fail)

    assert _load_recent_sprint_form(2026, 3) == {}


# ---------------------------------------------------------------------------
# Calendar lookup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_venue_is_found_by_location_whatever_round_it_was_held_at(fastf1_calendar):
    fastf1_calendar["schedules"][2024] = _schedule(bahrain=1, miami=6, monza=16)

    assert _find_round_for_location(2024, "Monza") == 16


@pytest.mark.unit
def test_a_venue_absent_from_that_season_calendar_has_no_round(fastf1_calendar):
    # Imola dropped, Las Vegas not yet added: neither may resolve to a
    # neighbouring race just because the round number exists.
    fastf1_calendar["schedules"][2024] = _schedule(bahrain=1, monza=16)

    assert _find_round_for_location(2024, "imola") is None


@pytest.mark.unit
def test_a_schedule_that_cannot_be_fetched_yields_no_round(fastf1_calendar):
    fastf1_calendar["schedules"][2024] = ConnectionError("fastf1 schedule unreachable")

    assert _find_round_for_location(2024, CIRCUIT) is None


# ---------------------------------------------------------------------------
# Result-frame parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_finish_positions_drop_rows_that_cannot_identify_a_driver_or_a_place():
    frame = pd.DataFrame(
        [
            {"Abbreviation": "VER", "Position": 1},
            {"Abbreviation": "LEC", "Position": "2"},  # numeric string from the source
            {"Abbreviation": "", "Position": 3},  # no driver code
            {"Abbreviation": "NOR", "Position": None},  # entered, never classified
            {"Abbreviation": "HUL", "Position": "DNF"},  # unparsable placeholder
        ]
    )

    # Every dropped row is missing data, not a failure: the rest of the race
    # still contributes to this driver's circuit history.
    assert _finish_positions(frame) == {"VER": 1, "LEC": 2}


@pytest.mark.unit
def test_grid_delta_is_positive_when_a_driver_gains_places():
    frame = pd.DataFrame(
        [
            {"Abbreviation": "VER", "GridPosition": 5, "Position": 1},
            {"Abbreviation": "LEC", "GridPosition": 2, "Position": 6},
        ]
    )

    assert _grid_to_finish_deltas(frame) == {"VER": 4, "LEC": -4}


@pytest.mark.unit
def test_a_pit_lane_start_is_excluded_from_the_overtaking_average():
    frame = pd.DataFrame(
        [
            {"Abbreviation": "VER", "GridPosition": 0, "Position": 3},  # pit-lane start
            {"Abbreviation": "LEC", "GridPosition": 4, "Position": 2},
        ]
    )

    # A pit-lane start scored against grid 0 would look like a 3-place *loss*
    # and drag the circuit's whole overtaking average with it.
    assert _grid_to_finish_deltas(frame) == {"LEC": 2}


@pytest.mark.unit
def test_grid_deltas_drop_rows_missing_either_end_of_the_comparison():
    frame = pd.DataFrame(
        [
            {"Abbreviation": "", "GridPosition": 1, "Position": 1},
            {"Abbreviation": "NOR", "GridPosition": None, "Position": 4},
            {"Abbreviation": "PIA", "GridPosition": 4, "Position": None},
            {"Abbreviation": "HUL", "GridPosition": "back", "Position": 9},
        ]
    )

    assert _grid_to_finish_deltas(frame) == {}


# ---------------------------------------------------------------------------
# Circuit history
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_circuit_history_reads_the_last_three_editions_of_that_venue(fastf1_calendar):
    for year, rnd in ((2025, 16), (2024, 14), (2023, 15)):
        fastf1_calendar["schedules"][year] = _schedule(monza=rnd)
        fastf1_calendar["races"][(year, rnd)] = _FakeSession(_results(VER=1, LEC=2))

    history = _load_circuit_history(2026, 5, CIRCUIT)

    assert history == {"VER": [1, 1, 1], "LEC": [2, 2, 2]}
    # The venue moved around the calendar; loading "round 5" each year would
    # have read three entirely different Grands Prix.
    assert fastf1_calendar["loaded"] == [(2025, 16), (2024, 14), (2023, 15)]


@pytest.mark.unit
def test_a_season_where_the_venue_was_not_raced_contributes_nothing(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(_results(VER=1))
    fastf1_calendar["schedules"][2024] = _schedule(bahrain=1)  # venue off the calendar
    fastf1_calendar["schedules"][2023] = _schedule(monza=15)
    fastf1_calendar["races"][(2023, 15)] = _FakeSession(_results(VER=3))

    assert _load_circuit_history(2026, 5, CIRCUIT) == {"VER": [1, 3]}
    assert (2024, 1) not in fastf1_calendar["loaded"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scripted", "case"),
    [
        pytest.param(None, "session_with_no_results_attribute", id="no_results"),
        pytest.param(pd.DataFrame(), "session_loaded_but_empty", id="empty_results"),
    ],
)
def test_an_edition_with_no_classification_is_skipped(fastf1_calendar, scripted, case):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(scripted)
    fastf1_calendar["schedules"][2024] = _schedule(monza=14)
    fastf1_calendar["races"][(2024, 14)] = _FakeSession(_results(VER=2))

    assert _load_circuit_history(2026, 5, CIRCUIT) == {"VER": [2]}, case


@pytest.mark.unit
def test_one_failed_session_load_does_not_lose_the_other_editions(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = TimeoutError("fastf1 session load timed out")
    fastf1_calendar["schedules"][2024] = _schedule(monza=14)
    fastf1_calendar["races"][(2024, 14)] = _FakeSession(_results(VER=2))

    assert _load_circuit_history(2026, 5, CIRCUIT) == {"VER": [2]}


@pytest.mark.unit
def test_circuit_history_is_loaded_once_per_venue_and_season(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(_results(VER=1))

    first = _load_circuit_history(2026, 5, CIRCUIT)

    # Three FastF1 race loads per driver per request is the cost this avoids.
    assert _load_circuit_history(2026, 9, CIRCUIT) is first
    # Only 2025 has a calendar registered here, so 2024 and 2023 resolve to no
    # round and are skipped — the point is that the second call loads nothing.
    assert fastf1_calendar["loaded"] == [(2025, 16)]


# ---------------------------------------------------------------------------
# Grid-to-finish delta
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_grid_delta_averages_a_drivers_places_gained_across_editions(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(
        pd.DataFrame([{"Abbreviation": "HAM", "GridPosition": 10, "Position": 4}])
    )
    fastf1_calendar["schedules"][2024] = _schedule(monza=14)
    fastf1_calendar["races"][(2024, 14)] = _FakeSession(
        pd.DataFrame([{"Abbreviation": "HAM", "GridPosition": 8, "Position": 6}])
    )

    assert _load_grid_to_finish_delta(2026, 5, CIRCUIT) == {"HAM": 4.0}


@pytest.mark.unit
def test_a_driver_who_loses_places_here_gets_a_negative_delta(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(
        pd.DataFrame(
            [
                {"Abbreviation": "OVERTAKER", "GridPosition": 12, "Position": 5},
                {"Abbreviation": "SLIPPER", "GridPosition": 3, "Position": 9},
            ]
        )
    )

    deltas = _load_grid_to_finish_delta(2026, 5, CIRCUIT)

    # The scorer subtracts this term, so a driver who goes backwards here must
    # never score better than one who comes through the field.
    assert deltas["SLIPPER"] < 0 < deltas["OVERTAKER"]


@pytest.mark.unit
def test_a_venue_missing_from_a_past_calendar_is_skipped_for_deltas(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(bahrain=1)
    fastf1_calendar["schedules"][2024] = _schedule(monza=14)
    fastf1_calendar["races"][(2024, 14)] = _FakeSession(
        pd.DataFrame([{"Abbreviation": "HAM", "GridPosition": 10, "Position": 4}])
    )

    assert _load_grid_to_finish_delta(2026, 5, CIRCUIT) == {"HAM": 6.0}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scripted", "case"),
    [
        pytest.param(None, "session_with_no_results", id="no_results"),
        pytest.param(pd.DataFrame(), "session_loaded_but_empty", id="empty_results"),
        pytest.param(TimeoutError("load timed out"), "session_load_failed", id="failed"),
    ],
)
def test_an_unusable_edition_leaves_the_delta_map_empty_rather_than_raising(fastf1_calendar, scripted, case):
    for year, rnd in ((2025, 16), (2024, 14), (2023, 15)):
        fastf1_calendar["schedules"][year] = _schedule(monza=rnd)
        fastf1_calendar["races"][(year, rnd)] = scripted if isinstance(scripted, Exception) else _FakeSession(scripted)

    assert _load_grid_to_finish_delta(2026, 5, CIRCUIT) == {}, case


@pytest.mark.unit
def test_grid_deltas_are_loaded_once_per_venue(fastf1_calendar):
    fastf1_calendar["schedules"][2025] = _schedule(monza=16)
    fastf1_calendar["races"][(2025, 16)] = _FakeSession(
        pd.DataFrame([{"Abbreviation": "HAM", "GridPosition": 10, "Position": 4}])
    )

    first = _load_grid_to_finish_delta(2026, 5, CIRCUIT)

    assert _load_grid_to_finish_delta(2027, 8, CIRCUIT) is first
