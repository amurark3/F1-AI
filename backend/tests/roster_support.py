"""Real 2026 data for the prediction-roster tests: f1db race starts and OpenF1 entry lists.

The roster broke on real data (the R20 São Paulo prediction listed 23 drivers),
so its tests run on the data that broke it:

* ``f1db_2026_r18/``: every 2026 race start through round 18 (f1db v2026.18.0)
  and the championship table after it. Tsunoda raced Racing Bulls' car in
  R12–R14 while Lawson stepped up for the injured Hadjar.
* ``mexico_2026_r19/``: OpenF1's sessions and ``drivers`` lists for Mexico City.
  Hirakawa raced Ocon's Haas as car 50, with no team in the race list.
* ``sao_paulo_2026_r20/``: OpenF1's São Paulo sessions, whose drivers OpenF1
  had already filled in (with Ocon) on 2 Nov, days before any of them ran.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

import httpx

from app.data import f1db_source
from app.data.openf1.sessions import _session
from tests.f1db_fixture import build_f1db
from tests.openf1_support import NO_RESULTS

if TYPE_CHECKING:
    import pytest

    from app.data.openf1.sessions import OpenF1Session

FIXTURES = Path(__file__).parent / "fixtures"
MEXICO = FIXTURES / "mexico_2026_r19"
SAO_PAULO = FIXTURES / "sao_paulo_2026_r20"
F1DB_2026 = FIXTURES / "f1db_2026_r18"

# OpenF1 session keys of the Mexico City weekend.
MEXICO_FP1 = 11397
MEXICO_QUALIFYING = 11400
MEXICO_RACE = 11404
SAO_PAULO_FP1 = 11405

# The morning after Mexico City, when the R20 snapshot was computed.
AFTER_MEXICO = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def load(path: Path) -> list | dict:
    return json.loads(path.read_text())


def weekend(path: Path) -> tuple[OpenF1Session, ...]:
    """A weekend's sessions as ``weekend_sessions`` returns them, from OpenF1's own rows."""
    return tuple(session for row in load(path / "openf1_sessions.json") if (session := _session(row)) is not None)


def mexico_drivers() -> dict[int, list]:
    """OpenF1 ``drivers`` rows for each Mexico City session that was captured."""
    return {
        MEXICO_FP1: load(MEXICO / "openf1_drivers_practice1.json"),
        MEXICO_QUALIFYING: load(MEXICO / "openf1_drivers_qualifying.json"),
        MEXICO_RACE: load(MEXICO / "openf1_drivers.json"),
    }


def drivers_route(by_session: dict[int, list | httpx.Response]):
    """An OpenF1 ``drivers`` route answering per ``session_key``; 404 for any other session."""

    def route(request: httpx.Request) -> httpx.Response:
        answer = by_session.get(int(request.url.params["session_key"]))
        if answer is None:
            return httpx.Response(404, json=NO_RESULTS)
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    return route


def requested_sessions(fake) -> list[int]:
    """The session keys a fake OpenF1 was asked for drivers of, in order."""
    return [int(request.url.params["session_key"]) for request in fake.requests]


def championship_2026() -> list[dict]:
    """The 2026 championship table after round 18, as ``driver_standings_detailed`` returns it."""
    return load(F1DB_2026 / "driver_standings.json")


def install_f1db_2026(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An f1db holding the real 2026 race starts through round 18, installed as the dataset."""
    data = load(F1DB_2026 / "race_starts.json")
    db_path = build_f1db(tmp_path / "f1db_2026.db", seed=False)
    rounds = sorted({start[0] for start in data["starts"]})
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany("INSERT INTO driver (id, name, abbreviation) VALUES (?, ?, ?)", data["drivers"])
        conn.executemany("INSERT INTO constructor (id, name) VALUES (?, ?)", data["constructors"])
        conn.executemany("INSERT INTO race (id, year, round) VALUES (?, 2026, ?)", [(rnd, rnd) for rnd in rounds])
        conn.executemany(
            "INSERT INTO race_data (race_id, type, driver_id, constructor_id) VALUES (?, 'RACE_RESULT', ?, ?)",
            data["starts"],
        )
        conn.commit()
    monkeypatch.setattr(f1db_source, "DB_PATH", db_path)
    return db_path
