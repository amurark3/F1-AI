"""Real f1db qualifying rows for the chat-tool tests.

``fixtures/f1db_session_tools/qualifying.json`` holds f1db v2026.20.0's rows for 2026 R19
Mexico City qualifying (Lawson disqualified: no place, no Q1, Q2/Q3 times kept) and R2 China
sprint qualifying.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

QUALIFYING = Path(__file__).parent / "fixtures" / "f1db_session_tools" / "qualifying.json"
MEXICO_Q_RACE_ID = 1168
CHINA_SQ_RACE_ID = 1151

SCHEMA = """
    CREATE TABLE race (id, year, round);
    CREATE TABLE driver (id PRIMARY KEY, name, abbreviation);
    CREATE TABLE constructor (id PRIMARY KEY, name);
    CREATE TABLE race_data (
        race_id, type, driver_id, constructor_id, position_display_order, position_number, position_text,
        practice_time, practice_gap, practice_laps, qualifying_q1, qualifying_q2, qualifying_q3, qualifying_gap,
        race_time, race_gap, race_laps, race_points, race_grid_position_number, race_reason_retired
    );
"""


def build_qualifying_db(path: Path) -> Path:
    data = json.loads(QUALIFYING.read_text())
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        for key, race_id in (("mexico_q", MEXICO_Q_RACE_ID), ("china_sq", CHINA_SQ_RACE_ID)):
            block = data[key]
            conn.execute("INSERT INTO race VALUES (?, ?, ?)", (race_id, block["year"], block["round"]))
            for order, position, text, code, name, team, q1, q2, q3 in block["rows"]:
                conn.execute("INSERT OR IGNORE INTO driver VALUES (?, ?, ?)", (code.lower(), name, code))
                conn.execute("INSERT OR IGNORE INTO constructor VALUES (?, ?)", (team.lower(), team))
                conn.execute(
                    "INSERT INTO race_data (race_id, type, driver_id, constructor_id, position_display_order,"
                    " position_number, position_text, qualifying_q1, qualifying_q2, qualifying_q3)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (race_id, block["type"], code.lower(), team.lower(), order, position, text, q1, q2, q3),
                )
        conn.commit()
    return path


@pytest.fixture
def qualifying_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point f1db at the captured qualifying rows."""
    from app.data import f1db_source

    db_path = build_qualifying_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
