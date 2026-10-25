"""The Technical Delegate's report *New PU Elements for this Competition*.

One section per element type fitted at the event::

    The following drivers will start the thirteenth Competition of the 2026
    Formula One World Championship with a new internal combustion engine (ICE):

or, in a report published once the weekend is under way::

    The following driver is using a new internal combustion engine (ICE) for
    the remainder of the Competition:

Neither wording is reliable word for word (one Monza heading reads "is using a
exhaust set (EXH)"), so a section is anchored on what never changes: it opens
with "The following driver(s)" and names the element by its bracketed code
before the colon.

    Number Car Driver Previously used ICE
    12 Mercedes Kimi Antonelli 4
    ...
    The internal combustion engine used by Kimi Antonelli and Alexander Albon
    is the fifth (5th) of the four (4) new internal combustion engines allowed
    for the 2026 Championship season and this is not in conformity with ...

The table is what is read: the new element is number ``previously used + 1``.
The sentences after it group drivers by compliance using names pypdf mangles
("Geor ge Russell") and phrases like "the rest of the above listed drivers",
so compliance is recomputed from the numbers rather than parsed from prose.
The one thing taken from the prose is the allowance itself — "of the four (4)
new ... allowed" — which the service checks against the regulations table.

An event can publish several of these reports (Monza had three): elements
fitted after the first one are announced in another.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import TYPE_CHECKING

from app.data.power_units.text import DocumentParseError, clean, squash

if TYPE_CHECKING:
    from collections.abc import Mapping

_SECTION = re.compile(
    r"The\s+following\s+drivers?\s+[^():]+?\(\s*(?P<code>[A-Z][A-Z-]*)\s*\)[^():]*:",
    re.IGNORECASE,
)
_ROW = re.compile(r"^\s*(?P<car>\d{1,2})\s+(?P<entrant>.+?)\s+(?P<previous>\d{1,2})\s*$", re.MULTILINE)
_ALLOWANCE = re.compile(r"of\s+the\s+[a-z]+\s+\((?P<count>\d+)\)\s+new\b", re.IGNORECASE)


@dataclass(frozen=True)
class Introduction:
    """One element fitted to one car at this event."""

    code: str
    car_number: int
    #: Team, power unit and driver as printed.
    entrant: str
    previously_used: int

    @property
    def number(self) -> int:
        """Which unit of the season this one is: the 5th ICE, the 4th ES."""
        return self.previously_used + 1


@dataclass(frozen=True)
class NewElementsReport:
    """Every element fitted, in the order the report lists them."""

    introductions: tuple[Introduction, ...]
    #: ``{code: allowance}`` as the report states it in words.
    stated_allowance: Mapping[str, int]


def parse_new_elements(text: str) -> NewElementsReport:
    """Read every section. Raises :class:`DocumentParseError` on any doubt."""
    text = clean(text)
    sections = list(_SECTION.finditer(text))
    if not sections:
        raise DocumentParseError("new-elements report has no element sections")

    introductions: list[Introduction] = []
    stated: dict[str, int] = {}
    for index, section in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        body = text[section.end() : end]
        code = section["code"].upper()
        rows = [
            Introduction(
                code=code,
                car_number=int(row["car"]),
                entrant=squash(row["entrant"]),
                previously_used=int(row["previous"]),
            )
            for row in _ROW.finditer(body)
        ]
        if not rows:
            raise DocumentParseError(f"new-elements section {code} lists no cars")
        introductions.extend(rows)
        allowance = _ALLOWANCE.search(body)
        if allowance is not None:
            stated[code] = int(allowance["count"])

    return NewElementsReport(introductions=tuple(introductions), stated_allowance=MappingProxyType(stated))
