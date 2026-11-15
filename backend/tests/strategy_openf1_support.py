"""The 2025 São Paulo Grand Prix (R21) as the strategy modules now read it: OpenF1 laps, stints and results.

Every row is real (``fixtures/sao_paulo_2025_r21``, captured from OpenF1 on
2026-11-10 and 2026-11-14): the entry list, the race's stints and
classification, race control (a safety car and a virtual safety car), and the
laps of car 12 (Antonelli), the only car whose laps were captured.
"""

from __future__ import annotations

import json
from pathlib import Path

import fastf1
import pytest

from app.data.openf1.laps import laps_from_openf1
from app.data.openf1.race_control import neutralised_windows
from app.data.openf1.session_laps import SessionLaps
from app.data.openf1.sessions import EntryDriver, _session
from app.data.openf1_stints import stints_from_openf1
from app.data.race_classification import RaceClassification, classification_from_openf1

SAO_PAULO_2025 = Path(__file__).parent / "fixtures" / "sao_paulo_2025_r21"
RACE_KEY = 9869


def _rows(name: str) -> list[dict]:
    return json.loads((SAO_PAULO_2025 / name).read_text())


def entries() -> dict[int, dict]:
    return {row["driver_number"]: row for row in _rows("openf1_drivers.json")}


def race_session_laps() -> SessionLaps:
    """The race with car 12's laps, the entry list and race control's windows."""
    race = next(session for row in _rows("openf1_sessions.json") if (session := _session(row)) and session.code == "R")
    drivers = {
        number: EntryDriver(
            number=number,
            code=row["name_acronym"],
            name=row["full_name"],
            team=row["team_name"],
            colour=row["team_colour"],
        )
        for number, row in entries().items()
    }
    return SessionLaps(
        session=race,
        year=2025,
        round=21,
        drivers=drivers,
        laps=laps_from_openf1(_rows("openf1_laps_ant.json")),
        windows=neutralised_windows(_rows("openf1_race_control.json")),
    )


def race_stints_2025():
    return stints_from_openf1(_rows("openf1_stints.json"), entries(), {})


def race_classification_2025() -> RaceClassification:
    codes = {number: row["name_acronym"] for number, row in entries().items()}
    return RaceClassification(
        source="openf1-session-result",
        drivers=classification_from_openf1(_rows("openf1_session_result.json"), codes),
    )


@pytest.fixture
def no_fastf1(monkeypatch):
    """Any FastF1 request fails the test (the pit-strategy tool reads OpenF1 and f1db only)."""

    def refuse(*args, **kwargs):
        raise AssertionError("FastF1 was asked for a session")

    monkeypatch.setattr(fastf1, "get_session", refuse)
    monkeypatch.setattr(fastf1.core.Session, "load", refuse)
