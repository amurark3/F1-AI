"""Tests for the f1db calendar and line-ups the power-unit service reads."""

from datetime import date
import sqlite3

import pytest

from app.data.power_units import season_context
from app.data.power_units.season_context import load_season_context

SCHEMA = """
CREATE TABLE grand_prix (id TEXT PRIMARY KEY, short_name TEXT, abbreviation TEXT);
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER, date TEXT, grand_prix_id TEXT);
CREATE TABLE driver (id TEXT PRIMARY KEY, name TEXT, abbreviation TEXT);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race_data (race_id INTEGER, type TEXT, driver_number INTEGER, driver_id TEXT, constructor_id TEXT);
"""


@pytest.fixture
def season_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO grand_prix VALUES (?, ?, ?)",
        [("italy", "Italian GP", "ITA"), ("spain", "Spanish GP", None)],
    )
    conn.executemany(
        "INSERT INTO race VALUES (?, ?, ?, ?, ?)",
        [
            (1, 2026, 13, "2026-09-06", "italy"),
            (2, 2026, 14, "2026-09-13", "spain"),
            (3, 2025, 1, "2025-03-16", "italy"),
        ],
    )
    conn.executemany(
        "INSERT INTO driver VALUES (?, ?, ?)",
        [
            ("liam-lawson", "Liam Lawson", "LAW"),
            ("ayumu-iwasa", "Ayumu Iwasa", None),
            ("max-verstappen", "Max Verstappen", "VER"),
        ],
    )
    conn.executemany("INSERT INTO constructor VALUES (?, ?)", [("red-bull", "Red Bull")])
    conn.executemany(
        "INSERT INTO race_data VALUES (?, ?, ?, ?, ?)",
        [
            (1, "QUALIFYING_RESULT", 30, "liam-lawson", "red-bull"),
            (1, "RACE_RESULT", 30, "liam-lawson", "red-bull"),
            (1, "STARTING_GRID_POSITION", 3, "max-verstappen", "red-bull"),
            # FP1 rookie running Lawson's car: not a seat change.
            (1, "FREE_PRACTICE_1_RESULT", 36, "ayumu-iwasa", "red-bull"),
            (2, "RACE_RESULT", 30, "liam-lawson", "red-bull"),
            (3, "RACE_RESULT", 30, "liam-lawson", "red-bull"),
        ],
    )
    monkeypatch.setattr(season_context, "connect", lambda: conn)
    return conn


def test_calendar_and_race_weekend_entries(season_db):
    context = load_season_context(2026)

    assert [(item.round, item.name, item.code) for item in context.rounds] == [
        (13, "Italian GP", "ITA"),
        (14, "Spanish GP", ""),
    ]
    assert context.round_on(date(2026, 9, 13)).round == 14
    assert context.round_on(date(2026, 9, 14)) is None
    assert {(entry.round, entry.car_number, entry.driver_code) for entry in context.entries} == {
        (13, 3, "VER"),
        (13, 30, "LAW"),
        (14, 30, "LAW"),
    }
    assert len(context.entries_at(13)) == 2
    assert context.constructors() == {"red-bull": "Red Bull"}


def test_driver_for_car_falls_back_to_the_latest_earlier_round(season_db):
    context = load_season_context(2026)
    assert context.driver_for_car(30, 14).round == 14
    assert context.driver_for_car(3, 18).driver_id == "max-verstappen"
    assert context.driver_for_car(3, 12) is None
    assert context.driver_for_car(99, 18) is None
