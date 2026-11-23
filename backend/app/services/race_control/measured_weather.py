"""OpenF1's trackside readings beside each finished session's forecast.

The forecast payload (:mod:`session_weather`) is Open-Meteo's and stays as it is.
Each row gains ``measured`` (the station's summary, only once the session is
over and OpenF1 has readings) and ``measured_note`` (why there is none).

Finished sessions are read from the session store first: OpenF1 refuses every
request while a session is live, so during the Race the practice and
qualifying sessions already kept still show their readings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import structlog

from app.data.openf1 import session_store
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import OpenF1Session, session_code, session_ended, weekend_sessions
from app.data.openf1.track_weather import summarise_track_weather

if TYPE_CHECKING:
    from datetime import datetime

    import httpx

logger = structlog.get_logger()

NOTE_AFTER_FLAG = "OpenF1 closes its feed while a session runs; trackside readings follow once it ends."
NOTE_NO_READINGS = "OpenF1 has no weather readings for this session."
NOTE_OFFLINE = "OpenF1 is unavailable right now."


def _with(row: dict, measured: dict | None = None, note: str | None = None) -> dict:
    return {**row, "measured": measured, "measured_note": note}


def _unavailable(error: OpenF1UnavailableError, year: int, round_num: int, session: str | None) -> None:
    logger.warning(
        "race_control.measured_weather.unavailable", year=year, round=round_num, session=session, error=str(error)
    )


class _Weekend(NamedTuple):
    year: int
    round_num: int
    now: datetime | None


def _measure(client: httpx.Client, row: dict, session: OpenF1Session | None, weekend: _Weekend) -> dict:
    if session is None:
        return _with(row, note=NOTE_NO_READINGS)
    if not session_ended(session, weekend.now):
        return _with(row, note=NOTE_AFTER_FLAG)
    try:
        readings = get_json(client, "weather", {"session_key": session.session_key})
    except OpenF1UnavailableError as exc:
        _unavailable(exc, weekend.year, weekend.round_num, row["name"])
        return _with(row, note=NOTE_OFFLINE)
    measured = summarise_track_weather(readings, session.date_start, session.date_end)
    return _with(row, measured, None if measured else NOTE_NO_READINGS)


def _sessions_by_code(client: httpx.Client, year: int, round_num: int, wanted: set[str | None]) -> dict | None:
    """The kept sessions, topped up from OpenF1 once if any wanted code is missing; None when that fails."""
    kept = {record["code"]: OpenF1Session(**record) for record in session_store.weekend(year, round_num)}
    if wanted <= kept.keys() | {None}:
        return kept
    try:
        return {session.code: session for session in weekend_sessions(client, year, round_num)} | kept
    except OpenF1UnavailableError as exc:
        _unavailable(exc, year, round_num, None)
        return None


def with_measured(session_weather: dict, year: int, race: dict | None, now: datetime | None = None) -> dict:
    """A new session-weather payload whose rows carry ``measured`` and ``measured_note``."""
    rows = session_weather.get("sessions", [])
    round_num = (race or {}).get("round")
    notes = {"live": NOTE_AFTER_FLAG}
    done = [row for row in rows if row["phase"] == "done"]
    if not done or not round_num:
        return {**session_weather, "sessions": [_with(row, note=notes.get(row["phase"])) for row in rows]}
    codes = {row["name"]: session_code(row["name"]) for row in done}
    sessions: list[dict] = []
    with new_client() as client:
        found = _sessions_by_code(client, year, round_num, set(codes.values()))
        for row in rows:
            if row["phase"] != "done":
                sessions.append(_with(row, note=notes.get(row["phase"])))
            elif found is None:
                sessions.append(_with(row, note=NOTE_OFFLINE))
            else:
                sessions.append(_measure(client, row, found.get(codes[row["name"]]), _Weekend(year, round_num, now)))
    return {**session_weather, "sessions": sessions}
