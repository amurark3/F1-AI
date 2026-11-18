"""Tests for the sprint, sprint-qualifying and qualifying chat tools (app.api.tools.sessions).

None reads FastF1: every table comes from f1db, or OpenF1's ``session_result`` until f1db holds the
round, and says which. The rows are real:

* ``fixtures/f1db_session_tools``: f1db v2026.20.0's Mexico City 2026 qualifying (Lawson disqualified)
  and China 2026 sprint qualifying.
* ``fixtures/f1db_race_results``: China's sprint, with Hülkenberg, Bottas and Lindblad out.
* ``fixtures/mexico_2026_r19``: OpenF1's qualifying ``session_result`` and entry list.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.tools import sessions as module
from app.api.tools.sessions import get_qualifying_results, get_sprint_qualifying_results, get_sprint_results
from app.data import qualifying_times as times_module, race_classification
from app.data.qualifying_times import QualifyingTimes
from app.services import race_results
from tests.fastf1_guard import no_fastf1  # noqa: F401
from tests.openf1_support import make_session, serve

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_fastf1")]

MEXICO = Path(__file__).parent / "fixtures" / "mexico_2026_r19"


def _round(monkeypatch: pytest.MonkeyPatch, number: int) -> None:
    monkeypatch.setattr(module, "resolve_round", lambda _year, _name: number)


def _no_openf1(monkeypatch: pytest.MonkeyPatch) -> None:
    for owner in (times_module, race_results):
        monkeypatch.setattr(owner, "openf1_session_result", lambda *_args: ([], {}))


def test_mexico_qualifying_reads_f1dbs_segments_fastest_first(qualifying_f1db, monkeypatch):
    _round(monkeypatch, 19)

    table = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    assert "*(Source: the FIA final classification)*" in table
    assert "### Q1 Results (Mexico 2026)" in table
    assert "### Q3 Results (Pole Position)" in table
    q3 = table.split("### Q3 Results (Pole Position)")[1]
    assert q3.splitlines()[3].startswith("| 1 | Lewis Hamilton (HAM) | Ferrari | 1:16.514 |")
    assert "| 2 | George Russell (RUS) | Mercedes | 1:16.523 |" in q3


def test_a_disqualified_car_keeps_its_times_and_reads_dsq(qualifying_f1db, monkeypatch):
    """Lawson has no place and no Q1; f1db keeps his Q2 and Q3 times, which the table labels."""
    _round(monkeypatch, 19)

    table = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    lawson = [line for line in table.splitlines() if "Liam Lawson" in line]
    assert len(lawson) == 2
    assert all(line.endswith("(DSQ) |") for line in lawson)
    assert "1:17.207 (DSQ)" in lawson[0]


def test_china_sprint_qualifying_reads_sq1_sq2_sq3(qualifying_f1db, monkeypatch):
    _round(monkeypatch, 2)

    table = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "China"})

    assert "### SQ1 Results (China 2026)" in table
    assert "### SQ3 Results (Sprint Pole Position)" in table
    assert "| 1 | George Russell (RUS) | Mercedes | 1:31.520 |" in table
    assert table.count("\n---\n") == 2


def test_openf1_answers_a_qualifying_f1db_does_not_hold_yet_and_says_provisional(race_results_f1db, monkeypatch):
    _round(monkeypatch, 19)
    session_result = json.loads((MEXICO / "openf1_session_result_qualifying.json").read_text())
    drivers = json.loads((MEXICO / "openf1_drivers_qualifying.json").read_text())
    monkeypatch.setattr(race_classification, "find_session", lambda *_args: make_session("Q"))
    serve(monkeypatch, race_classification, {"session_result": session_result, "drivers": drivers})

    table = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Mexico"})

    assert "*(Source: OpenF1, provisional until the FIA final classification is published)*" in table
    q3 = table.split("### Q3 Results (Pole Position)")[1]
    assert q3.splitlines()[3].startswith("| 1 | Lewis Hamilton (HAM)")
    assert "1:16.514" in q3.splitlines()[3]
    assert "| NC |" not in table  # a car OpenF1 left unplaced still carries its times, labelled
    assert "(NC)" in table


def test_a_session_with_no_segment_times_lists_the_order_and_says_so(monkeypatch):
    _round(monkeypatch, 2)
    cars = tuple(
        times_module.QualifyingCar(code, name, "Mercedes", position, (None, None, None), None if position else "DSQ")
        for code, name, position in (("RUS", "George Russell", 1), ("ANT", "Kimi Antonelli", None))
    )
    monkeypatch.setattr(module, "qualifying_times", lambda *_args: QualifyingTimes("f1db", True, cars))

    table = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "China"})

    assert "*(Detailed SQ1/SQ2/SQ3 split data currently unavailable)*" in table
    assert "| 1 | George Russell (RUS) | Mercedes | - |" in table
    assert "| DSQ | Kimi Antonelli (ANT) | Mercedes | - |" in table


def test_a_qualifying_no_source_holds_says_so(monkeypatch):
    _round(monkeypatch, 19)
    monkeypatch.setattr(module, "qualifying_times", lambda *_args: None)

    assert "No qualifying results are published for Mexico 2026" in get_qualifying_results.invoke(
        {"year": 2026, "grand_prix": "Mexico"}
    )
    assert "No sprint qualifying results are published" in get_sprint_qualifying_results.invoke(
        {"year": 2026, "grand_prix": "Mexico"}
    )


def test_a_failure_is_reported_not_raised(monkeypatch):
    def refuse(_year, _name):
        raise ValueError("No 2026 Grand Prix matches 'Nowhere'")

    monkeypatch.setattr(module, "resolve_round", refuse)
    args = {"year": 2026, "grand_prix": "Nowhere"}

    assert (
        get_qualifying_results.invoke(args)
        == "Failed to fetch qualifying results: No 2026 Grand Prix matches 'Nowhere'"
    )
    assert get_sprint_qualifying_results.invoke(args).startswith("Could not fetch Sprint Qualifying.")
    assert get_sprint_results.invoke(args) == "Could not fetch Sprint results: No 2026 Grand Prix matches 'Nowhere'"


def test_china_sprint_reads_f1db_with_retirements_as_dnf_and_a_reason(race_results_f1db, monkeypatch):
    _round(monkeypatch, 2)
    _no_openf1(monkeypatch)

    table = get_sprint_results.invoke({"year": 2026, "grand_prix": "China"})

    lines = table.splitlines()
    assert lines[0] == "### Sprint Race Results: China 2026"
    assert lines[1] == "*(Source: the FIA final classification)*"
    assert "| 1 | George Russell (RUS) | Mercedes | 33:38.998 | 8 |" in table
    assert "| 2 | Charles Leclerc (LEC) | Ferrari | +0.674 | 7 |" in table
    assert "| DNF | Nico Hülkenberg (HUL) | Audi | ❌ DNF (Mechanical) | 0 |" in table
    assert "| DNF | Valtteri Bottas (BOT) | Cadillac | ❌ DNF (Withdrew) | 0 |" in table
    assert "| 19 | Sergio Pérez (PER) | Cadillac | +28.241 (incl. 5s penalty) | 0 |" in table


def test_a_weekend_without_a_sprint_says_so(race_results_f1db, monkeypatch):
    _round(monkeypatch, 19)
    _no_openf1(monkeypatch)

    assert "No sprint classification is published for Mexico 2026" in get_sprint_results.invoke(
        {"year": 2026, "grand_prix": "Mexico"}
    )


def test_driver_label_degrades_to_what_is_known():
    assert module.driver_label("Kimi Antonelli", "ANT") == "Kimi Antonelli (ANT)"
    assert module.driver_label("", "ANT") == "ANT"
    assert module.driver_label("", "") == "-"
