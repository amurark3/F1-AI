"""What the Telemetry Lab's pickers offer: a round's sessions, then a session's drivers and laps.

The session list comes from f1db's calendar, not OpenF1, so it still loads
while OpenF1 is closed for a live session and sessions already kept can be
picked. f1db sets no session times before 2024, so a weekend it lists none for
takes OpenF1's own list (OpenF1 starts in 2023, and those seasons are never
live). Drivers are listed quickest first, by best valid lap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.data.openf1.client import new_client
from app.data.openf1.sessions import ScheduledSession, weekend_schedule, weekend_sessions
from app.services.analysis.common import (
    REASON_NO_SESSION,
    SOURCE,
    AnalysisUnavailableError,
    driver_json,
    session_json,
)
from app.services.analysis.lap_selection import timed_laps
from app.services.analysis.loading import require_session
from app.services.analysis.qualifying import LABELS, qualifying_view

if TYPE_CHECKING:
    from app.services.analysis.common import SessionRef


def _openf1_schedule(year: int, round_num: int) -> tuple[ScheduledSession, ...]:
    with new_client() as client:
        return tuple(
            ScheduledSession(session.code, session.name, session.date_start)
            for session in weekend_sessions(client, year, round_num)
        )


def build_weekend(year: int, round_num: int, now: datetime | None = None) -> dict:
    sessions, source = weekend_schedule(year, round_num), "calendar"
    if not sessions:
        sessions, source = _openf1_schedule(year, round_num), SOURCE
    if not sessions:
        raise AnalysisUnavailableError(REASON_NO_SESSION)
    moment = now or datetime.now(UTC)
    return {
        "available": True,
        "pending": False,
        "source": source,
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
    segments, extra = qualifying_view(session) if session.session.code in LABELS else (None, {})
    drivers = []
    for driver in session.drivers.values():
        laps = timed_laps(session, driver.number)
        best = min((lap["time"] for lap in laps if not lap["deleted"]), default=None)
        drivers.append(
            {**driver_json(driver, session.year), "best": best, "laps": laps, **extra.get(driver.number, {})}
        )
    drivers.sort(key=lambda entry: (entry["best"] is None, entry["best"] or 0.0, entry["code"]))
    return {
        "available": True,
        "pending": False,
        "source": SOURCE,
        "session": session_json(session),
        **({} if segments is None else {"segments": segments}),
        "drivers": drivers,
    }
