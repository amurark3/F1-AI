"""Tests for grid resolution and its provenance (app.services.race_grid).

The behaviour under test: what the payload is allowed to claim depends on which
source answered. f1db publishes a round's grid sheet only once the round is
complete, so between the end of qualifying and that release the best available
order is the qualifying classification — which is *not* the grid, because no
penalty has been applied to it. Serving that silently under a "starting grid"
heading is the failure this module exists to prevent.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.api.routers import race_control as race_control_router
from app.api.routers.race_control import get_starting_grid
from app.data import jolpica, predictions
from app.data.canonical_names import CODE_UNRESOLVED
from app.data.f1db_grid import GridSlot
from app.data.jolpica import JolpicaUnavailableError
from app.data.predictions import sessions as prediction_sessions
from app.services import race_grid
from app.services.race_grid import (
    PROVISIONAL_WARNING,
    SOURCE_NONE,
    SOURCE_OFFICIAL_GRID,
    SOURCE_QUALIFYING,
    build_starting_grid,
)
from tests.fia_documents_support import MEXICO_2026, held, hold
from tests.sao_paulo_2026_support import add_camara_to_f1db, r20_openf1_qualifying

FIXTURES = Path(__file__).parent / "fixtures"


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
    state = {"official": (), "qualifying": None, "jolpica": None}

    def jolpica(year, rnd):
        if state["jolpica"] is None:
            raise JolpicaUnavailableError("not stubbed")
        return state["jolpica"]

    monkeypatch.setattr(race_grid, "provisional_grid", jolpica)
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


def test_the_fia_grid_attaches_each_cars_rulings_to_f1dbs_sheet(sources, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)
    sources["official"] = (slot("GAS", 9, 9), slot("VER", 5, 4, penalty_positions=1))

    payload = build_starting_grid(2026, 19)

    rows = {row["driver_code"]: row for row in payload["grid"]}
    assert rows["VER"]["reasons"] == [
        {"ruling": "1 place grid penalty", "reason": "Causing a collision", "document": 33}
    ]
    assert rows["GAS"]["reasons"] == []
    assert (payload["source"], payload["fia_document"]["number"]) == (SOURCE_OFFICIAL_GRID, 67)
    # The offence is known, so the "f1db has no offence" note goes.
    assert payload["warnings"] == []


def test_before_f1db_the_fia_final_grid_answers_with_every_reason(sources, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    payload = build_starting_grid(2026, 19)

    assert (payload["source"], payload["provisional"], payload["warnings"]) == (race_grid.SOURCE_FIA_GRID, False, [])
    assert payload["fia_document"] == {
        "number": 67,
        "final": True,
        "url": MEXICO_2026["Doc 67 - Final Starting Grid"]["url"],
    }
    assert [row["driver_code"] for row in payload["grid"][:5]] == ["HAM", "RUS", "LEC", "ANT", "VER"]
    assert len(payload["grid"]) == 22
    penalties = {row["driver_code"]: row for row in payload["penalties"]}
    assert list(penalties) == ["VER", "BOT", "LAW"]
    facts = ("position", "qualifying_position", "penalty_positions", "places_lost", "pit_lane")
    assert [tuple(penalties[code][fact] for fact in facts) for code in penalties] == [
        (5, 4, 1, 1, False),
        # Last of the 21 who qualified: fifty places cost nothing.
        (21, 21, 50, 0, False),
        # Disqualified from qualifying, then sent to the pit lane.
        (None, None, 1, None, True),
    ]
    assert [reason["document"] for reason in penalties["LAW"]["reasons"]] == [58, 34, 65]
    assert penalties["BOT"]["reasons"][0]["reason"] == "Additional power unit elements have been used"


def test_a_provisional_fia_grid_is_labelled_provisional(sources, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held(title) for title in MEXICO_2026 if title != "Doc 67 - Final Starting Grid"])

    payload = build_starting_grid(2026, 19)

    assert (payload["source"], payload["provisional"]) == (race_grid.SOURCE_FIA_GRID, True)
    assert payload["warnings"] == [race_grid.FIA_PROVISIONAL_WARNING]
    lawson = payload["grid"][-1]
    # Before the parc fermé decision, Lawson still held slot 22.
    assert (lawson["driver_code"], lawson["position"], lawson["pit_lane"]) == ("LAW", 22, False)


def test_an_fia_grid_without_its_qualifying_classification_knows_no_places_lost(sources, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [held("Doc 67 - Final Starting Grid"), held("Doc 37 - Revised Entry List")])

    rows = {row["driver_code"]: row for row in build_starting_grid(2026, 19)["grid"]}

    assert (rows["VER"]["qualifying_position"], rows["VER"]["places_lost"]) == (None, None)


def test_qualifying_stands_in_before_the_grid_sheet_is_published(sources):
    sources["qualifying"] = [
        {"driver_code": "VER", "driver_name": "Max Verstappen", "team": "Red Bull", "position": 1},
    ]

    payload = build_starting_grid(2026, 14)

    assert payload["source"] == SOURCE_QUALIFYING
    assert (payload["available"], payload["provisional"]) == (True, True)
    assert payload["warnings"] == [PROVISIONAL_WARNING]


def test_the_provisional_warning_does_not_claim_the_sheet_is_unpublished():
    """Only that our dataset lacks it — the one thing the code actually knows.

    A missing grid means f1db has not released the round *or* this server is
    reading an old release. The warning used to assert the first, and production
    showed it for five rounds whose sheets had long been published, while the
    real cause — a dataset stuck on round 11 — went unnoticed.
    """
    assert "not been published" not in PROVISIONAL_WARNING
    assert "dataset" in PROVISIONAL_WARNING


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


@pytest.mark.integration
def test_the_r20_provisional_grid_prints_f1dbs_code_for_a_qualifier_sent_without_a_code(sources, identity_f1db):
    add_camara_to_f1db(identity_f1db)
    sources["qualifying"] = r20_openf1_qualifying(camara_coded=False)

    grid = build_starting_grid(2026, 20)["grid"]

    assert (grid[12]["position"], grid[12]["driver_code"], grid[12]["driver_name"]) == (13, "CAM", "Rafael Câmara")
    assert not any(row[CODE_UNRESOLVED] for row in grid)
    assert "nan" not in {row["driver_code"].lower() for row in grid}


@pytest.mark.integration
def test_the_r20_provisional_grid_keeps_and_labels_a_qualifier_no_source_can_code(sources, identity_f1db):
    """Production's f1db on qualifying day (v2026.19.0) did not know Câmara yet."""
    sources["qualifying"] = r20_openf1_qualifying(camara_coded=False)

    grid = build_starting_grid(2026, 20)["grid"]

    assert len(grid) == 22
    assert (grid[12]["position"], grid[12]["driver_code"], grid[12]["driver_name"]) == (13, "", "Rafael Camara")
    assert [row["position"] for row in grid if row[CODE_UNRESOLVED]] == [13]
    assert "nan" not in {row["driver_code"].lower() for row in grid}


def test_published_grid_rows_carry_the_same_label_unset(sources):
    sources["official"] = (slot("GAS", 1, 1),)

    assert build_starting_grid(2026, 13)["grid"][0][CODE_UNRESOLVED] is False


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
    monkeypatch.setattr(prediction_sessions, "_load_qualifying", lambda year, rnd: [{"driver_code": "VER"}])

    assert predictions.load_qualifying(2026, 14) == [{"driver_code": "VER"}]


def test_jolpica_qualifying_is_the_provisional_grid_when_f1db_has_none(sources, monkeypatch):
    """Sao Paulo 2026: Jolpica's real qualifying table, read through the real client code."""
    qualifying = json.loads((FIXTURES / "sao_paulo_2026_r20" / "jolpica_qualifying.json").read_text())
    monkeypatch.setattr(jolpica, "_race_rows", lambda *args: qualifying["QualifyingResults"])
    monkeypatch.setattr(race_grid, "provisional_grid", jolpica.provisional_grid)
    sources["qualifying"] = [{"driver_code": "ZZZ", "position": 1}]

    payload = build_starting_grid(2026, 20)

    assert (payload["available"], payload["provisional"], payload["source"]) == (True, True, SOURCE_QUALIFYING)
    assert payload["source_detail"] == jolpica.QUALIFYING_SOURCE
    assert payload["warnings"] == [PROVISIONAL_WARNING]
    assert [row["position"] for row in payload["grid"]] == list(range(1, 23))
    assert payload["grid"][0]["driver_code"] == "NOR"
    assert payload["grid"][12]["driver_code"] == "CAM"
    assert payload["penalties"] == []


def test_the_published_qualifying_order_still_answers_when_jolpica_cannot(sources):
    sources["qualifying"] = [{"driver_code": "VER", "driver_name": "Max Verstappen", "team": "Red Bull", "position": 1}]

    payload = build_starting_grid(2026, 14)

    assert (payload["provisional"], payload["source_detail"]) == (True, "openf1-qualifying")
