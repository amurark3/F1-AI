"""A session's deleted lap times ("Infringement - Qualifying Deleted Lap Times").

::

    Session Qualifying
    Fact The F1 Cars below did not use the track at turns 1, 4, 9, 11, 12, 13 and 14.
    No. Turn Car Driver Competitor Time of Day Lap Time
    1 4 18 Lance Stroll Aston Martin Aramco F1 Team 15:02:38 1:29.337
    3 1 11 Sergio Perez Cadillac Formula 1 Team 15:15:49 PIT

The sheet gives no lap number: a lap is named by the time of day it was set,
local to the circuit, on the document's date, and its lap time. "PIT" (a lap
ending in the pit lane) and "OUT" (an out-lap) print no time, so they have none
to delete from a ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.fia_documents.parsers.fields import document_date, document_number
from app.data.fia_documents.text import DocumentParseError, clean, squash

REASON_TRACK_LIMITS = "track_limits"
REASON_YELLOW_FLAGS = "yellow_flags"
REASON_OTHER = "other"

_SESSION = re.compile(r"^\s*Session\s+(?P<name>.+?)\s*$", re.MULTILINE)
_FACT = re.compile(r"^\s*Fact\s+(?P<text>.+?)^\s*No\.\s+Turn\b", re.MULTILINE | re.DOTALL)
_ROW = re.compile(
    r"^\s*(?P<row>\d{1,3})\s+(?P<turn>\d{1,2})\s+(?P<car>\d{1,2})\s+(?P<entrant>.+?)\s+"
    r"(?P<time_of_day>\d{1,2}:\d{2}:\d{2})\s+(?P<lap_time>\d{1,2}:\d{2}\.\d{3}|PIT|OUT)\s*$",
    re.MULTILINE,
)
_NO_TIME = frozenset({"PIT", "OUT"})
_TRACK_LIMITS = re.compile(r"did\s+not\s+use\s+the\s+track", re.IGNORECASE)
_YELLOW = re.compile(r"yellow\s+flag", re.IGNORECASE)


@dataclass(frozen=True)
class DeletedLap:
    car: int
    turn: int
    #: Driver and team as printed.
    entrant: str
    #: Local time of day the lap was set ("15:02:38").
    time_of_day: str
    #: "1:29.337"; ``None`` for an in-lap ("PIT") or an out-lap ("OUT").
    lap_time: str | None


@dataclass(frozen=True)
class DeletedLaps:
    document: int | None
    session: str
    #: The day ``time_of_day`` belongs to, ISO.
    date: str | None
    reason: str
    fact: str
    laps: tuple[DeletedLap, ...]


def _reason(fact: str) -> str:
    if _TRACK_LIMITS.search(fact):
        return REASON_TRACK_LIMITS
    if _YELLOW.search(fact):
        return REASON_YELLOW_FLAGS
    return REASON_OTHER


def parse_deleted_laps(text: str) -> DeletedLaps:
    """Read a deleted-lap sheet. Raises :class:`DocumentParseError` when a row is missing or unreadable."""
    text = clean(text)
    session = _SESSION.search(text)
    fact = _FACT.search(text)
    rows = list(_ROW.finditer(text))
    if session is None or fact is None or not rows:
        raise DocumentParseError("deleted-lap sheet without a session, a fact or a row")
    if [int(row["row"]) for row in rows] != list(range(1, len(rows) + 1)):
        raise DocumentParseError(f"deleted-lap rows are not 1..N: {[int(row['row']) for row in rows]}")
    fact_text = squash(fact["text"])
    return DeletedLaps(
        document=document_number(text),
        session=squash(session["name"]),
        date=document_date(text),
        reason=_reason(fact_text),
        fact=fact_text,
        laps=tuple(
            DeletedLap(
                car=int(row["car"]),
                turn=int(row["turn"]),
                entrant=squash(row["entrant"]),
                time_of_day=row["time_of_day"],
                lap_time=None if row["lap_time"] in _NO_TIME else row["lap_time"],
            )
            for row in rows
        ),
    )
