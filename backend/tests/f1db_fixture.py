"""A real-but-tiny f1db SQLite database for tests.

Every module that reads F1 history goes through ``app.data.f1db_source.connect``,
which opens ``DB_PATH`` read-only. Rather than mock ``connect`` (which would
leave the SQL itself untested — and the SQL is where the bugs are), tests build
an actual SQLite file with the f1db schema and point ``DB_PATH`` at it.

The schema below carries only the tables and columns the app actually queries,
with f1db's real names and semantics:

* ``race_data`` is every session result; rows are discriminated by ``type``
  (``RACE_RESULT``, ``QUALIFYING_RESULT``, ``SPRINT_RACE_RESULT``, ...).
* ``position_number`` is NULL for unclassified entries (DNF/DNS/DSQ);
  ``position_display_order`` ranks every entrant including those.
* ``championship_won`` is 1 for a decided title and 0 for the season still in
  progress — which is how "is this season live?" is derived.

Use the ``fake_f1db`` fixture for the default two-season dataset, or
``build_f1db`` directly to construct a bespoke one.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA = """
CREATE TABLE season (year INTEGER PRIMARY KEY);

CREATE TABLE country (
    id TEXT PRIMARY KEY,
    name TEXT,
    alpha2_code TEXT
);

CREATE TABLE grand_prix (
    id TEXT PRIMARY KEY,
    name TEXT,
    full_name TEXT
);

CREATE TABLE circuit (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    place_name TEXT,
    country_id TEXT
);

CREATE TABLE driver (
    id TEXT PRIMARY KEY,
    name TEXT,
    full_name TEXT,
    abbreviation TEXT,
    nationality_country_id TEXT,
    total_race_wins INTEGER DEFAULT 0,
    total_podiums INTEGER DEFAULT 0,
    total_pole_positions INTEGER DEFAULT 0,
    total_points REAL DEFAULT 0,
    total_championship_wins INTEGER DEFAULT 0,
    total_race_starts INTEGER DEFAULT 0
);

CREATE TABLE constructor (
    id TEXT PRIMARY KEY,
    name TEXT,
    total_race_wins INTEGER DEFAULT 0,
    total_pole_positions INTEGER DEFAULT 0,
    total_championship_wins INTEGER DEFAULT 0,
    total_points REAL DEFAULT 0
);

CREATE TABLE race (
    id INTEGER PRIMARY KEY,
    year INTEGER,
    round INTEGER,
    date TEXT,
    grand_prix_id TEXT,
    circuit_id TEXT,
    official_name TEXT
);

CREATE TABLE race_data (
    race_id INTEGER,
    type TEXT,
    position_number INTEGER,
    position_display_order INTEGER,
    position_text TEXT,
    driver_id TEXT,
    constructor_id TEXT,
    race_points REAL,
    race_grid_position_number INTEGER,
    race_positions_gained INTEGER,
    race_reason_retired TEXT,
    qualifying_q1 TEXT,
    qualifying_q2 TEXT,
    qualifying_q3 TEXT
);

CREATE TABLE season_driver_standing (
    year INTEGER,
    position_number INTEGER,
    driver_id TEXT,
    points REAL,
    championship_won INTEGER DEFAULT 0
);

CREATE TABLE season_constructor_standing (
    year INTEGER,
    position_number INTEGER,
    constructor_id TEXT,
    points REAL,
    championship_won INTEGER DEFAULT 0
);

CREATE TABLE race_driver_standing (
    race_id INTEGER,
    position_number INTEGER,
    driver_id TEXT,
    points REAL
);

CREATE TABLE race_constructor_standing (
    race_id INTEGER,
    position_number INTEGER,
    constructor_id TEXT,
    points REAL
);

CREATE TABLE season_entrant_driver (
    year INTEGER,
    driver_id TEXT,
    constructor_id TEXT,
    rounds_text TEXT,
    test_driver INTEGER DEFAULT 0
);
"""


def build_f1db(path: Path, seed: bool = True) -> Path:
    """Create an f1db-shaped SQLite file at ``path``.

    With ``seed=False`` the schema is created empty, which is the setup for
    "no data for that season" branches.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        if seed:
            _seed(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def _seed(conn: sqlite3.Connection) -> None:
    """Two seasons: 2025 decided, 2026 in progress after two of three rounds."""
    conn.executemany("INSERT INTO season VALUES (?)", [(2025,), (2026,)])

    conn.executemany(
        "INSERT INTO country (id, name, alpha2_code) VALUES (?, ?, ?)",
        [("netherlands", "Netherlands", "NL"), ("monaco", "Monaco", "MC")],
    )

    conn.executemany(
        "INSERT INTO grand_prix (id, name, full_name) VALUES (?, ?, ?)",
        [
            ("bahrain", "Bahrain", "Bahrain Grand Prix"),
            ("monaco", "Monaco", "Monaco Grand Prix"),
            ("monza", "Italy", "Italian Grand Prix"),
        ],
    )

    conn.executemany(
        "INSERT INTO circuit (id, name, type, place_name, country_id) VALUES (?, ?, ?, ?, ?)",
        [
            ("bahrain", "Bahrain International Circuit", "RACE", "Sakhir", "netherlands"),
            ("monaco", "Circuit de Monaco", "STREET", "Monte-Carlo", "monaco"),
            ("monza", "Autodromo Nazionale Monza", "RACE", "Monza", "netherlands"),
        ],
    )

    conn.executemany(
        """INSERT INTO driver (id, name, full_name, abbreviation, nationality_country_id,
                               total_race_wins, total_podiums, total_pole_positions,
                               total_points, total_championship_wins, total_race_starts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("max-verstappen", "Verstappen", "Max Verstappen", "VER", "netherlands", 60, 100, 40, 2500.0, 4, 200),
            ("charles-leclerc", "Leclerc", "Charles Leclerc", "LEC", "monaco", 8, 40, 26, 1200.0, 0, 150),
            ("lando-norris", "Norris", "Lando Norris", "NOR", "netherlands", 5, 30, 8, 900.0, 0, 130),
        ],
    )

    conn.executemany(
        """INSERT INTO constructor (id, name, total_race_wins, total_pole_positions,
                                    total_championship_wins, total_points)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            ("red-bull", "Red Bull", 120, 100, 6, 7000.0),
            ("ferrari", "Ferrari", 245, 250, 16, 9000.0),
            ("mclaren", "McLaren", 190, 160, 9, 6000.0),
        ],
    )

    # 2025: rounds 1-2. 2026: rounds 1-3, only 1-2 have results (season live).
    conn.executemany(
        "INSERT INTO race (id, year, round, date, grand_prix_id, circuit_id, official_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 2025, 1, "2025-03-02", "bahrain", "bahrain", "Bahrain Grand Prix"),
            (2, 2025, 2, "2025-05-25", "monaco", "monaco", "Monaco Grand Prix"),
            (3, 2026, 1, "2026-03-08", "bahrain", "bahrain", "Bahrain Grand Prix"),
            (4, 2026, 2, "2026-05-24", "monaco", "monaco", "Monaco Grand Prix"),
            (5, 2026, 3, "2026-09-06", "monza", "monza", "Italian Grand Prix"),
        ],
    )

    race_rows: list[tuple] = []
    for race_id in (1, 2, 3, 4):
        # Race result: VER wins, LEC second, NOR retires (unclassified).
        race_rows += [
            (race_id, "RACE_RESULT", 1, 1, "1", "max-verstappen", "red-bull", 25.0, 1, 0, None, None, None, None),
            (race_id, "RACE_RESULT", 2, 2, "2", "charles-leclerc", "ferrari", 18.0, 3, 1, None, None, None, None),
            (
                race_id,
                "RACE_RESULT",
                None,
                3,
                "DNF",
                "lando-norris",
                "mclaren",
                0.0,
                2,
                None,
                "Engine",
                None,
                None,
                None,
            ),
            # Qualifying: VER pole, NOR second, LEC third.
            (
                race_id,
                "QUALIFYING_RESULT",
                1,
                1,
                "1",
                "max-verstappen",
                "red-bull",
                None,
                None,
                None,
                None,
                "1:29.1",
                "1:28.5",
                "1:27.9",
            ),
            (
                race_id,
                "QUALIFYING_RESULT",
                2,
                2,
                "2",
                "lando-norris",
                "mclaren",
                None,
                None,
                None,
                None,
                "1:29.4",
                "1:28.8",
                "1:28.1",
            ),
            (
                race_id,
                "QUALIFYING_RESULT",
                3,
                3,
                "3",
                "charles-leclerc",
                "ferrari",
                None,
                None,
                None,
                None,
                "1:29.6",
                "1:28.9",
                "1:28.3",
            ),
        ]
    # One sprint weekend, so "no sprint" stays the common case.
    race_rows += [
        (3, "SPRINT_RACE_RESULT", 1, 1, "1", "charles-leclerc", "ferrari", 8.0, 1, 0, None, None, None, None),
        (3, "SPRINT_RACE_RESULT", 2, 2, "2", "max-verstappen", "red-bull", 7.0, 2, 0, None, None, None, None),
    ]
    conn.executemany(
        """INSERT INTO race_data (race_id, type, position_number, position_display_order,
                                  position_text, driver_id, constructor_id, race_points,
                                  race_grid_position_number, race_positions_gained,
                                  race_reason_retired, qualifying_q1, qualifying_q2, qualifying_q3)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        race_rows,
    )

    # 2025 title decided; 2026 leader has not clinched yet.
    conn.executemany(
        "INSERT INTO season_driver_standing (year, position_number, driver_id, points, championship_won) VALUES (?, ?, ?, ?, ?)",
        [
            (2025, 1, "max-verstappen", 50.0, 1),
            (2025, 2, "charles-leclerc", 36.0, 0),
            (2025, 3, "lando-norris", 0.0, 0),
            (2026, 1, "max-verstappen", 50.0, 0),
            (2026, 2, "charles-leclerc", 44.0, 0),
            (2026, 3, "lando-norris", 0.0, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO season_constructor_standing (year, position_number, constructor_id, points, championship_won) VALUES (?, ?, ?, ?, ?)",
        [
            (2025, 1, "red-bull", 50.0, 1),
            (2025, 2, "ferrari", 36.0, 0),
            (2026, 1, "red-bull", 50.0, 0),
            (2026, 2, "ferrari", 44.0, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO race_driver_standing (race_id, position_number, driver_id, points) VALUES (?, ?, ?, ?)",
        [
            (3, 1, "max-verstappen", 25.0),
            (3, 2, "charles-leclerc", 26.0),
            (4, 1, "max-verstappen", 50.0),
            (4, 2, "charles-leclerc", 44.0),
        ],
    )
    conn.executemany(
        "INSERT INTO race_constructor_standing (race_id, position_number, constructor_id, points) VALUES (?, ?, ?, ?)",
        [(4, 1, "red-bull", 50.0), (4, 2, "ferrari", 44.0)],
    )

    conn.executemany(
        "INSERT INTO season_entrant_driver (year, driver_id, constructor_id, rounds_text, test_driver) VALUES (?, ?, ?, ?, ?)",
        [
            (2025, "max-verstappen", "red-bull", "1;2", 0),
            (2025, "charles-leclerc", "ferrari", "1;2", 0),
            (2025, "lando-norris", "mclaren", "1;2", 0),
            # A mid-season switch: the title team is the one with more rounds.
            (2026, "max-verstappen", "mclaren", "1", 0),
            (2026, "max-verstappen", "red-bull", "2;3", 0),
            (2026, "charles-leclerc", "ferrari", "1;2;3", 0),
            # A test-driver row that must never be picked as a title team.
            (2026, "lando-norris", "ferrari", "1;2;3", 1),
        ],
    )


@pytest.fixture
def fake_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``app.data.f1db_source`` at a seeded throwaway database."""
    from app.data import f1db_source

    db_path = build_f1db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path


@pytest.fixture
def empty_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An f1db with the schema but no rows — drives the "no data" branches."""
    from app.data import f1db_source

    db_path = build_f1db(tmp_path / "f1db_empty.db", seed=False)
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
