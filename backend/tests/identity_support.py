"""Real f1db seasons for the driver-identity tests.

``fixtures/f1db_identity/seasons.json`` holds f1db v2026.19.0's rows for the
seasons whose names and numbers break a naive resolver (see its ``source`` for
how it was cut down):

* **2003**: VER is Jos Verstappen; two Schumachers race.
* **2006**: MSC is Michael; MON is both Tiago Monteiro and Franck Montagny;
  Super Aguri's car 23 had three drivers; Pedro de la Rosa's particles.
* **2014**: VER is Jean-Éric Vergne in the races and Max Verstappen in FP1.
* **2022**: MSC is Mick; Nyck de Vries raced car 45, which Logan Sargeant
  drove in FP1.
* **2023**: Nyck de Vries raced car 21 for AlphaTauri.
* **2026** through round 19: Carlos Sainz Jr., Nico Hülkenberg, and Ryō
  Hirakawa standing in for Ocon as car 50 at Mexico City.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from tests.profiles_support import SCHEMA

SEASONS = Path(__file__).parent / "fixtures" / "f1db_identity" / "seasons.json"


def identity_seasons() -> dict:
    return json.loads(SEASONS.read_text())


def build_identity_db(path: Path) -> Path:
    """An f1db at ``path`` holding the captured seasons."""
    data = identity_seasons()
    races = sorted({(year, rnd) for year, rnd, *_ in data["entries"]})
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            """INSERT INTO driver (id, name, first_name, last_name, full_name, abbreviation, permanent_number)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            data["drivers"],
        )
        conn.executemany("INSERT INTO constructor (id, name, full_name) VALUES (?, ?, ?)", data["constructors"])
        conn.executemany(
            "INSERT INTO race (id, year, round) VALUES (?, ?, ?)",
            [(year * 100 + rnd, year, rnd) for year, rnd in races],
        )
        conn.executemany(
            """INSERT INTO race_data (race_id, type, driver_id, driver_number, constructor_id)
               VALUES (?, ?, ?, ?, ?)""",
            [(year * 100 + rnd, kind, *rest) for year, rnd, kind, *rest in data["entries"]],
        )
        conn.executemany(
            "INSERT INTO season_entrant_driver (year, driver_id, constructor_id, rounds, test_driver) VALUES (?, ?, ?, '', 0)",
            data["entrants"],
        )
        conn.commit()
    return path
