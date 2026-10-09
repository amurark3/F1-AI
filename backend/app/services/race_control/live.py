"""Whether a session is on track right now — the one place the desk reads the clock.

``status == "in_progress"`` spans Friday practice to Sunday evening, so it cannot
answer "is anything running?". The LIVE pill, the desk focus and the strategy
phase all ask that question, and all ask it here, so they cannot disagree.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.live_timing import scheduled_session_now


def live_session(race: dict | None) -> str | None:
    """Name of the session on track for this event, or None between sessions."""
    return scheduled_session_now((race or {}).get("sessions", {}), datetime.now(timezone.utc))


def build_live_status(race: dict | None) -> dict:
    """Report whether a session is on track, not merely whether the weekend began.

    Using the weekend status here lit the LIVE pill for three days straight.
    """
    session = live_session(race)
    return {
        "connected": session is not None,
        "label": f"{session} in progress" if session else "Standby",
        "session": session,
    }
