"""Real f1db rows for the Results tab tests.

``fixtures/f1db_race_results/rounds.json`` holds f1db v2026.20.0's rows for 2026 R19 Mexico City
(``RACE_RESULT`` plus the ``FASTEST_LAP`` winner), R2's ``SPRINT_RACE_RESULT``, and the lapped
``RACE_RESULT`` rows of R18. Mexico: five DNFs, and time penalties for Piastri and Colapinto
(10 s) and Gasly (30 s).
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

ROUNDS = Path(__file__).parent / "fixtures" / "f1db_race_results" / "rounds.json"

SCHEMA = """
    CREATE TABLE race (id, year, round);
    CREATE TABLE driver (id, name, abbreviation);
    CREATE TABLE constructor (id, name);
    CREATE TABLE race_data (
        race_id, type, position_display_order, position_number, position_text, driver_id, constructor_id,
        race_laps, race_time, race_time_millis, race_time_penalty_millis, race_gap, race_gap_laps,
        race_reason_retired, race_points, race_fastest_lap, fastest_lap_lap, fastest_lap_time
    );
"""


def build_race_results_db(path: Path) -> Path:
    data = json.loads(ROUNDS.read_text())
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO race VALUES (?, ?, ?)", data["races"])
        conn.executemany("INSERT INTO driver VALUES (?, ?, ?)", data["drivers"])
        conn.executemany("INSERT INTO constructor VALUES (?, ?)", data["constructors"])
        conn.executemany(
            "INSERT INTO race_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data["race_data"]
        )
        conn.commit()
    return path


@pytest.fixture
def race_results_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.data import f1db_source

    db_path = build_race_results_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
