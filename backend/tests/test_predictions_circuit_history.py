"""Circuit history and grid-to-finish change, read from f1db by circuit id.

The rows are real (``tests/circuit_history_support``): the 2023-2025 Brazilian and
Las Vegas Grands Prix, the editions the R20 and R21 calls read. Nothing here can
reach FastF1: the module no longer imports it, and ``fastf1`` is poisoned below
so a stray load would fail the test.
"""

from __future__ import annotations

import pytest

from app.data import f1db_results
from app.data.predictions import form as form_module
from app.data.predictions.compute import _load_event_context
from app.data.predictions.form import circuit_editions

BRAZIL = "interlagos"
LAS_VEGAS = "las-vegas"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    form_module._circuit_editions_cache.clear()
    import fastf1

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("FastF1 must not be requested")

    monkeypatch.setattr(fastf1, "get_session", _forbidden)
    monkeypatch.setattr(fastf1, "get_event_schedule", _forbidden)
    yield
    form_module._circuit_editions_cache.clear()


@pytest.mark.integration
def test_the_r20_call_reads_three_brazilian_editions_from_f1db(circuit_history_f1db):
    editions = circuit_editions(2026, BRAZIL)

    assert editions.missing == {}
    # Verstappen: won from pole (2023), won from 17th (2024), 3rd from the pit lane (2025).
    # Newest edition first, as the FastF1 path listed them.
    assert editions.history["VER"] == [3, 1, 1]
    assert editions.history["NOR"] == [1, 6, 2]
    assert editions.history["OCO"][1] == 2


@pytest.mark.integration
def test_grid_deltas_are_the_mean_places_gained_with_pit_lane_starts_left_out(circuit_history_f1db):
    deltas = circuit_editions(2026, BRAZIL).deltas

    # 2023: 1 -> 1 (0); 2024: 17 -> 1 (+16); the 2025 pit-lane start holds no slot and is not counted.
    assert deltas["VER"] == 8.0
    # 2025: 1 -> 1 (0); 2024: 1 -> 6 (-5); 2023: 6 -> 2 (+4).
    assert deltas["NOR"] == pytest.approx(-1 / 3)


@pytest.mark.integration
def test_the_r21_call_reads_three_las_vegas_editions(circuit_history_f1db):
    editions = circuit_editions(2026, LAS_VEGAS)

    assert editions.missing == {}
    assert len(editions.history["VER"]) == 3


@pytest.mark.integration
def test_editions_f1db_does_not_have_are_reported_missing_with_a_reason(circuit_history_f1db):
    # 2024's last three seasons are 2023, 2022 and 2021; the capture holds Interlagos 2023 only.
    editions = circuit_editions(2024, BRAZIL)

    assert editions.history["VER"] == [1]
    assert editions.missing == {
        2022: "f1db has no Grand Prix at this circuit that season",
        2021: "f1db has no Grand Prix at this circuit that season",
    }


@pytest.mark.integration
def test_a_circuit_f1db_never_raced_is_all_missing_and_not_remembered(circuit_history_f1db):
    editions = circuit_editions(2026, "sepang")

    assert (editions.history, editions.deltas) == ({}, {})
    assert sorted(editions.missing) == [2023, 2024, 2025]
    assert not form_module._circuit_editions_cache


@pytest.mark.integration
def test_a_race_without_results_is_missing_not_empty(circuit_history_f1db):
    # 2026 R21 is on the calendar but has no result rows yet: reading 2027 sees it as the newest edition.
    editions = circuit_editions(2027, LAS_VEGAS)

    assert editions.missing == {2026: "f1db has no race result for round 21"}
    assert len(editions.history["VER"]) == 2


@pytest.mark.integration
def test_a_complete_answer_is_read_once(circuit_history_f1db, monkeypatch):
    first = circuit_editions(2026, BRAZIL)
    monkeypatch.setattr(form_module, "race_schedule", lambda _year: pytest.fail("read f1db twice"))

    assert circuit_editions(2026, BRAZIL) is first


@pytest.mark.unit
def test_an_unreadable_f1db_is_reported_and_retried_not_cached_as_empty(monkeypatch):
    calls = []

    def _broken(year):
        calls.append(year)
        raise RuntimeError("f1db is being replaced")

    monkeypatch.setattr(form_module, "race_schedule", _broken)

    editions = circuit_editions(2026, BRAZIL)

    assert editions.history == {}
    assert editions.missing[2025] == "f1db could not be read: f1db is being replaced"
    assert sorted(editions.missing) == [2023, 2024, 2025]
    circuit_editions(2026, BRAZIL)
    assert len(calls) == 6


@pytest.mark.unit
def test_the_first_season_bounds_how_far_back_editions_go(circuit_history_f1db):
    assert sorted(circuit_editions(2019, BRAZIL).missing) == [2018]


@pytest.mark.integration
def test_the_computes_circuit_key_is_f1dbs_circuit_id(calendar_f1db):
    assert _load_event_context(2026, 19).circuit_key == "mexico-city"
    assert _load_event_context(2026, 16).circuit_key == "sepang"


@pytest.mark.unit
def test_race_results_is_the_source_of_finishing_positions():
    # The history uses the same helper as training, so serving and training agree on every position.
    assert form_module.race_results is f1db_results.race_results
