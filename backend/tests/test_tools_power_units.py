"""Tests for the AI Engineer's power-unit tool.

The tool is fed the real payload built from the fixture corpus, so what the
model reads is what the screen shows.
"""

from __future__ import annotations

import pytest

from app.api.tools import TOOL_MAP, power_units as tool_module
from app.data.f1db_grid import GridSlot
from app.data.power_units.status import OUTCOME_OK, IngestStatus
from app.services.power_units import clear_cache, provenance, report
from tests.power_units_support import allowance_entries, corpus, season_context

GRIDS = {13: (GridSlot("LAW", "Liam Lawson", "Red Bull", None, 14, 35, False, True),)}


@pytest.fixture(autouse=True)
def wired(monkeypatch):
    clear_cache()
    monkeypatch.setattr(report, "load_season", lambda year: corpus())
    monkeypatch.setattr(report, "load_season_context", lambda year: season_context())
    monkeypatch.setattr(report, "starting_grid", lambda year, round_num: GRIDS.get(round_num, ()))
    monkeypatch.setattr(report, "load_allowances", lambda year: allowance_entries())
    monkeypatch.setattr(
        provenance, "load_status", lambda year: IngestStatus(year, "2026-10-24T08:17:00+00:00", OUTCOME_OK)
    )
    yield
    clear_cache()


def run(**args) -> str:
    return TOOL_MAP["get_power_unit_usage"].invoke(args)


def test_the_tool_is_registered():
    assert "get_power_unit_usage" in TOOL_MAP


def test_without_a_driver_it_returns_the_season_table():
    text = run(year=2026)
    assert text.startswith("### Power-unit usage — 2026")
    assert "Allowance per car: ICE 4 · TC 4 · EXH 4 · MGU-K 3 · ES 3 · PU-CE 3 · PU-ANC 6" in text
    assert "| #6 | Isack Hadjar (HAD) | Red Bull | 7/4 | 6/4 | 6/4 | 4/3 | 4/3 | 4/3 | 7/6 | 35 grid places |" in text
    assert "| #14 | Fernando Alonso (ALO) | Aston Martin |" in text
    assert "1 pit-lane start(s)" in text
    assert "1 decision(s) pending" in text  # Lindblad's sixth engine at Austin
    assert "| none |" in text


@pytest.mark.parametrize("driver", ["Hadjar", "had", "6", "isack-hadjar"])
def test_a_driver_can_be_named_by_surname_code_number_or_id(driver):
    text = run(driver=driver, year=2026)
    assert text.startswith("### #6 Isack Hadjar (HAD) — Red Bull, 2026")


def test_the_detail_names_the_stand_in_and_what_each_round_cost():
    text = run(driver="Hadjar", year=2026)
    assert "Also raced by Liam Lawson (LAW) at round(s) 13 — their units count against this car." in text
    assert "| ICE | 7 | 4 | 3 |" in text
    assert "PU grid penalties: 35 grid places." in text
    monza = next(line for line in text.splitlines() if line.startswith("- R13"))
    assert "(driven by Liam Lawson (LAW))" in monza
    assert "new ICE #6 (beyond allowance)" in monza
    assert "stewards: drop of 35 grid places (Doc 41 - Infringement - Car 30 - Change to PU elements)" in monza
    assert "qualified P14, started from the pit lane" in monza


def test_pending_and_pit_lane_outcomes_read_in_words():
    lindblad = run(driver="LIN", year=2026)
    assert "stewards' decision not published yet" in lindblad
    alonso = run(driver="Alonso", year=2026)
    assert "stewards: pit-lane start" in alonso


def test_a_started_grid_slot_reads_as_a_position(monkeypatch):
    monkeypatch.setattr(
        report, "starting_grid", lambda year, round_num: (GridSlot("RUS", "R", "M", 22, 6, 40, False, False),)
    )
    assert "qualified P6, started P22" in run(driver="Russell", year=2026)


def test_an_unmatched_driver_says_so():
    assert "No 2026 car matches 'Senna'" in run(driver="Senna", year=2026)


def test_an_unavailable_season_returns_its_reason():
    assert "have not been read from its regulations yet" in run(year=2019)


def test_the_season_defaults_to_the_current_one(monkeypatch):
    seen = []
    monkeypatch.setattr(
        tool_module, "build_power_units", lambda year: seen.append(year) or {"available": False, "reason": "x"}
    )
    run()
    assert seen
    assert seen[0] >= 2026


def test_a_failure_reaches_the_model_without_its_details(monkeypatch):
    def explode(year):
        raise RuntimeError("postgres://secret-host:5432 refused")

    monkeypatch.setattr(tool_module, "build_power_units", explode)
    text = run(year=2026)
    assert "unavailable right now" in text
    assert "secret-host" not in text


def test_the_model_is_told_how_fresh_the_data_is(monkeypatch):
    assert "FIA documents last checked 2026-10-24T08:17:00+00:00." in run(year=2026)
    monkeypatch.setattr(
        provenance, "load_status", lambda year: IngestStatus(year, "2026-01-01T00:00:00+00:00", OUTCOME_OK)
    )
    clear_cache()
    assert "more than a day old" in run(driver="HAD", year=2026)
    monkeypatch.setattr(provenance, "load_status", lambda year: None)
    clear_cache()
    assert "last checked is not recorded" in run(year=2026)


def test_an_allowance_not_stored_yet_reads_as_unknown(monkeypatch):
    monkeypatch.setattr(report, "load_allowances", lambda year: {})
    clear_cache()
    assert "Allowance per car: ICE ? · TC ?" in run(year=2026)
    assert "| ICE | 7 | ? | 0 |" in run(driver="HAD", year=2026)


def test_a_drivers_own_car_comes_before_the_one_they_stood_in_for():
    text = run(driver="Lawson", year=2026)
    assert text.index("### #30 Liam Lawson") < text.index("### #6 Isack Hadjar")


def test_a_pit_lane_starter_without_a_qualifying_position_reads_plainly(monkeypatch):
    unplaced = GridSlot("LAW", "Liam Lawson", "Red Bull", None, None, 35, False, True)
    monkeypatch.setattr(report, "starting_grid", lambda year, round_num: (unplaced,) if round_num == 13 else ())
    clear_cache()
    monza = next(line for line in run(driver="HAD", year=2026).splitlines() if line.startswith("- R13"))
    assert monza.endswith("; started from the pit lane")
    assert "PNone" not in monza
