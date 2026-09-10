"""Pure logic for resolving and validating live-timing sessions.

Nothing here performs I/O, so every rule is directly testable. The HTTP calls
that feed these functions live in ``live_timing_client``.

Three rules exist because the timing tower once rendered the Belgian Grand
Prix's final classification as a live Dutch Grand Prix feed:

  * meetings are matched by circuit location, never by round index — FastF1
    and OpenF1 disagree on which events exist, so positions drift apart
  * the active session is whichever session's window contains *now*, never
    "the first session whose type is Race" (that is the Sprint on a sprint
    weekend, and a finished race every other day of it)
  * position data is rejected unless it was sampled seconds ago — OpenF1
    serves a finished session's last rows indefinitely
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Position samples older than this are a replay of a finished session, not a
# live feed. OpenF1 pushes updates every few seconds during a session.
STALE_AFTER = timedelta(minutes=5)

# Sessions routinely run past their scheduled end (red flags, safety cars).
SESSION_END_GRACE = timedelta(minutes=15)

# A meeting's own window is only a day-level hint, so the location fallback
# accepts any event date inside the race weekend.
MEETING_DATE_TOLERANCE = timedelta(days=4)

# Schedule-derived session lengths, used where only start times are known
# (FastF1 publishes no end times). Deliberately generous.
DEFAULT_SESSION_MINUTES = 75
SESSION_MINUTES: dict[str, int] = {
    "practice": 75,
    "qualifying": 75,
    "sprint qualifying": 75,
    "sprint shootout": 75,
    "sprint": 75,
    "race": 150,
}

UNKNOWN_GAP = "—"
LEADER_GAP = "LEADER"


def parse_iso(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Naive timestamps are assumed to be UTC, matching every upstream feed.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise(value: object) -> str:
    return str(value or "").strip().lower()


def match_meeting(
    meetings: list[dict],
    location: str,
    event_date: datetime | None = None,
) -> dict | None:
    """Find the OpenF1 meeting for a circuit location.

    Positional lookup (``meetings[round - 1]``) is unusable: the two calendars
    disagree about which events exist, so a mismatch silently shifts every
    later round onto a different race. Location is stable across both sources.
    """
    target = _normalise(location)
    if target:
        for meeting in meetings:
            if _normalise(meeting.get("location")) == target:
                return meeting

    if event_date is None:
        return None

    for meeting in meetings:
        start = parse_iso(meeting.get("date_start"))
        if start is not None and abs(start - event_date) <= MEETING_DATE_TOLERANCE:
            return meeting
    return None


def select_active_session(
    sessions: list[dict],
    now: datetime,
    grace: timedelta = SESSION_END_GRACE,
) -> dict | None:
    """Return the session whose window contains ``now``, or None.

    Any session type qualifies — a timing tower should follow practice and
    qualifying, not only the Grand Prix.
    """
    for session in sessions:
        if session.get("is_cancelled"):
            continue
        start = parse_iso(session.get("date_start"))
        end = parse_iso(session.get("date_end"))
        if start is None or end is None:
            continue
        if start <= now <= end + grace:
            return session
    return None


def newest_sample_time(rows: list[dict], key: str = "date") -> datetime | None:
    """The most recent timestamp across ``rows``, or None if there is none."""
    stamps = [parse_iso(row.get(key)) for row in rows]
    usable = [stamp for stamp in stamps if stamp is not None]
    return max(usable) if usable else None


def is_fresh(rows: list[dict], now: datetime, max_age: timedelta = STALE_AFTER) -> bool:
    """Whether ``rows`` were sampled recently enough to present as live.

    Without this guard a session that ended weeks ago renders as a live tower,
    because OpenF1 keeps returning its final rows.
    """
    newest = newest_sample_time(rows)
    return newest is not None and (now - newest) < max_age


def derive_session_state(
    session: dict | None,
    now: datetime,
    has_fresh_data: bool,
    grace: timedelta = SESSION_END_GRACE,
) -> str:
    """Classify the session as ``live``, ``finished`` or ``standby``.

    ``live`` requires fresh data as well as an open window: the clock alone is
    never enough to claim a feed is delivering.
    """
    if session is None:
        return "standby"
    start = parse_iso(session.get("date_start"))
    end = parse_iso(session.get("date_end"))
    if start is None or end is None:
        return "standby"
    if now < start:
        return "standby"
    if now > end + grace:
        return "finished"
    return "live" if has_fresh_data else "standby"


def _latest_per_driver(rows: list[dict]) -> dict[int, dict]:
    """Collapse a position feed to the last row seen for each driver."""
    latest: dict[int, dict] = {}
    for row in rows:
        number = row.get("driver_number")
        if number is not None:
            latest = {**latest, number: row}
    return latest


def _format_gap(raw: object, position: int) -> str:
    try:
        gap = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        gap = None
    if position == 1 or gap == 0.0:
        return LEADER_GAP
    if gap is None:
        return UNKNOWN_GAP
    return f"+{gap:.3f}"


def build_positions(
    position_rows: list[dict],
    interval_rows: list[dict],
    drivers: dict[int, dict],
) -> list[dict]:
    """Build the timing-tower rows from raw OpenF1 payloads."""
    intervals = {
        row["driver_number"]: row
        for row in interval_rows
        if row.get("driver_number") is not None
    }
    latest = _latest_per_driver(position_rows)

    return [
        {
            "position": row.get("position", 0),
            "driver": drivers.get(number, {}).get("name_acronym") or str(number),
            "driver_number": number,
            "team": drivers.get(number, {}).get("team_name"),
            "gap": _format_gap(
                intervals.get(number, {}).get("gap_to_leader"),
                row.get("position", 0),
            ),
            "last_lap": None,
            "pit_stops": None,
        }
        for number, row in sorted(latest.items(), key=lambda item: item[1].get("position", 99))
    ]


def _session_window_minutes(name: str) -> int:
    key = _normalise(name)
    for prefix, minutes in SESSION_MINUTES.items():
        if key.startswith(prefix):
            return minutes
    return DEFAULT_SESSION_MINUTES


def scheduled_session_now(sessions: dict[str, str], now: datetime) -> str | None:
    """Name the session scheduled to be running at ``now``, from start times alone.

    FastF1 publishes no end times, so windows are derived from typical session
    lengths. This answers "is something on track?" for status pills; it is not
    evidence that a feed is delivering — use ``derive_session_state`` for that.
    """
    for name, start_iso in sessions.items():
        start = parse_iso(start_iso)
        if start is None:
            continue
        if start <= now <= start + timedelta(minutes=_session_window_minutes(name)):
            return name
    return None
