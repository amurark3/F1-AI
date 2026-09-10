"""OpenF1 access for the live-timing WebSocket.

Thin I/O layer: every decision about which session is live and whether its
data can be trusted lives in ``live_timing``, which is pure and unit-tested.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import fastf1
import httpx
import structlog

from app.config import OPENF1_HTTP_TIMEOUT_SECONDS
from app.services.live_timing import (
    build_positions,
    is_fresh,
    match_meeting,
    parse_iso,
    select_active_session,
)

logger = structlog.get_logger()

OPENF1_BASE = "https://api.openf1.org/v1"

# Driver metadata is static for a session, so it is fetched once per session.
_driver_cache: dict[str, dict[int, dict]] = {}


@dataclass(frozen=True)
class ActiveSession:
    """The session currently running at a race weekend."""

    session_key: str
    session_name: str
    session_type: str
    meeting_name: str
    date_start: datetime
    date_end: datetime

    @property
    def raw(self) -> dict:
        """The shape ``live_timing.derive_session_state`` expects."""
        return {
            "date_start": self.date_start.isoformat(),
            "date_end": self.date_end.isoformat(),
        }


async def _get_json(client: httpx.AsyncClient, path: str, params: dict) -> list | None:
    """GET a JSON list from OpenF1, or None when the response is unusable."""
    try:
        response = await client.get(f"{OPENF1_BASE}/{path}", params=params)
    except httpx.HTTPError as exc:
        logger.warning("openf1.request_failed", path=path, error=str(exc))
        return None
    if response.status_code != 200:
        logger.warning("openf1.bad_status", path=path, status=response.status_code)
        return None
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("openf1.bad_json", path=path, error=str(exc))
        return None
    return payload if isinstance(payload, list) else None


def _event_identity(year: int, round_num: int) -> tuple[str, datetime, str] | None:
    """Resolve a round to its circuit location, date and name via FastF1.

    Blocking — callers wrap this in a thread.
    """
    # OSError covers requests.RequestException, which subclasses it — FastF1
    # reaches the network here and a transient failure must not kill the socket.
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except (ValueError, KeyError, OSError) as exc:
        logger.warning("fastf1.schedule_failed", year=year, error=str(exc))
        return None

    matches = schedule[schedule["RoundNumber"] == round_num]
    if matches.empty:
        return None
    row = matches.iloc[0]
    event_date = row["EventDate"].to_pydatetime().replace(tzinfo=timezone.utc)
    return str(row["Location"]), event_date, str(row["EventName"])


async def resolve_active_session(
    year: int,
    round_num: int,
    now: datetime | None = None,
) -> ActiveSession | None:
    """Find the session running right now for a round, or None.

    Returns None whenever nothing is on track — between sessions, before the
    weekend, and after the chequered flag.
    """
    identity = await asyncio.to_thread(_event_identity, year, round_num)
    if identity is None:
        return None
    location, event_date, event_name = identity

    moment = now or datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
        meetings = await _get_json(client, "meetings", {"year": year})
        if not meetings:
            return None

        meeting = match_meeting(meetings, location, event_date)
        if meeting is None:
            logger.warning("openf1.meeting_unmatched", year=year, round=round_num, location=location)
            return None

        sessions = await _get_json(client, "sessions", {"meeting_key": meeting["meeting_key"]})
        if not sessions:
            return None

    session = select_active_session(sessions, moment)
    if session is None:
        return None

    start = parse_iso(session.get("date_start"))
    end = parse_iso(session.get("date_end"))
    if start is None or end is None:
        return None

    return ActiveSession(
        session_key=str(session["session_key"]),
        session_name=str(session.get("session_name") or session.get("session_type") or "Session"),
        session_type=str(session.get("session_type") or ""),
        meeting_name=str(meeting.get("meeting_name") or event_name),
        date_start=start,
        date_end=end,
    )


async def _fetch_drivers(client: httpx.AsyncClient, session_key: str) -> dict[int, dict]:
    """Driver metadata for a session, cached for the life of the process."""
    if session_key in _driver_cache:
        return _driver_cache[session_key]

    rows = await _get_json(client, "drivers", {"session_key": session_key})
    drivers = {
        row["driver_number"]: row
        for row in (rows or [])
        if row.get("driver_number") is not None
    }
    if drivers:
        _driver_cache[session_key] = drivers
    return drivers


async def poll_positions(session_key: str, now: datetime | None = None) -> list[dict] | None:
    """Current timing-tower rows, or None when there is no live data.

    Returns None for stale samples rather than presenting a finished session's
    final classification as a live feed.
    """
    moment = now or datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
        drivers = await _fetch_drivers(client, session_key)
        positions, intervals = await asyncio.gather(
            _get_json(client, "position", {"session_key": session_key}),
            _get_json(client, "intervals", {"session_key": session_key}),
        )

    if not positions:
        return None
    if not is_fresh(positions, moment):
        logger.info("openf1.stale_positions", session_key=session_key)
        return None

    return build_positions(positions, intervals or [], drivers)


async def fetch_current_lap(session_key: str) -> int | None:
    """Highest lap number completed in the session, or None if unavailable.

    OpenF1 publishes no total-lap count, so the tower shows a lap number
    without a denominator rather than inventing one.
    """
    async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
        rows = await _get_json(client, "laps", {"session_key": session_key})

    laps = [row.get("lap_number") for row in (rows or []) if row.get("lap_number")]
    return max(laps) if laps else None
