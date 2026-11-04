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
from typing import TYPE_CHECKING

import pytest

from tests.profiles_support import SCHEMA

if TYPE_CHECKING:
    from collections.abc import Iterator

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


@pytest.fixture
def identity_f1db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point f1db at the captured seasons, with no directory or index cached from elsewhere.

    ``app`` is imported inside: the conftest re-exports this fixture, and importing
    ``app`` there would run before the environment is scrubbed.
    """
    from app.data import f1db_source, identity

    db_path = build_identity_db(tmp_path / "f1db.db")
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    identity.clear_cache()
    yield db_path
    identity.clear_cache()


# FastF1's spellings for the Mexico City weekend (2026 R19), as its results carried
# them into the R19 post-qualifying prediction snapshot (stored 2026-11-01 01:38 UTC):
# FirstName + LastName, TeamName and Abbreviation, which FastF1 left blank for
# Hirakawa (the snapshot stored "NAN"). Keyed by car number, OpenF1's for each car.
MEXICO_FASTF1_NAMES: dict[int, tuple[str | None, str, str, str]] = {
    3: ("VER", "Max", "Verstappen", "Red Bull"),
    11: ("PER", "Sergio", "Pérez", "Cadillac F1 Team"),
    12: ("ANT", "Andrea Kimi", "Antonelli", "Mercedes"),
    27: ("HUL", "Nico", "Hülkenberg", "Audi"),
    30: ("LAW", "Liam", "Lawson", "RB F1 Team"),
    50: (None, "Ryo", "Hirakawa", "Haas F1 Team"),
    55: ("SAI", "Carlos", "Sainz", "Williams"),
}

JOLPICA_MEXICO_RESULTS = Path(__file__).parent / "fixtures" / "mexico_2026_r19" / "jolpica_results.json"


def mexico_fastf1_results() -> list[dict]:
    """FastF1 result rows for those cars, in Jolpica's Mexico City race order (the source FastF1 reads).

    A missing abbreviation is NaN, the way pandas hands it over.
    """
    results = json.loads(JOLPICA_MEXICO_RESULTS.read_text())["Results"]
    return [
        {
            "Position": float(row["position"]),
            "DriverNumber": row["number"],
            "Abbreviation": code if code is not None else float("nan"),
            "FirstName": first,
            "LastName": last,
            "TeamName": team,
            "GridPosition": float(row["grid"]),
            "Points": float(row["points"]),
            "Status": row["status"],
        }
        for row in results
        if int(row["number"]) in MEXICO_FASTF1_NAMES
        for code, first, last, team in [MEXICO_FASTF1_NAMES[int(row["number"])]]
    ]
