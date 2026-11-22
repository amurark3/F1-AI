"""Every lap of a session, with deletions applied and neutralised periods attached.

Deletions come from race control's messages and, once they land, the FIA's
deleted-lap sheets, so every "fastest lap" pick made from these laps skips them.

This is the measured base of the Telemetry Lab: the picker lists these laps,
the track map and the comparison pick from them, and tyre degradation reads a
race's laps from here. One load is four OpenF1 requests after the session is
found (drivers, laps, race control), so a session that has ended and settled is
kept in :mod:`app.data.analysis_cache` and never asked for again.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import structlog

from app.data.analysis_cache import analysis_cache
from app.data.fia_documents.results import fia_deleted_laps
from app.data.openf1.client import get_json, new_client
from app.data.openf1.laps import Lap, laps_from_openf1
from app.data.openf1.qualifying_result import ResultRow, result_rows
from app.data.openf1.race_control import (
    SegmentWindow,
    Window,
    deleted_laps,
    lap_by_time,
    lap_seconds,
    neutralised_windows,
    segment_windows,
    standing_deletions,
)
from app.data.openf1.sessions import EntryDriver, OpenF1Session, entry_list, find_session, session_ended
from app.services.live_timing import parse_iso

logger = structlog.get_logger()

SESSION_LAPS_KIND = "session_laps"
# 3: untimed deletions placed by the message's "LAP n" (D3.1).
SESSION_LAPS_VERSION = 3
QUALIFYING_CODES = frozenset({"Q", "SQ"})
# App session code -> the session as the FIA's deleted-lap sheets print it.
# shortcut: the sprint names are assumed (no sprint weekend in the store yet); check them against one.
FIA_SESSION_NAMES = {
    "FP1": "Free Practice 1",
    "FP2": "Free Practice 2",
    "FP3": "Free Practice 3",
    "SQ": "Sprint Qualifying",
    "S": "Sprint",
    "Q": "Qualifying",
    "R": "Race",
}


@dataclass(frozen=True)
class SessionLaps:
    session: OpenF1Session
    year: int
    round: int
    drivers: dict[int, EntryDriver]
    laps: tuple[Lap, ...]
    windows: tuple[Window, ...]
    # Qualifying only: the three segment windows (none unless all were published) and the classification.
    segments: tuple[SegmentWindow, ...] = ()
    result: tuple[ResultRow, ...] = ()

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
            "segments": [window.to_json() for window in self.segments],
            "result": [row.to_json() for row in self.result],
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
            segments=tuple(SegmentWindow.from_json(row) for row in payload["segments"]),
            result=tuple(ResultRow.from_json(row) for row in payload["result"]),
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
        classification = get_json(client, "session_result", query) if code in QUALIFYING_CODES else []
    deleted = deleted_laps(standing_deletions(messages), laps, code)
    return SessionLaps(
        session=session,
        year=year,
        round=round_num,
        drivers=drivers,
        laps=tuple(lap.marked_deleted() if (lap.driver, lap.number) in deleted else lap for lap in laps),
        windows=neutralised_windows(messages),
        segments=segment_windows(messages),
        result=result_rows(classification),
    )


def _with_fia_deletions(loaded: SessionLaps) -> SessionLaps:
    """The laps with the FIA's deleted-lap sheets applied over race control's messages.

    A sheet names a lap by its time, as race control does. Its "PIT" and "OUT"
    rows carry none, and neither lap is ever a fastest one, so they mark nothing.
    """
    rows = fia_deleted_laps(loaded.year, loaded.round, FIA_SESSION_NAMES[loaded.session.code])
    deleted = {
        (lap.driver, lap.number)
        for row in rows
        if row.lap_time is not None
        and (lap := lap_by_time(list(loaded.laps_of(row.car)), lap_seconds(row.lap_time))) is not None
    }
    if not deleted:
        return loaded
    laps = tuple(lap.marked_deleted() if (lap.driver, lap.number) in deleted else lap for lap in loaded.laps)
    return replace(loaded, laps=laps)


def load_session_laps(year: int, round_num: int, code: str) -> SessionLaps | None:
    """The session's laps; None when the round has no such session.

    Raises :class:`~app.data.openf1.client.OpenF1UnavailableError` (or its
    live-lockout subclass) when OpenF1 cannot answer.
    """
    key = _cache_key(year, round_num, code)
    kept = analysis_cache.get(SESSION_LAPS_KIND, key, SESSION_LAPS_VERSION)
    if kept is not None:
        return _with_fia_deletions(SessionLaps.from_json(kept))
    loaded = _fetch(year, round_num, code)
    if loaded is None:
        return None
    # Kept as OpenF1 published it: an FIA sheet that lands later still applies on the next load.
    if loaded.laps and loaded.drivers and session_ended(loaded.session):
        analysis_cache.put(SESSION_LAPS_KIND, key, SESSION_LAPS_VERSION, loaded.to_json())
    logger.info("openf1.session_laps.loaded", year=year, round=round_num, session=code, laps=len(loaded.laps))
    return _with_fia_deletions(loaded)
