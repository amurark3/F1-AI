"""Tests for app.data.qualifying_times — a qualifying session's segment times from f1db, else OpenF1.

Real rows: f1db v2026.20.0's Mexico City 2026 qualifying (Lawson disqualified: no place, no Q1) and
OpenF1's session_result and entry list for the same session (``fixtures/mexico_2026_r19``).
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from app.data import qualifying_times as module, race_classification
from app.data.qualifying_times import qualifying_times, seconds
from tests.fastf1_guard import no_fastf1  # noqa: F401
from tests.openf1_support import make_session, serve

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_fastf1")]

MEXICO = Path(__file__).parent / "fixtures" / "mexico_2026_r19"


@pytest.mark.parametrize(
    ("text", "value"),
    [("1:16.514", 76.514), ("45.123", 45.123), ("", None), (None, None)],
)
def test_seconds(text, value):
    assert seconds(text) == value


def test_f1db_answers_first_and_is_final(qualifying_f1db, monkeypatch):
    monkeypatch.setattr(module, "openf1_session_result", lambda *_args: pytest.fail("OpenF1 was asked"))

    table = qualifying_times(2026, 19, "Q")

    assert table is not None
    assert (table.source, table.final, len(table.cars)) == ("f1db", True, 22)
    assert (table.cars[0].code, table.cars[0].times, table.cars[0].note) == ("HAM", (77.341, 76.953, 76.514), None)


def test_a_disqualified_car_has_no_place_a_note_and_the_times_f1db_kept(qualifying_f1db):
    table = qualifying_times(2026, 19, "Q")

    lawson = next(car for car in table.cars if car.code == "LAW")
    assert (lawson.position, lawson.note, lawson.times) == (None, "DSQ", (None, 77.207, 77.029))


def test_an_unreadable_f1db_falls_through_to_openf1(monkeypatch):
    def refuse(*_args):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(module, "session_classification", refuse)
    monkeypatch.setattr(module, "openf1_session_result", lambda *_args: ([], {}))

    assert qualifying_times(2026, 19, "Q") is None


def test_openf1_answers_a_round_f1db_does_not_hold_and_is_provisional(race_results_f1db, monkeypatch):
    """Lawson has no position in OpenF1's result (it does not flag a disqualification): NC, with his times."""
    monkeypatch.setattr(race_classification, "find_session", lambda *_args: make_session("Q"))
    serve(
        monkeypatch,
        race_classification,
        {
            "session_result": json.loads((MEXICO / "openf1_session_result_qualifying.json").read_text()),
            "drivers": json.loads((MEXICO / "openf1_drivers_qualifying.json").read_text()),
        },
    )

    table = qualifying_times(2026, 19, "Q")

    assert table is not None
    assert (table.source, table.final, len(table.cars)) == ("openf1-session-result", False, 22)
    assert (table.cars[0].code, table.cars[0].position, table.cars[0].times) == ("HAM", 1, (77.341, 76.953, 76.514))
    unplaced = [car for car in table.cars if car.position is None]
    assert [(car.code, car.note) for car in unplaced] == [("LAW", "NC")]
