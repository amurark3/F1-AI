"""Real f1db calendar rows for the season-schedule tests.

``fixtures/f1db_calendar/calendar.json`` holds f1db v2026.20.0's race rows of
two seasons (see its ``source``):

* **2026**, all 23 rounds with every session's UTC start: six sprint weekends
  (R2, R4, R5, R9, R12, R17) and the Bahrain Grand Prix at Sepang (R16).
* **2023**, all 22 rounds: f1db records no session times before 2024, so only
  the race day and the weekend format.

``openf1_meetings_2026.json`` is OpenF1's 2026 meeting list for the same season.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CALENDAR = FIXTURES / "f1db_calendar" / "calendar.json"
MEETINGS_2026 = FIXTURES / "f1db_calendar" / "openf1_meetings_2026.json"

# The race columns the calendar reads, in the fixture's ``race_columns`` order.
SCHEMA = """
    CREATE TABLE race (
        id, year, round, date, time, grand_prix_id, circuit_id, qualifying_format, sprint_qualifying_format,
        free_practice_1_date, free_practice_1_time, free_practice_2_date, free_practice_2_time,
        free_practice_3_date, free_practice_3_time, sprint_qualifying_date, sprint_qualifying_time,
        sprint_race_date, sprint_race_time, qualifying_date, qualifying_time
    );
    CREATE TABLE grand_prix (id, full_name);
    CREATE TABLE circuit (id, place_name, country_id);
    CREATE TABLE country (id, name);
"""
INSERT_RACE = "INSERT INTO race VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"


def meetings_2026() -> list[dict]:
    return json.loads(MEETINGS_2026.read_text())


def build_calendar_db(path: Path) -> Path:
    """An f1db at ``path`` holding the captured calendars."""
    data = json.loads(CALENDAR.read_text())
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(INSERT_RACE, data["races"])
        conn.executemany("INSERT INTO grand_prix VALUES (?, ?)", data["grands_prix"])
        conn.executemany("INSERT INTO circuit VALUES (?, ?, ?)", data["circuits"])
        conn.executemany("INSERT INTO country VALUES (?, ?)", data["countries"])
        conn.commit()
    return path


@pytest.fixture
def calendar_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point f1db at the captured calendars.

    ``app`` is imported inside: the conftest re-exports this fixture, and importing
    ``app`` there would run before the environment is scrubbed.
    """
    from app.data import f1db_source

    db_path = build_calendar_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
