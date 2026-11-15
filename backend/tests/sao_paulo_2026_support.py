"""São Paulo 2026 qualifying (round 20), for the driver-code tests.

On the day, FastF1 sent Rafael Câmara's row (Q P13, car 51 in Ocon's Haas) with
no ``Abbreviation``. ``str()`` turned that NaN into the code "nan", the grid
dropped him as not entered and back-filled him at "P23", and the model scored
him from there. FastF1 no longer feeds the order; :func:`r20_openf1_qualifying`
builds it from OpenF1 and can blank his code the same way. The fixtures in ``fixtures/sao_paulo_2026_r20/`` are real
(``provenance.json`` names every request):

* ``jolpica_qualifying.json``: the classification FastF1 read, in its order.
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

from app.data.openf1.sessions import entry_list
from app.data.predictions.openf1_qualifying import qualifying_order
from app.data.session_entries import WeekendEntryList, _entry

FIXTURES = Path(__file__).parent / "fixtures" / "sao_paulo_2026_r20"
YEAR = 2026
ROUND = 20
QUALIFYING_SESSION_KEY = 11408
CAMARA_NUMBER = 51


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


def r20_openf1_qualifying(*, camara_coded: bool = True) -> list[dict]:
    """R20's qualifying order as the OpenF1 path builds it from the captured ``session_result`` and entry list.

    ``camara_coded=False`` blanks Câmara's ``name_acronym``, the way a feed can send a debutant: the entry list
    then prints car 51 by its number and only f1db can name him.
    """
    rows = _load("openf1_drivers_qualifying.json")
    if not camara_coded:
        rows = [{**row, "name_acronym": None} if row["driver_number"] == CAMARA_NUMBER else row for row in rows]
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=rows))) as client:
        entries = entry_list(client, QUALIFYING_SESSION_KEY)
    return qualifying_order(_load("openf1_session_result_qualifying.json"), entries, YEAR)


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
