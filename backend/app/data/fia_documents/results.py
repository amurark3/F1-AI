"""The FIA's final race and sprint classifications: the authority for results and points.

``docs/DATA_SOURCES.md`` names the FIA final classification as the authority:
f1db mirrors it about ten hours later, sometimes days, and Jolpica still had
the pre-penalty order the morning after Mexico 2026. Once the document is in
the store (the ingest runs every five minutes over a weekend), a result read
from it is final; until then callers fall back to OpenF1, labelled provisional.

* **The newest standing document wins.** A corrected classification takes a
  higher number; a recalled one is withdrawn and skipped.
* **A document that does not parse is skipped** and logged, never guessed at.
* **Drivers are named by the event's newest entry list**, which prints each
  car's three-letter code, then the car number and the printed name, through
  :mod:`app.data.canonical_names`. A debutant f1db does not hold yet keeps the
  code the timing feeds use, rather than his car number.
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
from app.data.fia_documents.listing import title_number
from app.data.fia_documents.parsers.classifications import parse_classification
from app.data.fia_documents.parsers.entry_list import parse_entry_list
from app.data.fia_documents.store import FiaStoreError
from app.data.fia_documents.text import DocumentParseError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.data.canonical_names import CanonicalDriver
    from app.data.fia_documents.document import SourceDocument
    from app.data.fia_documents.parsers.classifications import Classification

logger = structlog.get_logger()

FIA_FINAL_SOURCE = "fia-final-classification"
PointsSession = Literal["race", "sprint"]

# shortcut: the sprint wording is assumed ("Final Sprint Classification"); no 2026 sprint is in the fixtures yet,
# so check it against a sprint weekend's listing when one is in the store.
_FINAL = re.compile(r"\bFinal\s+(?P<session>Race|Sprint)\s+(?:Race\s+)?Classification\b", re.IGNORECASE)
_ENTRY_LIST = re.compile(r"\bEntry\s+List\b", re.IGNORECASE)
_TIME_PENALTY = re.compile(r"(\d+)\s+second\s+time\s+penalty", re.IGNORECASE)


@dataclass(frozen=True)
class FinalClassification:
    """A session's final classification, the document it came from and the event's car codes."""

    classification: Classification
    url: str
    #: Car number to the entry list's three-letter code; empty when no entry list reads.
    codes: Mapping[int, str]

    def driver(self, year: int, car: int, printed: str) -> CanonicalDriver:
        """f1db's driver for ``car``, found by the entry list's code, the car number and the printed name."""
        return driver_identity(year, code=self.codes.get(car), number=car, name=printed)

    def time_penalty(self, car: int) -> int:
        """Seconds of time penalty listed for ``car``, a converted stop-and-go included; 0 for none."""
        return sum(
            int(match[1])
            for note in self.classification.penalties
            if note.car == car
            for match in _TIME_PENALTY.finditer(note.ruling)
        )


def _standing(documents: tuple[SourceDocument, ...], wanted: Callable[[str], bool]) -> list[SourceDocument]:
    """The documents ``wanted`` picks by title that still stand and have text, newest first."""
    return sorted(
        (document for document in documents if not document.withdrawn and document.text and wanted(document.title)),
        key=lambda document: title_number(document.title) or 0,
        reverse=True,
    )


def _codes(documents: tuple[SourceDocument, ...]) -> dict[int, str]:
    for document in _standing(documents, lambda title: bool(_ENTRY_LIST.search(title))):
        try:
            rows = parse_entry_list(document.text or "").rows
        except DocumentParseError as exc:
            logger.warning("fia_results.entry_list_unread", title=document.title, error=str(exc))
            continue
        # A reserve only runs in FP1, never in a points session.
        return {row.car: row.tla for row in rows if not row.reserve}
    return {}


def _is_final(session: PointsSession) -> Callable[[str], bool]:
    def wanted(title: str) -> bool:
        match = _FINAL.search(title)
        return match is not None and match["session"].lower() == session

    return wanted


def final_classification(year: int, round_number: int, session: PointsSession) -> FinalClassification | None:
    """The round's final race or sprint classification; ``None`` until it lands or when the store cannot be read."""
    try:
        event = fia_event(year, round_number)
        documents = store.load_event(year, event) if event else ()
    except (FiaStoreError, *F1DB_READ_ERRORS) as exc:
        logger.warning("fia_results.store_unreadable", year=year, round=round_number, error=str(exc))
        return None
    for document in _standing(documents, _is_final(session)):
        try:
            classification = parse_classification(document.text or "")
        except DocumentParseError as exc:
            logger.warning("fia_results.classification_unread", title=document.title, error=str(exc))
            continue
        return FinalClassification(classification=classification, url=document.url, codes=_codes(documents))
    return None
