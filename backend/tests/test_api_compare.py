"""Tests for app.api.compare — season-long head-to-head between two drivers.

The comparison walks every round of a season out of f1db, so the tests run
against the seeded database rather than mocking the queries: the head-to-head
counting is the logic under test, and it is only meaningful over real rows.

The seeded season has VER winning every round with LEC second and NOR retiring,
so the expected tallies are known exactly. The properties that matter:

* a driver is found by code **or** by a substring of their name — the chat tool
  and the UI both pass free text here;
* a round with no result is skipped rather than counted as a draw, so an
  unraced future round cannot dilute the average;
* a driver who did not finish is absent from that round's comparison instead of
  being scored as a loss at a made-up position.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import compare as compare_module
from app.api.compare import _build_comparison_sync


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(compare_module.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# _build_comparison_sync — the actual comparison logic, over real f1db rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_head_to_head_counts_every_completed_round(fake_f1db):
    result = _build_comparison_sync(2026, "VER", "LEC")

    # Two rounds have results in 2026; VER wins both on track and in qualifying.
    assert result["race_h2h"] == {"d1": 2, "d2": 0}
    assert result["qualifying_h2h"] == {"d1": 2, "d2": 0}


@pytest.mark.integration
def test_average_race_position_is_computed_from_scored_rounds_only(fake_f1db):
    result = _build_comparison_sync(2026, "VER", "LEC")

    assert result["avg_race_position"] == {"d1": 1.0, "d2": 2.0}


@pytest.mark.integration
def test_only_rounds_with_results_appear(fake_f1db):
    """2026 round 3 is scheduled but unraced — it must not show up as a draw."""
    result = _build_comparison_sync(2026, "VER", "LEC")

    assert [r["round"] for r in result["rounds"]] == [1, 2]


@pytest.mark.integration
def test_drivers_are_found_by_name_substring_as_well_as_code(fake_f1db):
    by_code = _build_comparison_sync(2026, "VER", "LEC")
    by_name = _build_comparison_sync(2026, "verstappen", "leclerc")

    assert by_name["driver1"]["code"] == by_code["driver1"]["code"]
    assert by_name["driver2"]["code"] == by_code["driver2"]["code"]


@pytest.mark.integration
def test_driver_lookup_is_case_insensitive_and_trims_whitespace(fake_f1db):
    result = _build_comparison_sync(2026, "  ver  ", "Leclerc")

    assert result["driver1"]["code"] == "VER"


@pytest.mark.integration
def test_driver_payload_carries_the_standings_summary(fake_f1db):
    result = _build_comparison_sync(2026, "VER", "LEC")

    assert result["driver1"]["name"] == "Verstappen"
    assert result["driver1"]["position"] == 1
    assert result["driver1"]["points"] == 50.0


@pytest.mark.integration
def test_the_tally_is_symmetric_when_the_drivers_are_swapped(fake_f1db):
    """Swapping the arguments must mirror the result, not change who won."""
    forward = _build_comparison_sync(2026, "VER", "LEC")
    reversed_ = _build_comparison_sync(2026, "LEC", "VER")

    assert reversed_["race_h2h"] == {"d1": 0, "d2": forward["race_h2h"]["d1"]}
    assert reversed_["qualifying_h2h"] == {"d1": 0, "d2": forward["qualifying_h2h"]["d1"]}
    assert reversed_["avg_race_position"]["d1"] == forward["avg_race_position"]["d2"]


@pytest.mark.integration
def test_a_test_driver_only_entrant_is_not_comparable(fake_f1db):
    """NOR's only 2026 entry is a test-driver row, so they are not in the standings.

    Comparing against them has to fail as "not found" rather than silently
    matching a driver who never raced the season.
    """
    result = _build_comparison_sync(2026, "VER", "NOR")

    assert "Could not find driver" in result["error"]


@pytest.mark.integration
def test_an_unknown_driver_is_reported_rather_than_guessed(fake_f1db):
    result = _build_comparison_sync(2026, "VER", "hamilton")

    assert "Could not find driver" in result["error"]


@pytest.mark.integration
def test_a_season_with_no_standings_is_reported(fake_f1db):
    result = _build_comparison_sync(1998, "VER", "LEC")

    assert result["error"] == "No standings data for 1998"


@pytest.mark.integration
def test_an_empty_database_reports_missing_standings(empty_f1db):
    result = _build_comparison_sync(2026, "VER", "LEC")

    assert "No standings data" in result["error"]


# ---------------------------------------------------------------------------
# The HTTP handler
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_endpoint_returns_the_comparison(client, fake_f1db):
    body = client.get("/compare/2026/VER/LEC").json()

    assert body["driver1"]["code"] == "VER"
    assert body["race_h2h"] == {"d1": 2, "d2": 0}


@pytest.mark.unit
def test_endpoint_reports_a_timeout_without_an_error_id(client, monkeypatch):
    """A slow data source is a retry-able condition, not a server fault."""

    def timeout(*_args, **_kwargs):
        # On 3.10 asyncio.TimeoutError is distinct from the builtin, and the
        # handler catches the asyncio one specifically.
        raise asyncio.TimeoutError

    monkeypatch.setattr(compare_module, "_build_comparison_sync", timeout)

    body = client.get("/compare/2026/VER/LEC").json()

    assert body == {"error": "Comparison timed out. Try again."}


@pytest.mark.unit
def test_endpoint_returns_a_client_safe_error_on_failure(client, monkeypatch):
    def explode(*_args, **_kwargs):
        raise ValueError("no such column: race_data.position_display_order")

    monkeypatch.setattr(compare_module, "_build_comparison_sync", explode)

    response = client.get("/compare/2026/VER/LEC")
    body = response.json()

    assert response.status_code == 200
    assert "error_id" in body
    # The SQLite message names internal schema and must not reach the client.
    assert "position_display_order" not in str(body)


@pytest.mark.unit
def test_comparison_shares_the_fastf1_timeout_budget():
    assert compare_module.FASTF1_TIMEOUT == compare_module.FASTF1_TIMEOUT_SECONDS
