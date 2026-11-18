"""The Provisional and Final Starting Grid.

::

    1 44 Lewis HAMILTONScuderia Ferrari HP 1:16.514
    5 3 Max VERSTAPPEN *Oracle Red Bull Racing 1:16.692
    DRIVERS REQUIRED TO START FROM THE PIT LANE
    30 Liam LAWSON *
    Visa Cash App Racing Bulls F1 Team
    NOTES
    Car 30 - Permitted to start - Stewards' document no. 58
    * PENALTIES
    Car 3 - 1 place grid penalty - Causing a collision - Stewards' document no. 33

The rows come out of the PDF two columns at a time (even slots, then odd), so
they are put back in slot order. ``*`` marks a car whose slot a penalty moved;
the penalties block says which and why. A car without a time set none, or had
it removed: the notes and penalties carry the reason.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.fia_documents.parsers.fields import RuledNote, document_number, ruled_notes
from app.data.fia_documents.text import DocumentParseError, clean, squash

_FINAL = re.compile(r"\bFinal\s+Starting\s+Grid\b", re.IGNORECASE)
_PIT_LANE = re.compile(r"^\s*DRIVERS\s+REQUIRED\s+TO\s+START\s+FROM\s+THE\s+PIT\s+LANE\s*$", re.MULTILINE)
_NOTES = re.compile(r"^\s*NOTES\s*$", re.MULTILINE)
_PENALTIES = re.compile(r"^\s*\*\s*PENALTIES\s*$", re.MULTILINE)
# The FOM legal notice that closes every timing sheet.
_END = re.compile(r"^The F1 FORMULA 1 logo", re.MULTILINE)
_SLOT = re.compile(
    r"^\s*(?P<position>\d{1,2})\s+(?P<car>\d{1,2})\s+(?P<entrant>\D.*?)(?:\s+(?P<time>\d:\d{2}\.\d{3}))?\s*$"
)
# A pit-lane starter: car, then "Firstname SURNAME" (the team follows on its own line).
_PIT_STARTER = re.compile(r"(?P<car>\d{1,2})\s+(?P<entrant>.+?)(?=\s+\d{1,2}\s+[A-Z][a-z]|\Z)")


@dataclass(frozen=True)
class GridSlot:
    position: int
    car: int
    #: Driver and team as printed, run together ("Oliver BEARMANTGR Haas F1 Team").
    entrant: str
    #: The qualifying time beside the slot; ``None`` when none is printed.
    time: str | None
    #: Marked ``*``: a penalty moved this car.
    penalised: bool


@dataclass(frozen=True)
class PitLaneStart:
    car: int
    entrant: str


@dataclass(frozen=True)
class StartingGrid:
    document: int | None
    final: bool
    slots: tuple[GridSlot, ...]
    pit_lane: tuple[PitLaneStart, ...]
    notes: tuple[RuledNote, ...]
    penalties: tuple[RuledNote, ...]


def _section(text: str, heading: re.Pattern[str]) -> str:
    """The lines under ``heading`` up to the next heading or the legal notice; empty when absent."""
    start = heading.search(text)
    if start is None:
        return ""
    ends = [
        match.start()
        for pattern in (_PIT_LANE, _NOTES, _PENALTIES, _END)
        if (match := pattern.search(text, start.end()))
    ]
    return text[start.end() : min(ends, default=len(text))]


def _slots(text: str) -> tuple[GridSlot, ...]:
    ends = [match.start() for pattern in (_PIT_LANE, _NOTES, _PENALTIES, _END) if (match := pattern.search(text))]
    slots = []
    for line in text[: min(ends, default=len(text))].splitlines():
        match = _SLOT.match(line)
        if match:
            entrant = match["entrant"]
            slots.append(
                GridSlot(
                    position=int(match["position"]),
                    car=int(match["car"]),
                    entrant=squash(entrant.replace("*", " ")),
                    time=match["time"],
                    penalised="*" in entrant,
                )
            )
    return tuple(sorted(slots, key=lambda slot: slot.position))


def parse_starting_grid(text: str) -> StartingGrid:
    """Read a starting grid. Raises :class:`DocumentParseError` when its slots are not 1..N."""
    text = clean(text)
    slots = _slots(text)
    if not slots or [slot.position for slot in slots] != list(range(1, len(slots) + 1)):
        raise DocumentParseError(f"grid slots are not 1..N: {[slot.position for slot in slots]}")
    pit_lane = tuple(
        PitLaneStart(car=int(match["car"]), entrant=squash(match["entrant"].replace("*", " ")))
        for match in _PIT_STARTER.finditer(squash(_section(text, _PIT_LANE)))
    )
    return StartingGrid(
        document=document_number(text),
        final=bool(_FINAL.search(text)),
        slots=slots,
        pit_lane=pit_lane,
        notes=ruled_notes(_section(text, _NOTES)),
        penalties=ruled_notes(_section(text, _PENALTIES)),
    )
