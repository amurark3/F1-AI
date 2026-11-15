"""A qualifying (or sprint qualifying) session's per-segment times, for the chat tools.

**Where it comes from** (``docs/DATA_SOURCES.md``): f1db once it holds the round,
else OpenF1's ``session_result`` (``duration`` is each car's best per segment).
Neither is FastF1. A car with no classified place carries a ``note`` saying why
("DSQ" from f1db, "NC" from OpenF1, which does not flag a disqualification).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.canonical_names import F1DB_READ_ERRORS, driver_identity, team_display_name
from app.data.f1db_sessions import (
    KIND_QUALIFYING,
    TYPE_QUALIFYING,
    TYPE_SPRINT_QUALIFYING,
    SessionEntry,
    session_classification,
)
from app.data.openf1.qualifying_result import result_rows
from app.data.race_classification import openf1_session_result

logger = structlog.get_logger()

F1DB_SOURCE = "f1db"
OPENF1_SOURCE = "openf1-session-result"
F1DB_TYPES = {"Q": TYPE_QUALIFYING, "SQ": TYPE_SPRINT_QUALIFYING}
SEGMENTS = 3

Times = tuple[float | None, float | None, float | None]


@dataclass(frozen=True)
class QualifyingCar:
    code: str
    name: str
    team: str
    #: The classified place; ``None`` for a car with none.
    position: int | None
    #: Best time in Q1, Q2 and Q3, in seconds.
    times: Times
    #: Why the car has no place ("DSQ", "NC"), else ``None``.
    note: str | None


@dataclass(frozen=True)
class QualifyingTimes:
    source: str
    #: True when the source is the FIA classification as f1db mirrors it.
    final: bool
    cars: tuple[QualifyingCar, ...]


def seconds(text: str | None) -> float | None:
    """``"1:23.456"`` or ``"45.123"`` as seconds; ``None`` for no time."""
    if not text:
        return None
    minutes, _, rest = text.rpartition(":")
    return round(int(minutes or 0) * 60 + float(rest), 3)


def _f1db_car(year: int, entry: SessionEntry) -> QualifyingCar:
    text = entry.position_text.strip().upper()
    return QualifyingCar(
        code=entry.driver_code,
        name=entry.driver_name,
        team=team_display_name(year, entry.team),
        position=entry.position,
        times=(seconds(entry.q1), seconds(entry.q2), seconds(entry.q3)),
        note=None if entry.position is not None else text,
    )


def _from_f1db(year: int, round_num: int, code: str) -> QualifyingTimes | None:
    try:
        entries = session_classification(year, round_num, F1DB_TYPES[code], KIND_QUALIFYING)
    except F1DB_READ_ERRORS as exc:
        logger.warning("qualifying_times.f1db_unreadable", year=year, round=round_num, error=str(exc))
        return None
    cars = tuple(_f1db_car(year, entry) for entry in entries)
    return QualifyingTimes(F1DB_SOURCE, True, cars) if cars else None


def _from_openf1(year: int, round_num: int, code: str) -> QualifyingTimes | None:
    rows, entries = openf1_session_result(year, round_num, code)
    cars = []
    for row in result_rows(rows):
        entry = entries.get(row.driver)
        who = driver_identity(year, code=entry and entry.code, number=row.driver, name=entry and entry.name)
        cars.append(
            QualifyingCar(
                code=who.code or str(row.driver),
                name=who.name,
                team=team_display_name(year, entry.team if entry else None),
                position=row.position,
                times=row.durations,
                note=None if row.position is not None else "NC",
            )
        )
    return QualifyingTimes(OPENF1_SOURCE, False, tuple(cars)) if cars else None


def qualifying_times(year: int, round_num: int, code: str) -> QualifyingTimes | None:
    """The session's cars with their segment times (``code`` "Q" or "SQ"), or ``None`` when no source holds it."""
    return _from_f1db(year, round_num, code) or _from_openf1(year, round_num, code)
