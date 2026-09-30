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
  * feed data is rejected unless it was sampled *after the active session
    began* — OpenF1 serves a finished session's last rows indefinitely, but
    judging a sample by its age instead reads a quiet track as a dead feed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# How far back the gap and lap feeds are queried. Both are read only for their
# latest row per driver, so pulling a whole session is wasted bandwidth: Spain
# 2026 served 3.8 MB of intervals by the chequered flag, every poll.
GAP_FEED_WINDOW = timedelta(minutes=5)
LAP_FEED_WINDOW = timedelta(minutes=15)

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


def next_session_start(sessions: list[dict], now: datetime) -> datetime | None:
    """When the next session of this weekend opens, or None if none remain.

    The socket uses this to stop sleeping through lights out. Rate-limiting the
    calendar lookup to a flat interval left a five-minute hole at the start of
    every session: a page opened at 12:58 still reported "no session on track"
    two minutes into the race.
    """
    starts = [
        parse_iso(session.get("date_start"))
        for session in sessions
        if not session.get("is_cancelled")
    ]
    upcoming = [start for start in starts if start is not None and start > now]
    return min(upcoming) if upcoming else None


def newest_sample_time(rows: list[dict], key: str = "date") -> datetime | None:
    """The most recent timestamp across ``rows``, or None if there is none."""
    stamps = [parse_iso(row.get(key)) for row in rows]
    usable = [stamp for stamp in stamps if stamp is not None]
    return max(usable) if usable else None


def newest_feed_sample(feeds: list[tuple[list[dict] | None, str]]) -> datetime | None:
    """The newest timestamp across several feeds, each with its own date key.

    No single OpenF1 feed covers every session type: the gap feed is published
    for races only, while the position feed is change-driven and goes quiet
    whenever the order holds. Reading them together is what keeps practice,
    qualifying and a processional Grand Prix all looking live.
    """
    stamps = [newest_sample_time(rows or [], key) for rows, key in feeds]
    usable = [stamp for stamp in stamps if stamp is not None]
    return max(usable) if usable else None


def feed_belongs_to_session(newest: datetime | None, session_start: datetime) -> bool:
    """Whether the newest sample was produced by the session now on track.

    This replaced a wall-clock staleness gate. Both guard the same defect —
    OpenF1 serving a finished session's final rows forever — but age is the
    wrong question: the position feed only emits on a change, so Spain 2026
    left it untouched for 58 minutes mid-race and the tower went dark for 39%
    of the Grand Prix. Provenance is exact, and a row from this session is
    current however old it is, because nothing has happened to supersede it.

    Rows sampled before lights out are the pre-session feed (Spain opened its
    position feed 54 minutes early) and do not count as the session running.
    """
    return newest is not None and newest >= session_start


def derive_session_state(
    session: dict | None,
    now: datetime,
    has_session_data: bool,
    grace: timedelta = SESSION_END_GRACE,
) -> str:
    """Classify the session as ``live``, ``finished`` or ``standby``.

    ``live`` requires data from this session as well as an open window: the
    clock alone is never enough to claim a feed is delivering. An open window
    whose feed has not opened yet is ``standby`` *with a session name*, which
    is what lets the desk say "Race — awaiting feed" instead of the flatly
    wrong "no session on track".
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
    return "live" if has_session_data else "standby"


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
