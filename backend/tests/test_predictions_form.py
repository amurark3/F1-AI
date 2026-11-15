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

Circuit history and the grid-to-finish change are in
``test_predictions_circuit_history.py``.

f1db is a real seeded SQLite file here so the results SQL runs.
"""

from __future__ import annotations

import pytest

from app.data import f1db_results
from app.data.predictions import form as form_module
from app.data.predictions.form import (
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
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


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
