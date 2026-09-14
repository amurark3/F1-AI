"""Tests for grid resolution and its provenance (app.services.race_grid).

The behaviour under test: what the payload is allowed to claim depends on which
source answered. f1db publishes a round's grid sheet only once the round is
complete, so between the end of qualifying and that release the best available
order is the qualifying classification — which is *not* the grid, because no
penalty has been applied to it. Serving that silently under a "starting grid"
heading is the failure this module exists to prevent.
"""

import asyncio

import pytest

from app.api.routers import race_control as race_control_router
from app.api.routers.race_control import get_starting_grid
from app.data import predictions
from app.data.f1db_grid import GridSlot
from app.services import race_grid
from app.services.race_grid import (
    PROVISIONAL_WARNING,
    SOURCE_NONE,
    SOURCE_OFFICIAL_GRID,
    SOURCE_QUALIFYING,
    build_starting_grid,
)


def slot(code, position, qualifying, **overrides):
    return GridSlot(
        driver_code=code,
        driver_name=f"{code} Driver",
        team="Alpine",
        position=position,
        qualifying_position=qualifying,
        penalty_positions=overrides.get("penalty_positions"),
        start_from_back=overrides.get("start_from_back", False),
        pit_lane=overrides.get("pit_lane", False),
    )


@pytest.fixture
def sources(monkeypatch):
    """Stub both grid sources; each test sets only the one it is exercising."""
    state = {"official": (), "qualifying": None}
    monkeypatch.setattr(race_grid, "starting_grid", lambda year, rnd: state["official"])
    monkeypatch.setattr(race_grid, "load_qualifying", lambda year, rnd: state["qualifying"])
    return state


def test_published_grid_is_served_as_authoritative(sources):
    sources["official"] = (slot("GAS", 1, 1), slot("PIA", 6, 3, penalty_positions=3))

    payload = build_starting_grid(2026, 13)

    assert payload["source"] == SOURCE_OFFICIAL_GRID
    assert (payload["available"], payload["provisional"]) == (True, False)
    assert [row["driver_code"] for row in payload["grid"]] == ["GAS", "PIA"]


def test_penalties_list_holds_only_the_sanctioned_drivers(sources):
    sources["official"] = (
        slot("GAS", 1, 1),
        slot("PIA", 6, 3, penalty_positions=3),
        slot("LAW", None, 14, pit_lane=True),
    )

    payload = build_starting_grid(2026, 13)

    assert [row["driver_code"] for row in payload["penalties"]] == ["PIA", "LAW"]
    assert payload["penalties"][0]["places_lost"] == 3
    # The offence is not in f1db, so the payload says where the number came from.
    assert payload["warnings"] == [race_grid.PENALTY_SOURCE_NOTE]


def test_clean_round_reports_no_penalties_and_no_warning(sources):
    sources["official"] = (slot("GAS", 1, 1), slot("RUS", 2, 2))

    payload = build_starting_grid(2026, 12)

    assert payload["penalties"] == []
    assert payload["warnings"] == []


def test_qualifying_stands_in_before_the_grid_sheet_is_published(sources):
    sources["qualifying"] = [
        {"driver_code": "VER", "driver_name": "Max Verstappen", "team": "Red Bull", "position": 1},
    ]

    payload = build_starting_grid(2026, 14)

    assert payload["source"] == SOURCE_QUALIFYING
    assert (payload["available"], payload["provisional"]) == (True, True)
    assert payload["warnings"] == [PROVISIONAL_WARNING]


def test_provisional_rows_claim_no_penalty_state(sources):
    sources["qualifying"] = [
        {"driver_code": "VER", "driver_name": "Max Verstappen", "team": "Red Bull", "position": 1},
    ]

    row = build_starting_grid(2026, 14)["grid"][0]

    # Absent, not zero: nothing here has been checked against a grid sheet, and
    # a zero would read as "penalty checked, none applied".
    assert row["penalty_positions"] is None
    assert row["places_lost"] is None
    assert row["penalised"] is False
    assert build_starting_grid(2026, 14)["penalties"] == []


def test_provisional_row_falls_back_to_the_driver_code_for_a_missing_name(sources):
    sources["qualifying"] = [{"driver_code": "VER", "position": 1}]

    row = build_starting_grid(2026, 14)["grid"][0]

    assert row["driver_name"] == "VER"
    assert row["team"] == ""


def test_published_grid_wins_over_qualifying(sources):
    sources["official"] = (slot("PIA", 6, 3, penalty_positions=3),)
    sources["qualifying"] = [{"driver_code": "PIA", "position": 3}]

    assert build_starting_grid(2026, 13)["source"] == SOURCE_OFFICIAL_GRID


def test_no_grid_before_qualifying_has_run(sources):
    payload = build_starting_grid(2026, 20)

    assert (payload["available"], payload["source"]) == (False, SOURCE_NONE)
    assert payload["grid"] == []
    assert payload["warnings"] == [race_grid.UNAVAILABLE_REASON]


def test_empty_qualifying_result_is_not_treated_as_a_grid(sources):
    sources["qualifying"] = []

    assert build_starting_grid(2026, 20)["available"] is False


class TestGridRoute:
    """The HTTP boundary: a failing source must not leak, and must not lie.

    An error envelope keeps ``available: False`` so a caller that renders the
    grid from the payload shows "no grid" rather than an empty starting line-up
    presented as fact.
    """

    def test_serves_the_resolved_grid(self, monkeypatch):
        monkeypatch.setattr(
            race_control_router, "build_starting_grid", lambda year, rnd: {"grid": ["row"], "available": True}
        )

        assert asyncio.run(get_starting_grid(2026, 13)) == {"grid": ["row"], "available": True}

    def test_a_failing_source_reports_no_grid_rather_than_an_empty_one(self, monkeypatch):
        def _boom(year, rnd):
            raise RuntimeError("no such column: race_data.starting_grid_position_grid_penalty")

        monkeypatch.setattr(race_control_router, "build_starting_grid", _boom)

        payload = asyncio.run(get_starting_grid(2026, 13))

        assert (payload["available"], payload["grid"], payload["penalties"]) == (False, [], [])
        assert "starting_grid_position_grid_penalty" not in str(payload)


def test_load_qualifying_exposes_the_cached_classification(monkeypatch):
    """The provisional source reuses the prediction module's cached session load."""
    monkeypatch.setattr(predictions, "_load_qualifying", lambda year, rnd: [{"driver_code": "VER"}])

    assert predictions.load_qualifying(2026, 14) == [{"driver_code": "VER"}]
