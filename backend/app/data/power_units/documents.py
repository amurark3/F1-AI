"""Classify an FIA document's text and route it to its parser.

Classification reads the document, not its title or URL. Titles are written by
hand at every event — "PU element", "PU elements", "Change to PU elements",
"PU elements changed during Parc Ferme" — while the body of each type is a
fixed template: the Technical Delegate's reports carry a ``Description`` line,
and a power-unit decision carries the fact line "The following Power Unit
elements have been used".

Any document may also take earlier ones back ("This decision replaces
Document 37"); those numbers are read from every document, whatever its kind
(see :mod:`app.data.power_units.rescission`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.data.power_units.cover import Cover, parse_cover
from app.data.power_units.decision import ELEMENTS_USED, PuDecision, parse_decision
from app.data.power_units.new_elements import NewElementsReport, parse_new_elements
from app.data.power_units.rescission import withdrawn_numbers
from app.data.power_units.text import clean
from app.data.power_units.usage_report import UsageReport, parse_usage_report

KIND_USAGE_REPORT = "usage_report"
KIND_NEW_ELEMENTS = "new_elements"
KIND_DECISION = "decision"
#: A notice whose only business is taking earlier documents back.
KIND_WITHDRAWAL = "withdrawal"
#: A document collected because its title mentioned power units, whose body
#: turned out to be about something else. Not an error — just not evidence.
KIND_UNRELATED = "unrelated"

_FROM_TECHNICAL_DELEGATE = re.compile(
    r"^\s*From\s+The\s+FIA\s+Formula\s+(?:1|One)\s+Technical\s+Delegate", re.MULTILINE
)
_FROM_STEWARDS = re.compile(r"^\s*From\s+The\s+Stewards\b", re.MULTILINE)
_USAGE_DESCRIPTION = re.compile(r"PU\s+Elements\s+used\s+per\s+Driver", re.IGNORECASE)
_NEW_DESCRIPTION = re.compile(r"New\s+PU\s+Elements\s+for\s+this\s+Competition", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDocument:
    """A document's cover, the body its kind carries, and what it takes back."""

    kind: str
    cover: Cover
    body: UsageReport | NewElementsReport | PuDecision | None = None
    #: Numbers of earlier documents of the same event this one withdraws.
    withdraws: frozenset[int] = field(default_factory=frozenset)


def classify(text: str) -> str:
    """Which of the power-unit templates ``text`` is, if any."""
    if _FROM_TECHNICAL_DELEGATE.search(text):
        if _USAGE_DESCRIPTION.search(text):
            return KIND_USAGE_REPORT
        if _NEW_DESCRIPTION.search(text):
            return KIND_NEW_ELEMENTS
    if _FROM_STEWARDS.search(text) and ELEMENTS_USED.search(text):
        return KIND_DECISION
    return KIND_UNRELATED


def parse_document(text: str) -> ParsedDocument:
    """Parse ``text`` as whatever it is.

    Raises :class:`app.data.power_units.text.DocumentParseError` when the
    document is a power-unit template but cannot be read in full.
    """
    text = clean(text)
    kind = classify(text)
    cover = parse_cover(text)
    withdraws = withdrawn_numbers(text, cover.document_number)
    if kind == KIND_USAGE_REPORT:
        return ParsedDocument(kind=kind, cover=cover, body=parse_usage_report(text), withdraws=withdraws)
    if kind == KIND_NEW_ELEMENTS:
        return ParsedDocument(kind=kind, cover=cover, body=parse_new_elements(text), withdraws=withdraws)
    if kind == KIND_DECISION:
        return ParsedDocument(kind=kind, cover=cover, body=parse_decision(text), withdraws=withdraws)
    return ParsedDocument(kind=KIND_WITHDRAWAL if withdraws else kind, cover=cover, withdraws=withdraws)
