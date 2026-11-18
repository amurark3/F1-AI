"""The Entry List, the Revised Entry List and the driver-change decision behind it.

An entry list row is one line::

    81 PIA Oscar Piastri  AUS McLaren Mastercard F1 Team McLaren Mercedes
    12 ANT Kimi Antonelli ITA Mercedes -AMG PETRONAS F1 Team Mercedes
    31 VER Max Verstappen NED Oracle Red Bull Racing Red Bull Racing Red Bull Ford

pypdf damages spacing ("Aram co", "Mercedes -AMG", "Cadilla c"), so the text is
kept as printed (squashed) and matched with :func:`compact`.

The first list also has a footnote number glued to some car numbers: "13 NOR"
is car 1 with footnote 3, "632 RUS" car 63 with footnote 2 (after the car number on
the grid, before it in the reserve table). Footnote *i* ties a
car to the i-th driver of the reserve table that follows ("In addition to the
list of cars ... may also take part in FP1"), whose own numbers *start* with *i*
("367 FOR" = footnote 3, car 67), and the two share a team. The footnotes are
solved from that: the one reading of every row in which each reserve footnote
sits on exactly one car of its team and no car number repeats. No such reading,
or two, raises. The revised list has no reserves and no footnotes.

The driver-change decision reads::

    The Stewards have received a request from TGR Haas F1 Team to change the driver of car 31,
    Esteban Ocon.
    ... the Stewards grant permission for the driver, Ryo Hirakawa, with the car number 50, to
    participate in the 2026 Mexico City Grand Prix in place of Esteban Ocon for the rest of the competition.
"""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import re

from app.data.fia_documents.parsers.fields import document_number
from app.data.fia_documents.text import DocumentParseError, clean, compact, squash

_HEADER = re.compile(r"^No\.\s+TLA\s+Driver\s+Nat\s+Team\s+Constructor\s*$", re.MULTILINE)
_RESERVES = re.compile(r"^In addition to the list of cars", re.MULTILINE)
_CANDIDATE = re.compile(r"^\d+\s+[A-Z]{3}\s")
_ROW = re.compile(r"^(?P<digits>\d+)\s+(?P<tla>[A-Z]{3})\s+(?P<driver>.+?)\s+(?P<nationality>[A-Z]{3})\s+(?P<rest>.+)$")
# The team ends at "Team", or at Ferrari's "HP" or Red Bull's name, which carry no "Team".
_TEAM = re.compile(r"^(?P<team>.+? Team|Scuderia Ferrari HP|Oracle Red Bull Racing)\s+(?P<constructor>.+)$")
_CHANGE = re.compile(
    r"request from\s+(?P<team>.+?)\s+to change the driver of car\s+(?P<car>\d+),\s+(?P<outgoing>.+?)\."
    r"\s+In accordance.*?the driver,\s+(?P<incoming>.+?),(?:\s+with the car number\s+(?P<new_car>\d+),)?\s+to participate",
    re.DOTALL,
)


@dataclass(frozen=True)
class EntryRow:
    car: int
    tla: str
    #: As printed: "Oscar Piastri".
    driver: str
    nationality: str
    team: str
    #: Chassis and power unit: "Red Bull Racing Red Bull Ford".
    constructor: str
    #: A named reserve who may run in FP1 in a listed car's place.
    reserve: bool


@dataclass(frozen=True)
class EntryList:
    document: int | None
    revised: bool
    rows: tuple[EntryRow, ...]


@dataclass(frozen=True)
class DriverChange:
    document: int | None
    team: str
    car: int
    outgoing: str
    incoming: str
    #: The number the incoming driver races under, when the decision gives one.
    incoming_car: int | None


def _read(line: str) -> tuple[str, re.Match[str], re.Match[str]]:
    row = _ROW.match(line)
    team = _TEAM.match(row["rest"]) if row else None
    if row is None or team is None:
        raise DocumentParseError(f"unreadable entry row {line!r}")
    return row["digits"], row, team


def _options(digits: str, team: str, reserves: list[tuple[int, str]]) -> list[tuple[int, int | None]]:
    """Every (car, footnote) the printed digits could be."""
    options: list[tuple[int, int | None]] = [(int(digits), None)]
    for footnote, reserve_team in reserves:
        suffix = str(footnote)
        if compact(team) == compact(reserve_team) and digits.endswith(suffix) and len(digits) > len(suffix):
            options.append((int(digits[: -len(suffix)]), footnote))
    return options


def _solve(options: list[list[tuple[int, int | None]]], footnotes: int) -> list[tuple[int, int | None]]:
    """The one assignment using every footnote once with no car repeated."""
    found = [
        reading
        for reading in itertools.product(*options)
        if sorted(note for _, note in reading if note) == list(range(1, footnotes + 1))
        and len({car for car, _ in reading}) == len(reading)
    ]
    if len(found) != 1:
        raise DocumentParseError(f"{len(found)} readings of the entry list's footnotes")
    return list(found[0])


def _rows(lines: list[str], reserve: bool, cars: list[int]) -> list[EntryRow]:
    return [
        EntryRow(
            car=car,
            tla=row["tla"],
            driver=row["driver"],
            nationality=row["nationality"],
            team=team["team"],
            constructor=team["constructor"],
            reserve=reserve,
        )
        for line, car in zip(lines, cars, strict=True)
        for _, row, team in [_read(line)]
    ]


def parse_entry_list(text: str) -> EntryList:
    """Read an entry list. Raises :class:`DocumentParseError` for any other shape."""
    text = clean(text)
    header = _HEADER.search(text)
    if header is None:
        raise DocumentParseError("not an entry list: no column header")
    table = text[header.end() :]
    split = _RESERVES.search(table)
    main_text, reserve_text = (table[: split.start()], table[split.end() :]) if split else (table, "")
    main = [squash(line) for line in main_text.splitlines() if _CANDIDATE.match(squash(line))]
    reserves = [squash(line) for line in reserve_text.splitlines() if _CANDIDATE.match(squash(line))]
    if not main:
        raise DocumentParseError("entry list has no rows")

    reserve_cars = []
    reserve_teams = []
    for footnote, line in enumerate(reserves, start=1):
        digits, _, team = _read(line)
        suffix = str(footnote)
        if not digits.startswith(suffix) or len(digits) == len(suffix):
            raise DocumentParseError(f"reserve {footnote} does not start with its footnote: {line!r}")
        reserve_cars.append(int(digits[len(suffix) :]))
        reserve_teams.append((footnote, team["team"]))
    options = []
    for line in main:
        digits, _, team = _read(line)
        options.append(_options(digits, team["team"], reserve_teams))
    cars = [car for car, _ in _solve(options, len(reserves))]
    rows = _rows(main, False, cars) + _rows(reserves, True, reserve_cars)
    title = re.search(r"^Title\s+(?P<title>.+)$", text, re.MULTILINE)
    return EntryList(
        document=document_number(text),
        revised=bool(title and "Revised" in title["title"]),
        rows=tuple(rows),
    )


def parse_driver_change(text: str) -> DriverChange:
    """Read a "Decision - Driver Change" document. Raises :class:`DocumentParseError` otherwise."""
    flat = squash(clean(text))
    match = _CHANGE.search(flat)
    if match is None:
        raise DocumentParseError("not a driver-change decision")
    return DriverChange(
        document=document_number(text),
        team=match["team"],
        car=int(match["car"]),
        outgoing=match["outgoing"],
        incoming=match["incoming"],
        incoming_car=int(match["new_car"]) if match["new_car"] else None,
    )
