"""São Paulo 2026 qualifying (round 20) the way production read it, for the driver-code tests.

FastF1 sent Rafael Câmara's row (Q P13, car 51 in Ocon's Haas) with no
``Abbreviation``. ``str()`` turned that NaN into the code "nan", the grid
dropped him as not entered and back-filled him at "P23", and the model scored
him from there. The fixtures in ``fixtures/sao_paulo_2026_r20/`` are real
(``provenance.json`` names every request):

* ``jolpica_qualifying.json``: the classification FastF1 reads, in its order.
  Jolpica codes him CAM today; :func:`r20_fastf1_qualifying` blanks that one
  cell, as FastF1 had it.
* ``openf1_drivers_qualifying.json``: the qualifying entry list. OpenF1 codes
  car 51 CAM.
* ``f1db_v2026_20_camara.json``: his f1db rows, which arrived with v2026.20.0
  on 9 Nov. Production read v2026.19.0 on qualifying day, which does not know
  him; the ``identity_f1db`` fixture is that release.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import httpx
import pandas as pd

from app.data.openf1.sessions import entry_list
from app.data.session_entries import WeekendEntryList, _entry

FIXTURES = Path(__file__).parent / "fixtures" / "sao_paulo_2026_r20"
YEAR = 2026
ROUND = 20
QUALIFYING_SESSION_KEY = 11408
CAMARA_NUMBER = 51


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


def r20_fastf1_qualifying() -> pd.DataFrame:
    """FastF1's R20 qualifying results: Jolpica's rows, with Câmara's Abbreviation NaN.

    Columns are FastF1's: ``DriverNumber`` is text and ``Position`` a float, as
    pandas hands them over.
    """
    rows = _load("jolpica_qualifying.json")["QualifyingResults"]
    return pd.DataFrame(
        [
            {
                "DriverNumber": row["number"],
                "Position": float(row["position"]),
                "Abbreviation": float("nan") if int(row["number"]) == CAMARA_NUMBER else row["Driver"]["code"],
                "FirstName": row["Driver"]["givenName"],
                "LastName": row["Driver"]["familyName"],
                "TeamName": row["Constructor"]["name"],
            }
            for row in rows
        ]
    )


def add_camara_to_f1db(db_path: Path) -> None:
    """Add f1db v2026.20.0's Câmara rows to an ``identity_f1db`` database (v2026.19.0)."""
    data = _load("f1db_v2026_20_camara.json")
    races = sorted({(year, rnd) for year, rnd, *_ in data["entries"]})
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            """INSERT INTO driver (id, name, first_name, last_name, full_name, abbreviation, permanent_number)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            data["drivers"],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO race (id, year, round) VALUES (?, ?, ?)",
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


def r20_qualifying_entry_list() -> WeekendEntryList:
    """The weekend entry list as ``load_weekend_entry_list`` builds it from OpenF1's qualifying cars."""
    rows = _load("openf1_drivers_qualifying.json")
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=rows))) as client:
        cars = entry_list(client, QUALIFYING_SESSION_KEY)
    entries = tuple(_entry(car, YEAR) for car in sorted(cars.values(), key=lambda car: car.number))
    return WeekendEntryList(entries=entries, session="Q")
