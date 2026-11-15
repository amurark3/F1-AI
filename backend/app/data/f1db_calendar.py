"""The season calendar from f1db, in the shape FastF1's event schedule had.

FastF1's ``get_event_schedule`` counted against FastF1's 500-requests-an-hour
cap and revalidated every five minutes, and every OpenF1 reader went through
it. f1db's ``race`` table holds the same calendar on disk: rounds, venues and
each session's start in UTC (D1.3). Readers keep the columns they read before:

* ``RoundNumber``: ``race.round``.
* ``EventName``: the Grand Prix's full name ("Mexican Grand Prix").
* ``Location`` / ``Country``: the circuit's place and country ("Sepang",
  "Malaysia" for the 2026 Bahrain Grand Prix).
* ``CircuitId``: f1db's circuit id, the same every season.
* ``EventDate``: race day, naive (midnight), as FastF1 gave it.
* ``EventFormat``: ``"sprint"`` or ``"conventional"``.
* ``Session1`` .. ``Session5`` and ``Session1DateUtc`` .. ``Session5DateUtc``:
  the sessions in running order under FastF1's (and OpenF1's) names, starts
  naive UTC. f1db lists a session only on a weekend that has it, so a sprint
  weekend has sprint qualifying and the sprint where others have FP2 and FP3.

f1db records session times from 2024 on. An earlier weekend lists no sessions,
and ``EventDate`` is all a reader has.

A season f1db does not hold (the local file can trail a release) or an f1db
that cannot be read raises :class:`CalendarUnavailableError`, a ``ValueError``
as FastF1's was for an unknown season, so every reader treats it as the
unavailable calendar it already handles. There is no FastF1 fallback.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from app.data.f1db_source import connect

SPRINT_FORMAT = "sprint"
CONVENTIONAL_FORMAT = "conventional"
SESSION_SLOTS = 5

# (date column, time column, session name) for each session a weekend can have.
_SESSIONS = (
    ("free_practice_1_date", "free_practice_1_time", "Practice 1"),
    ("free_practice_2_date", "free_practice_2_time", "Practice 2"),
    ("free_practice_3_date", "free_practice_3_time", "Practice 3"),
    ("sprint_qualifying_date", "sprint_qualifying_time", "Sprint Qualifying"),
    ("sprint_race_date", "sprint_race_time", "Sprint"),
    ("qualifying_date", "qualifying_time", "Qualifying"),
    ("date", "time", "Race"),
)

_QUERY = """
    SELECT r.*, gp.full_name AS event_name, c.place_name AS location, co.name AS country
    FROM race r
    JOIN grand_prix gp ON gp.id = r.grand_prix_id
    JOIN circuit c ON c.id = r.circuit_id
    JOIN country co ON co.id = c.country_id
    WHERE r.year = ?
    ORDER BY r.round
"""


class CalendarUnavailableError(ValueError):
    """f1db cannot say what the season's calendar is."""


def _is_sprint(row: sqlite3.Row) -> bool:
    # 2023 on: the sprint has its own qualifying. 2021-22: the sprint set the grid.
    return row["sprint_qualifying_format"] is not None or row["qualifying_format"] == "SPRINT_RACE"


def _event(row: sqlite3.Row) -> dict:
    timed = sorted(
        (pd.Timestamp(f"{row[date]} {row[time]}"), name)
        for date, time, name in _SESSIONS
        if row[date] is not None and row[time] is not None
    )
    slots = [*timed, *[(pd.NaT, None)] * SESSION_SLOTS][:SESSION_SLOTS]
    event = {
        "RoundNumber": int(row["round"]),
        "EventName": row["event_name"],
        "Location": row["location"],
        "Country": row["country"],
        "CircuitId": row["circuit_id"],
        "EventDate": pd.Timestamp(row["date"]),
        "EventFormat": SPRINT_FORMAT if _is_sprint(row) else CONVENTIONAL_FORMAT,
    }
    for index, (start, name) in enumerate(slots, start=1):
        event[f"Session{index}"] = name
        event[f"Session{index}DateUtc"] = start
    return event


def season_schedule(year: int) -> pd.DataFrame:
    """The season's rounds, one row each, in round order (see the module docstring)."""
    try:
        with connect() as conn:
            rows = conn.execute(_QUERY, (year,)).fetchall()
    except sqlite3.Error as exc:
        raise CalendarUnavailableError(f"f1db cannot be read: {exc}") from exc
    if not rows:
        raise CalendarUnavailableError(f"f1db has no calendar for {year} yet")
    return pd.DataFrame([_event(row) for row in rows])
