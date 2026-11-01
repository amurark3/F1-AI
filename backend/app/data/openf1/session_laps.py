"""Every lap of a session, with deletions applied and neutralised periods attached.

This is the measured base of the Telemetry Lab: the picker lists these laps,
the track map and the comparison pick from them, and tyre degradation reads a
race's laps from here. One load is four OpenF1 requests after the session is
found (drivers, laps, race control), so a session that has ended and settled is
kept in :mod:`app.data.analysis_cache` and never asked for again.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.analysis_cache import analysis_cache
from app.data.openf1.client import get_json, new_client
from app.data.openf1.laps import Lap, laps_from_openf1
from app.data.openf1.race_control import Window, deleted_laps, neutralised_windows, standing_deletions
from app.data.openf1.sessions import EntryDriver, OpenF1Session, entry_list, find_session, session_ended
from app.services.live_timing import parse_iso

logger = structlog.get_logger()

SESSION_LAPS_KIND = "session_laps"
SESSION_LAPS_VERSION = 1


@dataclass(frozen=True)
class SessionLaps:
    session: OpenF1Session
    year: int
    round: int
    drivers: dict[int, EntryDriver]
    laps: tuple[Lap, ...]
    windows: tuple[Window, ...]

    def driver_by_code(self, code: str) -> EntryDriver | None:
        wanted = code.strip().upper()
        return next((driver for driver in self.drivers.values() if driver.code == wanted), None)

    def laps_of(self, number: int) -> tuple[Lap, ...]:
        return tuple(lap for lap in self.laps if lap.driver == number)

    def to_json(self) -> dict:
        session = self.session
        return {
            "year": self.year,
            "round": self.round,
            "session": {
                "session_key": session.session_key,
                "meeting_key": session.meeting_key,
                "circuit_key": session.circuit_key,
                "code": session.code,
                "name": session.name,
                "date_start": None if session.date_start is None else session.date_start.isoformat(),
                "date_end": None if session.date_end is None else session.date_end.isoformat(),
            },
            "drivers": [driver.__dict__ for driver in self.drivers.values()],
            "laps": [lap.to_json() for lap in self.laps],
            "windows": [window.to_json() for window in self.windows],
        }

    @classmethod
    def from_json(cls, payload: dict) -> SessionLaps:
        session = payload["session"]
        drivers = [EntryDriver(**row) for row in payload["drivers"]]
        return cls(
            session=OpenF1Session(
                session_key=int(session["session_key"]),
                meeting_key=int(session["meeting_key"]),
                circuit_key=session["circuit_key"],
                code=str(session["code"]),
                name=str(session["name"]),
                date_start=parse_iso(session["date_start"]),
                date_end=parse_iso(session["date_end"]),
            ),
            year=int(payload["year"]),
            round=int(payload["round"]),
            drivers={driver.number: driver for driver in drivers},
            laps=tuple(Lap.from_json(row) for row in payload["laps"]),
            windows=tuple(Window.from_json(row) for row in payload["windows"]),
        )


def _cache_key(year: int, round_num: int, code: str) -> str:
    return f"{year}:{round_num}:{code}"


def _fetch(year: int, round_num: int, code: str) -> SessionLaps | None:
    with new_client() as client:
        session = find_session(client, year, round_num, code)
        if session is None:
            return None
        query = {"session_key": session.session_key}
        drivers = entry_list(client, session.session_key)
        laps = laps_from_openf1(get_json(client, "laps", query))
        messages = get_json(client, "race_control", query)
    deleted = deleted_laps(standing_deletions(messages), laps)
    return SessionLaps(
        session=session,
        year=year,
        round=round_num,
        drivers=drivers,
        laps=tuple(lap.marked_deleted() if (lap.driver, lap.number) in deleted else lap for lap in laps),
        windows=neutralised_windows(messages),
    )


def load_session_laps(year: int, round_num: int, code: str) -> SessionLaps | None:
    """The session's laps; None when the round has no such session.

    Raises :class:`~app.data.openf1.client.OpenF1UnavailableError` (or its
    live-lockout subclass) when OpenF1 cannot answer.
    """
    key = _cache_key(year, round_num, code)
    kept = analysis_cache.get(SESSION_LAPS_KIND, key, SESSION_LAPS_VERSION)
    if kept is not None:
        return SessionLaps.from_json(kept)
    loaded = _fetch(year, round_num, code)
    if loaded is None:
        return None
    if loaded.laps and loaded.drivers and session_ended(loaded.session):
        analysis_cache.put(SESSION_LAPS_KIND, key, SESSION_LAPS_VERSION, loaded.to_json())
    logger.info("openf1.session_laps.loaded", year=year, round=round_num, session=code, laps=len(loaded.laps))
    return loaded
