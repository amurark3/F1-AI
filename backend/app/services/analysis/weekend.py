"""What the Telemetry Lab's pickers offer: a round's sessions, then a session's drivers and laps.

The session list comes from FastF1's calendar, not OpenF1, so it still loads
while OpenF1 is closed for a live session and sessions already kept can be
picked. Drivers are listed quickest first, by best valid lap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.data.openf1.sessions import weekend_schedule
from app.services.analysis.common import (
    REASON_NO_SESSION,
    SOURCE,
    AnalysisUnavailableError,
    driver_json,
    session_json,
)
from app.services.analysis.lap_selection import timed_laps
from app.services.analysis.loading import require_session

if TYPE_CHECKING:
    from app.services.analysis.common import SessionRef


def build_weekend(year: int, round_num: int, now: datetime | None = None) -> dict:
    sessions = weekend_schedule(year, round_num)
    if not sessions:
        raise AnalysisUnavailableError(REASON_NO_SESSION)
    moment = now or datetime.now(UTC)
    return {
        "available": True,
        "pending": False,
        "source": "calendar",
        "year": year,
        "round": round_num,
        "sessions": [
            {
                "code": session.code,
                "name": session.name,
                "date_start": None if session.start is None else session.start.isoformat(),
                "started": session.start is not None and session.start <= moment,
            }
            for session in sessions
        ],
    }


def build_lap_list(ref: SessionRef) -> dict:
    session = require_session(ref)
    drivers = []
    for driver in session.drivers.values():
        laps = timed_laps(session, driver.number)
        best = min((lap["time"] for lap in laps if not lap["deleted"]), default=None)
        drivers.append({**driver_json(driver), "best": best, "laps": laps})
    drivers.sort(key=lambda entry: (entry["best"] is None, entry["best"] or 0.0, entry["code"]))
    return {
        "available": True,
        "pending": False,
        "source": SOURCE,
        "session": session_json(session),
        "drivers": drivers,
    }
