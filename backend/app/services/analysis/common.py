"""Payload pieces every Telemetry Lab answer shares.

Every answer says where its numbers came from (``source``) and, when there is
nothing to show, why not (``reason``), so the page never renders an empty chart
as if the session had no data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.api.errors import GENERIC_ERROR_MESSAGE

if TYPE_CHECKING:
    from app.data.openf1.laps import Lap
    from app.data.openf1.session_laps import SessionLaps
    from app.data.openf1.sessions import EntryDriver

SOURCE = "openf1"


@dataclass(frozen=True)
class SessionRef:
    """A session of a round: ``code`` is one of the app's session codes (Q, R, SQ...)."""

    year: int
    round: int
    code: str


@dataclass(frozen=True)
class DriverLap:
    """A driver by three-letter code, and a lap number (None: the fastest valid lap)."""

    code: str
    lap: int | None = None


REASON_NO_SESSION = "no_session"
REASON_NO_DRIVER = "no_driver"
REASON_NO_LAP = "no_lap"
REASON_NO_TELEMETRY = "no_telemetry"
REASON_NO_STINTS = "no_stints"
REASON_OPENF1_LIVE = "openf1_live"
REASON_OPENF1_UNAVAILABLE = "openf1_unavailable"
REASON_LOADING = "loading"
REASON_ERROR = "error"

MESSAGES: dict[str, str] = {
    REASON_NO_SESSION: "OpenF1 has no such session for this round (yet).",
    REASON_NO_DRIVER: "That driver did not take part in this session.",
    REASON_NO_LAP: "No timed lap to show for that driver in this session.",
    REASON_NO_TELEMETRY: "OpenF1 has no car telemetry for this lap yet.",
    REASON_NO_STINTS: "No tyre stints are published for this race yet.",
    REASON_OPENF1_LIVE: (
        "OpenF1 is closed to the public while an F1 session is live. Sessions already analysed still load; "
        "try this one again after the session ends."
    ),
    REASON_OPENF1_UNAVAILABLE: "OpenF1 could not be reached. Try again shortly.",
    REASON_LOADING: "Still loading this session from OpenF1. This page will update when it is ready.",
    REASON_ERROR: GENERIC_ERROR_MESSAGE,
}


def unavailable(reason: str, **extra: object) -> dict:
    """An answer with nothing to show, saying why."""
    return {
        "available": False,
        "pending": reason == REASON_LOADING,
        "reason": reason,
        "message": MESSAGES[reason],
        "source": SOURCE,
        **extra,
    }


def session_json(session: SessionLaps) -> dict:
    return {
        "year": session.year,
        "round": session.round,
        "code": session.session.code,
        "name": session.session.name,
        "date_start": None if session.session.date_start is None else session.session.date_start.isoformat(),
    }


def driver_json(driver: EntryDriver) -> dict:
    return {
        "number": driver.number,
        "code": driver.code,
        "name": driver.name,
        "team": driver.team,
        "colour": driver.colour,
    }


def lap_json(lap: Lap, fastest: Lap | None) -> dict:
    """A lap's measured timing, and whether it is the driver's fastest valid lap."""
    return {
        "number": lap.number,
        "time": lap.time,
        "sectors": list(lap.sectors),
        "speed_traps": {"i1": lap.traps[0], "i2": lap.traps[1], "speed_trap": lap.traps[2]},
        "deleted": lap.deleted,
        "pit_out": lap.pit_out,
        "is_fastest": fastest is not None and fastest.number == lap.number,
    }


class AnalysisUnavailableError(Exception):
    """There is nothing to show, for one of the ``REASON_*`` reasons."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
