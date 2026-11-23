"""The 2026 Mexico City Grand Prix (R19) race as the debrief's lap reader sees it.

Every row is real (``fixtures/mexico_2026_r19``, captured from OpenF1): the race
session, the entry list, race control, and the laps of the first five cars home
(Verstappen, Hamilton, Antonelli, Leclerc, Norris). Only those five cars' laps
are held, and R19's three lap leaders (Leclerc, Antonelli, Verstappen) are all
among them, so every lap's leader can be read.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from app.data.openf1.laps import laps_from_openf1
from app.data.openf1.race_control import neutralised_windows
from app.data.openf1.session_laps import SessionLaps
from app.data.openf1.sessions import EntryDriver, _colour, _session

MEXICO_2026 = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
RACE_KEY = 11404


def rows(name: str) -> list[dict]:
    return json.loads((MEXICO_2026 / name).read_text())


def entries() -> dict[int, EntryDriver]:
    return {
        row["driver_number"]: EntryDriver(
            number=row["driver_number"],
            code=row["name_acronym"],
            name=row["full_name"],
            team=row["team_name"],
            colour=row["team_colour"],
        )
        for row in rows("openf1_drivers.json")
    }


def race_session():
    return next(session for row in rows("openf1_sessions.json") if (session := _session(row)) and session.code == "R")


def race_session_laps() -> SessionLaps:
    """The race with the top five's laps, the entry list and race control's windows."""
    return SessionLaps(
        session=race_session(),
        year=2026,
        round=19,
        drivers=entries(),
        laps=laps_from_openf1(rows("openf1_laps_top5.json")),
        windows=neutralised_windows(rows("openf1_race_control.json")),
    )


def radio_inputs():
    """The race with the radio clips' cars: top five, three clip drivers and the five DNFs, plus the dated pit rows."""
    from app.services.debrief_radio import RadioInputs

    laps = laps_from_openf1(rows("openf1_laps_top5.json") + rows("openf1_laps_radio.json"))
    # The entry list as OpenF1's client serves it: team colours normalised to #RRGGBB.
    drivers = {n: replace(entry, colour=_colour(entry.colour)) for n, entry in entries().items()}
    return RadioInputs(
        laps=replace(race_session_laps(), laps=laps, drivers=drivers),
        radio=rows("openf1_team_radio.json"),
        pit=rows("openf1_pit_dated.json"),
        messages=rows("openf1_race_control.json"),
        gmt_offset="-06:00:00",
        dnf_cars={14: 5, 18: 5, 41: 58, 77: 42, 87: 47},  # laps completed, as the FIA final classification prints them
    )
