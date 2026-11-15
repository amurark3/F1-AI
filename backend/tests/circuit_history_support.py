"""Real f1db rows for the circuit-history tests.

``fixtures/f1db_circuit_history/editions.json`` holds f1db v2026.20.0's race rows
for the Brazilian (``interlagos``, 2026 R20) and Las Vegas (``las-vegas``, 2026 R21)
Grands Prix of 2023-2026, with the ``RACE_RESULT`` and ``STARTING_GRID_POSITION``
rows of every edition already run (Brazil 2023-2026, Las Vegas 2023-2025). The 2026
Las Vegas race is on the calendar with no results yet.

Hand-checked against what was raced: Verstappen won Brazil 2023 from pole and 2024
from 17th, and finished 3rd in 2025 after starting from the pit lane.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

EDITIONS = Path(__file__).parent / "fixtures" / "f1db_circuit_history" / "editions.json"

SCHEMA = """
    CREATE TABLE race (id, year, round, circuit_id, grand_prix_id);
    CREATE TABLE grand_prix (id, name);
    CREATE TABLE driver (id, name, abbreviation);
    CREATE TABLE constructor (id, name);
    CREATE TABLE race_data (
        race_id, type, position_number, position_display_order, position_text, driver_id, constructor_id,
        starting_grid_position_qualification_position_number, starting_grid_position_grid_penalty,
        starting_grid_position_grid_penalty_positions
    );
"""


def build_circuit_history_db(path: Path) -> Path:
    """An f1db at ``path`` holding the captured editions."""
    data = json.loads(EDITIONS.read_text())
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO race VALUES (?, ?, ?, ?, ?)", data["races"])
        conn.executemany("INSERT INTO grand_prix VALUES (?, ?)", data["grands_prix"])
        conn.executemany("INSERT INTO driver VALUES (?, ?, ?)", data["drivers"])
        conn.executemany("INSERT INTO constructor VALUES (?, ?)", data["constructors"])
        conn.executemany("INSERT INTO race_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data["race_data"])
        conn.commit()
    return path


@pytest.fixture
def circuit_history_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point f1db at the captured editions (``app`` is imported inside, as in ``calendar_support``)."""
    from app.data import f1db_source

    db_path = build_circuit_history_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
