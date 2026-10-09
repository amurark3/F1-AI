"""Tests for app.data.f1db_results — session results read from local f1db.

These functions are the feature-engineering inputs for the race predictor, so a
wrong ordering here poisons the training set silently. The two position
semantics are the crux and are asserted explicitly:

* qualifying uses ``position_number`` — only classified runners,
* race and sprint use ``position_display_order`` — every entrant gets a rank,
  including a DNF, which is what the old FastF1 path produced.

Everything runs against a real seeded SQLite f1db so the SQL is exercised.
"""

from __future__ import annotations

import pytest

from app.data import f1db_results
from app.data.f1db_results import (
    driver_teams,
    qualifying_positions,
    race_results,
    race_retirements,
    race_schedule,
    sprint_positions,
)

# ---------------------------------------------------------------------------
# race_schedule
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_race_schedule_returns_rounds_in_order_keyed_by_circuit_id(fake_f1db):
    """``location`` is the stable circuit slug, not a display name — it is the
    join key for circuit-history features across seasons."""
    schedule = race_schedule(2026)

    assert schedule == [
        {"round": 1, "name": "Bahrain", "location": "bahrain"},
        {"round": 2, "name": "Monaco", "location": "monaco"},
        {"round": 3, "name": "Italy", "location": "monza"},
    ]


@pytest.mark.integration
def test_race_schedule_is_empty_for_a_season_not_in_the_dataset(fake_f1db):
    assert race_schedule(1997) == []


@pytest.mark.integration
def test_race_schedule_is_empty_when_the_dataset_has_no_races(empty_f1db):
    assert race_schedule(2026) == []


# ---------------------------------------------------------------------------
# qualifying_positions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_qualifying_positions_returns_the_classified_grid_order(fake_f1db):
    assert qualifying_positions(2026, 1) == {"VER": 1, "NOR": 2, "LEC": 3}


@pytest.mark.integration
def test_qualifying_positions_is_empty_for_a_round_with_no_session(fake_f1db):
    # 2026 round 3 is scheduled but not yet run.
    assert qualifying_positions(2026, 3) == {}


# ---------------------------------------------------------------------------
# race_results
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_race_results_ranks_a_retirement_instead_of_dropping_it(fake_f1db):
    """NOR retired (NULL ``position_number``) yet must still be classified 3rd —
    the predictor needs a finishing order for every starter."""
    assert race_results(2025, 1) == {"VER": 1, "LEC": 2, "NOR": 3}


@pytest.mark.integration
def test_race_results_differ_from_qualifying_for_the_same_weekend(fake_f1db):
    """Guards against the two queries accidentally selecting the same column."""
    assert race_results(2026, 1)["NOR"] == 3
    assert qualifying_positions(2026, 1)["NOR"] == 2


@pytest.mark.integration
def test_race_results_is_empty_for_an_unraced_round(fake_f1db):
    assert race_results(2026, 3) == {}


# ---------------------------------------------------------------------------
# sprint_positions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sprint_positions_returns_the_sprint_classification(fake_f1db):
    # 2026 round 1 is the one seeded sprint weekend: LEC beat VER.
    assert sprint_positions(2026, 1) == {"LEC": 1, "VER": 2}


@pytest.mark.integration
def test_sprint_positions_is_empty_on_a_non_sprint_weekend(fake_f1db):
    assert sprint_positions(2026, 2) == {}


# ---------------------------------------------------------------------------
# driver_teams
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_driver_teams_maps_every_race_entrant_to_its_constructor(fake_f1db):
    assert driver_teams(2025, 2) == {"VER": "Red Bull", "LEC": "Ferrari", "NOR": "McLaren"}


@pytest.mark.integration
def test_driver_teams_is_empty_for_a_round_without_a_race_result(fake_f1db):
    assert driver_teams(2026, 3) == {}


# ---------------------------------------------------------------------------
# race_retirements
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_race_retirements_gives_a_reason_only_for_the_drivers_who_retired(fake_f1db):
    """Finishers map to ``None``; the retirement cause is what feeds a driver's
    reliability profile."""
    assert race_retirements(2025, 1) == {"VER": None, "LEC": None, "NOR": "Engine"}


@pytest.mark.integration
def test_race_retirements_is_empty_for_an_unraced_round(fake_f1db):
    assert race_retirements(2026, 3) == {}


# ---------------------------------------------------------------------------
# _positions_by_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_position_queries_cover_exactly_the_two_supported_orderings():
    """The query map is the reason no identifier is ever interpolated into SQL —
    a third ordering would have to be added as a complete literal statement."""
    assert set(f1db_results._POSITION_QUERIES) == {"position_number", "position_display_order"}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("position_number", {"VER": 1, "LEC": 2}),
        ("position_display_order", {"VER": 1, "LEC": 2, "NOR": 3}),
    ],
    ids=["classified-only", "every-entrant"],
)
def test_positions_by_type_selects_the_requested_ordering(fake_f1db, column, expected):
    result = f1db_results._positions_by_type(2025, 1, "RACE_RESULT", column)

    assert result == expected
