"""Which OpenF1 session a round's qualifying, sprint or race is.

A round is found the way the Stints tab has always found it: FastF1's calendar
(which still loads) gives the circuit location and date, and the OpenF1 meeting
is matched on those, never on its position in the season. A session is then
picked **by name**. ``session_type`` reads "Race" for a sprint and "Qualifying"
for sprint qualifying, so it cannot tell them apart.

The names are OpenF1's own, which are not FastF1's: OpenF1 calls 2023's sprint
shootout "Sprint Qualifying" too, so each app code maps to a set of names and
FastF1 names are never passed through.

``entry_list`` keeps OpenF1's own words for each car ("Ryo HIRAKAWA", "Haas F1
Team"), which is what the session caches store. ``canonical_entry`` is what a
payload prints: f1db's driver and team names ("Ryō Hirakawa", "Haas"), from the
car's code, number and name (:mod:`app.data.canonical_names`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import fastf1
import pandas as pd

from app.config import ANALYSIS_SESSION_SETTLE_MINUTES
from app.data.canonical_names import driver_identity, team_display_name
from app.data.openf1.client import get_json
from app.services.live_timing import match_meeting, parse_iso

if TYPE_CHECKING:
    import httpx

# App session code -> the names OpenF1 has used for it.
SESSION_NAMES: dict[str, frozenset[str]] = {
    "FP1": frozenset({"Practice 1"}),
    "FP2": frozenset({"Practice 2"}),
    "FP3": frozenset({"Practice 3"}),
    "SQ": frozenset({"Sprint Qualifying", "Sprint Shootout"}),
    "S": frozenset({"Sprint"}),
    "Q": frozenset({"Qualifying"}),
    "R": frozenset({"Race"}),
}
SESSION_CODES = tuple(SESSION_NAMES)
# Sessions run like a race: laps on a long run, tyre stints, a classification
# in finishing order.
RACE_CODES = frozenset({"S", "R"})
# Sessions whose best laps are the point: practice and qualifying of both kinds.
LAP_TIME_CODES = frozenset(SESSION_CODES) - RACE_CODES

DEFAULT_TEAM_COLOUR = "#8A8F98"


@dataclass(frozen=True)
class OpenF1Session:
    """One session of a weekend, as OpenF1 knows it."""

    session_key: int
    meeting_key: int
    circuit_key: int | None
    code: str
    name: str
    date_start: datetime | None
    date_end: datetime | None


@dataclass(frozen=True)
class ScheduledSession:
    """A session as the calendar lists it, before or after it has run."""

    code: str
    name: str
    start: datetime | None


@dataclass(frozen=True)
class EntryDriver:
    """A car in a session: its number, three-letter code, team and team colour."""

    number: int
    code: str
    name: str
    team: str
    colour: str


def session_code(name: object) -> str | None:
    """The app code for an OpenF1 session name; None for testing days and the like."""
    return next((code for code, names in SESSION_NAMES.items() if name in names), None)


def _event_row(year: int, round_num: int) -> pd.Series | None:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    matches = schedule[schedule["RoundNumber"] == round_num]
    return None if matches.empty else matches.iloc[0]


def _utc(value: object) -> datetime | None:
    if not isinstance(value, pd.Timestamp) or pd.isna(value):
        return None
    return value.to_pydatetime().replace(tzinfo=UTC)


def event_identity(year: int, round_num: int) -> tuple[str, datetime] | None:
    """The round's circuit location and date, from FastF1's calendar."""
    row = _event_row(year, round_num)
    if row is None:
        return None
    return str(row["Location"]), row["EventDate"].to_pydatetime().replace(tzinfo=UTC)


def weekend_schedule(year: int, round_num: int) -> tuple[ScheduledSession, ...]:
    """The round's sessions from FastF1's calendar, which loads while OpenF1 is closed for a live session."""
    row = _event_row(year, round_num)
    if row is None:
        return ()
    sessions = []
    for index in range(1, 6):
        name = row.get(f"Session{index}")
        code = session_code(name)
        if code is not None:
            sessions.append(ScheduledSession(code=code, name=str(name), start=_utc(row.get(f"Session{index}DateUtc"))))
    return tuple(sessions)


def find_meeting(client: httpx.Client, year: int, round_num: int) -> dict | None:
    identity = event_identity(year, round_num)
    if identity is None:
        return None
    location, event_date = identity
    return match_meeting(get_json(client, "meetings", {"year": year}), location, event_date)


def _session(row: dict) -> OpenF1Session | None:
    code = session_code(row.get("session_name"))
    if code is None or row.get("is_cancelled") or row.get("session_key") is None:
        return None
    circuit_key = row.get("circuit_key")
    return OpenF1Session(
        session_key=int(row["session_key"]),
        meeting_key=int(row.get("meeting_key") or 0),
        circuit_key=None if circuit_key is None else int(circuit_key),
        code=code,
        name=str(row.get("session_name")),
        date_start=parse_iso(row.get("date_start")),
        date_end=parse_iso(row.get("date_end")),
    )


def weekend_sessions(client: httpx.Client, year: int, round_num: int) -> tuple[OpenF1Session, ...]:
    """Every session of the round that was not cancelled, in running order."""
    meeting = find_meeting(client, year, round_num)
    if meeting is None:
        return ()
    rows = get_json(client, "sessions", {"meeting_key": meeting["meeting_key"]})
    sessions = [session for row in rows if (session := _session(row)) is not None]
    return tuple(sorted(sessions, key=lambda item: item.date_start or datetime.max.replace(tzinfo=UTC)))


def find_session(client: httpx.Client, year: int, round_num: int, code: str) -> OpenF1Session | None:
    return next((session for session in weekend_sessions(client, year, round_num) if session.code == code), None)


def session_ended(session: OpenF1Session, now: datetime | None = None) -> bool:
    """Whether the session is over and settled, so its rows are final and may be kept."""
    if session.date_end is None:
        return False
    moment = now or datetime.now(UTC)
    return moment >= session.date_end + timedelta(minutes=ANALYSIS_SESSION_SETTLE_MINUTES)


def _colour(value: object) -> str:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
        return DEFAULT_TEAM_COLOUR
    return f"#{text.upper()}"


def entry_list(client: httpx.Client, session_key: int) -> dict[int, EntryDriver]:
    """The cars in a session, by number."""
    drivers: dict[int, EntryDriver] = {}
    for row in get_json(client, "drivers", {"session_key": session_key}):
        number = row.get("driver_number")
        if number is None:
            continue
        drivers[int(number)] = EntryDriver(
            number=int(number),
            code=str(row.get("name_acronym") or number).strip().upper(),
            name=str(row.get("full_name") or row.get("broadcast_name") or "").strip(),
            team=str(row.get("team_name") or "").strip(),
            colour=_colour(row.get("team_colour")),
        )
    return drivers


def canonical_entry(driver: EntryDriver, year: int) -> EntryDriver:
    """The car under f1db's driver and team names; OpenF1's number, code and colour are kept.

    An unresolved driver keeps OpenF1's name in display case ("Ryo HIRAKAWA" ->
    "Ryo Hirakawa"), and a team f1db does not know keeps OpenF1's spelling.
    """
    identity = driver_identity(year, code=driver.code, number=driver.number, name=driver.name)
    return replace(driver, name=identity.name, team=team_display_name(year, driver.team))
