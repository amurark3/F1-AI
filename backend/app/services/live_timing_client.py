"""OpenF1 access for the live-timing WebSocket.

Thin I/O layer: every decision about which session is live and whether its
data can be trusted lives in ``live_timing``, which is pure and unit-tested.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import fastf1
import httpx
import structlog

from app.config import OPENF1_HTTP_TIMEOUT_SECONDS
from app.services.live_timing import (
    GAP_FEED_WINDOW,
    LAP_FEED_WINDOW,
    build_positions,
    feed_belongs_to_session,
    match_meeting,
    newest_feed_sample,
    next_session_start,
    parse_iso,
    select_active_session,
)

logger = structlog.get_logger()

OPENF1_BASE = "https://api.openf1.org/v1"

# Driver metadata is static for a session, so it is fetched once per session.
_driver_cache: dict[str, dict[int, dict]] = {}


@dataclass(frozen=True)
class TimingSnapshot:
    """One poll of a running session's feeds."""

    rows: list[dict]
    #: When the newest sample behind these rows was taken.
    sampled_at: datetime
    #: Highest lap completed, or None — OpenF1 publishes no total-lap figure.
    lap: int | None


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


@dataclass(frozen=True)
class SessionLookup:
    """What one calendar lookup taught the socket.

    ``next_start`` matters as much as ``active``: without it the loop had no
    way to tell "nothing is on track for hours" from "the race starts in two
    minutes", so it rate-limited both the same way and slept through lights
    out.
    """

    active: ActiveSession | None
    next_start: datetime | None


EMPTY_LOOKUP = SessionLookup(active=None, next_start=None)


async def _weekend_sessions(
    client: httpx.AsyncClient,
    year: int,
    round_num: int,
    location: str,
    event_date: datetime,
) -> tuple[list[dict], dict] | None:
    """The OpenF1 session list and meeting for a round, or None if unresolved."""
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
    return sessions, meeting


def _build_active(session: dict, meeting: dict, event_name: str) -> ActiveSession | None:
    """Turn an OpenF1 session row into an ``ActiveSession``, or None if unusable."""
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


async def resolve_session_window(
    year: int,
    round_num: int,
    now: datetime | None = None,
) -> SessionLookup:
    """Find the session running right now for a round, and when the next opens.

    ``active`` is None whenever nothing is on track — between sessions, before
    the weekend, and after the chequered flag.
    """
    identity = await asyncio.to_thread(_event_identity, year, round_num)
    if identity is None:
        return EMPTY_LOOKUP
    location, event_date, event_name = identity

    moment = now or datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
        weekend = await _weekend_sessions(client, year, round_num, location, event_date)
    if weekend is None:
        return EMPTY_LOOKUP
    sessions, meeting = weekend

    upcoming = next_session_start(sessions, moment)
    session = select_active_session(sessions, moment)
    if session is None:
        return SessionLookup(active=None, next_start=upcoming)

    return SessionLookup(active=_build_active(session, meeting, event_name), next_start=upcoming)


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


def _recent(session_key: str, moment: datetime, span: timedelta, key: str = "date") -> dict:
    """Query params limiting a feed to its most recent rows.

    OpenF1 has no "latest row" endpoint, so an unfiltered read returns the
    whole session — 26,935 interval rows by the end of a Grand Prix, re-fetched
    every eight seconds. Both windowed feeds are read only for their last row
    per driver, so the history is pure waste.
    """
    return {"session_key": session_key, f"{key}>": (moment - span).isoformat()}


def _highest_lap(rows: list[dict] | None) -> int | None:
    """Highest lap completed, or None if unavailable.

    OpenF1 publishes no total-lap count, so the tower shows a lap number
    without a denominator rather than inventing one.
    """
    laps = [row.get("lap_number") for row in (rows or []) if row.get("lap_number")]
    return max(laps) if laps else None


async def poll_timing(
    session: ActiveSession,
    now: datetime | None = None,
    last_lap: int | None = None,
) -> TimingSnapshot | None:
    """One poll of a running session, or None when its feed has not opened.

    The guard is provenance, not age: a sample taken after lights out is
    current however long ago it arrived, because the position feed only emits
    on a change. What must never render is a *previous* session's final
    classification, which OpenF1 serves forever.

    ``last_lap`` is the caller's previous lap count, held over when the
    windowed lap feed comes back empty — a red flag longer than the window, or
    the run-off after the chequered flag.
    """
    moment = now or datetime.now(timezone.utc)
    key = session.session_key
    async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
        drivers = await _fetch_drivers(client, key)
        positions, intervals, laps = await asyncio.gather(
            _get_json(client, "position", {"session_key": key}),
            _get_json(client, "intervals", _recent(key, moment, GAP_FEED_WINDOW)),
            _get_json(client, "laps", _recent(key, moment, LAP_FEED_WINDOW, key="date_start")),
        )

    sampled_at = newest_feed_sample([
        (positions, "date"),
        (intervals, "date"),
        (laps, "date_start"),
    ])
    if not feed_belongs_to_session(sampled_at, session.date_start):
        logger.info("openf1.feed_not_open", session_key=key, newest=str(sampled_at))
        return None
    if not positions:
        return None

    published = _highest_lap(laps)
    return TimingSnapshot(
        rows=build_positions(positions, intervals or [], drivers),
        sampled_at=sampled_at,
        lap=last_lap if published is None else published,
    )
