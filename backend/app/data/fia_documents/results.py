"""The FIA's final classifications, starting grid and deleted laps: the authority for results, points and the grid.

``docs/DATA_SOURCES.md`` names the FIA's documents as the authority: f1db
mirrors them about ten hours later, sometimes days, without the reasons behind
a grid penalty, and Jolpica still had the pre-penalty order the morning after
Mexico 2026. Once a document is in the store (the ingest runs every five
minutes over a weekend), callers read it first; until then they fall back to
OpenF1, labelled provisional.

* **The newest standing document wins.** A corrected classification takes a
  higher number; a recalled one is withdrawn and skipped. A final starting
  grid wins over the provisional one.
* **A document that does not parse is skipped** and logged, never guessed at.
* **Drivers are named by the event's newest entry list**, which prints each
  car's three-letter code and name, through :mod:`app.data.canonical_names`.
  A debutant f1db does not hold yet keeps the code the timing feeds use,
  rather than his car number.
* **A store that cannot be read is "not landed yet"**, so the caller falls
  back instead of failing the page.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Literal

import structlog

from app.data.canonical_names import F1DB_READ_ERRORS, driver_identity
from app.data.fia_documents import store
from app.data.fia_documents.feed import fia_event
from app.data.fia_documents.kinds import KIND_DELETED_LAPS, document_kind
from app.data.fia_documents.listing import title_number
from app.data.fia_documents.parsers.classifications import parse_classification
from app.data.fia_documents.parsers.deleted_laps import parse_deleted_laps
from app.data.fia_documents.parsers.entry_list import parse_entry_list
from app.data.fia_documents.parsers.grids import parse_starting_grid
from app.data.fia_documents.store import FiaStoreError
from app.data.fia_documents.text import DocumentParseError
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.data.canonical_names import CanonicalDriver
    from app.data.fia_documents.document import SourceDocument
    from app.data.fia_documents.parsers.classifications import Classification
    from app.data.fia_documents.parsers.deleted_laps import DeletedLap
    from app.data.fia_documents.parsers.entry_list import EntryRow
    from app.data.fia_documents.parsers.fields import RuledNote
    from app.data.fia_documents.parsers.grids import StartingGrid

logger = structlog.get_logger()

FIA_FINAL_SOURCE = "fia-final-classification"
Session = Literal["race", "sprint", "qualifying"]
#: The ingest runs every five minutes; a minute's reuse spares the store on every page view.
EVENT_TTL_SECONDS = 60.0

# shortcut: the sprint wording is assumed ("Final Sprint Classification"); no 2026 sprint is in the fixtures yet,
# so check it against a sprint weekend's listing when one is in the store.
_FINAL = re.compile(r"\bFinal\s+(?P<session>Race|Sprint|Qualifying)\s+(?:Race\s+)?Classification\b", re.IGNORECASE)
_ENTRY_LIST = re.compile(r"\bEntry\s+List\b", re.IGNORECASE)
_GRID = re.compile(r"\b(?P<stage>Provisional|Final)\s+Starting\s+Grid\b", re.IGNORECASE)
_SPRINT = re.compile(r"\bSprint\b", re.IGNORECASE)
_TIME_PENALTY = re.compile(r"(\d+)\s+second\s+time\s+penalty", re.IGNORECASE)
_CACHE: TtlCache[tuple[int, int], tuple[SourceDocument, ...]] = TtlCache()


def _driver(year: int, entries: Mapping[int, EntryRow], car: int, printed: str | None) -> CanonicalDriver:
    entry = entries.get(car)
    return driver_identity(
        year, code=entry.tla if entry else None, number=car, name=printed or (entry.driver if entry else None)
    )


@dataclass(frozen=True)
class FinalClassification:
    """A session's final classification, the document it came from and the event's entry list."""

    classification: Classification
    url: str
    #: Car number to its row on the newest entry list; empty when none reads.
    entries: Mapping[int, EntryRow]

    def driver(self, year: int, car: int, printed: str) -> CanonicalDriver:
        """f1db's driver for ``car``, found by the entry list's code, the car number and the printed name."""
        return _driver(year, self.entries, car, printed)

    def time_penalty(self, car: int) -> int:
        """Seconds of time penalty listed for ``car``, a converted stop-and-go included; 0 for none."""
        return sum(
            int(match[1])
            for note in self.classification.penalties
            if note.car == car
            for match in _TIME_PENALTY.finditer(note.ruling)
        )


@dataclass(frozen=True)
class FiaGrid:
    """The race's starting grid as the FIA published it, with what explains each slot."""

    grid: StartingGrid
    url: str
    entries: Mapping[int, EntryRow]
    #: The final qualifying classification, for where each car qualified; ``None`` until it lands.
    qualifying: Classification | None

    def driver(self, year: int, car: int) -> CanonicalDriver:
        """f1db's driver for ``car``; the grid runs name into team, so the entry list names him."""
        return _driver(year, self.entries, car, None)

    def qualified(self, car: int) -> int | None:
        """Where ``car`` qualified; ``None`` for a car with no place (disqualified) or before the classification lands."""
        entries = self.qualifying.entries if self.qualifying else ()
        return next((entry.position for entry in entries if entry.car == car), None)

    def rulings(self, car: int) -> tuple[RuledNote, ...]:
        """The grid's notes and penalties for ``car``, in the order printed."""
        return tuple(note for note in (*self.grid.notes, *self.grid.penalties) if note.car == car)


def _event(year: int, round_number: int) -> tuple[SourceDocument, ...] | None:
    """The round's documents; ``None`` when the store (or f1db's calendar) cannot be read."""
    cached = _CACHE.get((year, round_number))
    if cached is not None:
        return cached
    try:
        event = fia_event(year, round_number)
        documents = store.load_event(year, event) if event else ()
    except (FiaStoreError, *F1DB_READ_ERRORS) as exc:
        logger.warning("fia_results.store_unreadable", year=year, round=round_number, error=str(exc))
        return None
    _CACHE.put((year, round_number), documents, EVENT_TTL_SECONDS)
    return documents


def _newest[T](
    documents: tuple[SourceDocument, ...], wanted: Callable[[str], bool], parse: Callable[[str], T]
) -> tuple[T, str] | None:
    """The newest standing document ``wanted`` picks by title that parses, with its URL."""
    standing = sorted(
        (document for document in documents if not document.withdrawn and document.text and wanted(document.title)),
        key=lambda document: title_number(document.title) or 0,
        reverse=True,
    )
    for document in standing:
        try:
            return parse(document.text or ""), document.url
        except DocumentParseError as exc:
            logger.warning("fia_results.document_unread", title=document.title, error=str(exc))
    return None


def _entries(documents: tuple[SourceDocument, ...]) -> dict[int, EntryRow]:
    found = _newest(documents, lambda title: bool(_ENTRY_LIST.search(title)), parse_entry_list)
    # A reserve only runs in FP1, never in a points session.
    return {row.car: row for row in found[0].rows if not row.reserve} if found else {}


def _is_final(session: Session) -> Callable[[str], bool]:
    def wanted(title: str) -> bool:
        match = _FINAL.search(title)
        # Whatever the wording, a sprint document never answers for the race or its qualifying.
        sprint = bool(_SPRINT.search(title))
        return match is not None and match["session"].lower() == session and sprint == (session == "sprint")

    return wanted


def _is_grid(stage: str) -> Callable[[str], bool]:
    def wanted(title: str) -> bool:
        match = _GRID.search(title)
        return match is not None and match["stage"].lower() == stage and not _SPRINT.search(title)

    return wanted


def final_classification(year: int, round_number: int, session: Session) -> FinalClassification | None:
    """The round's final race, sprint or qualifying classification; ``None`` until it lands or the store fails."""
    documents = _event(year, round_number)
    found = _newest(documents or (), _is_final(session), parse_classification)
    if found is None:
        return None
    classification, url = found
    return FinalClassification(classification=classification, url=url, entries=_entries(documents or ()))


def fia_starting_grid(year: int, round_number: int) -> FiaGrid | None:
    """The race's final starting grid, else the provisional one; ``None`` until one lands or the store fails."""
    documents = _event(year, round_number) or ()
    found = _newest(documents, _is_grid("final"), parse_starting_grid) or _newest(
        documents, _is_grid("provisional"), parse_starting_grid
    )
    if found is None:
        return None
    grid, url = found
    qualifying = _newest(documents, _is_final("qualifying"), parse_classification)
    return FiaGrid(grid=grid, url=url, entries=_entries(documents), qualifying=qualifying[0] if qualifying else None)


def fia_deleted_laps(year: int, round_number: int, session: str) -> tuple[DeletedLap, ...]:
    """Every lap the standing deleted-lap sheets for ``session`` ("Qualifying", "Free Practice 1" …) list.

    A session can have several sheets (track limits, double yellows), so all of
    them count, not only the newest. Empty until one lands or when the store fails.
    """
    found: list[DeletedLap] = []
    for document in _event(year, round_number) or ():
        if document.withdrawn or not document.text or document_kind(document.title) != KIND_DELETED_LAPS:
            continue
        try:
            sheet = parse_deleted_laps(document.text)
        except DocumentParseError as exc:
            logger.warning("fia_results.document_unread", title=document.title, error=str(exc))
            continue
        if sheet.session.casefold() == session.casefold():
            found.extend(sheet.laps)
    return tuple(found)
