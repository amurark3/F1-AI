"""The Pirelli preview: which three compounds the weekend runs.

::

    Compound
    C4
    C3
    C5
    Intermediate
    Wet
    Q3 tyre
    C5
    Mandatory race tyres
    C3
    C4

The slicks nominated are listed in no useful order; by the C-number the
lowest is the hardest, so Mexico's C3, C4, C5 are hard, medium, soft.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.fia_documents.text import DocumentParseError, clean

_COMPOUNDS = re.compile(r"^Compound\s*\n(?P<lines>(?:C[1-5]\s*\n)+)", re.MULTILINE)
_Q3 = re.compile(r"^Q3 tyre\s*\n(?P<compound>C[1-5])\s*$", re.MULTILINE)
_MANDATORY = re.compile(r"^Mandatory race tyres\s*\n(?P<lines>(?:C[1-5]\s*(?:\n|\Z))+)", re.MULTILINE)


@dataclass(frozen=True)
class TyreNomination:
    hard: str
    medium: str
    soft: str
    #: The compound the preview names for Q3, when it reads cleanly.
    q3: str | None
    #: The compounds the preview names for the race's mandatory stop; empty when not read.
    mandatory_race: tuple[str, ...]


def parse_pirelli_preview(text: str) -> TyreNomination:
    """Read the nominated compounds. Raises :class:`DocumentParseError` unless there are exactly three."""
    text = clean(text)
    block = _COMPOUNDS.search(text)
    found = sorted(set(block["lines"].split())) if block else []
    if len(found) != 3 or len(block["lines"].split()) != 3:
        raise DocumentParseError(f"expected three distinct compounds, found {found}")
    q3 = _Q3.search(text)
    mandatory = _MANDATORY.search(text)
    hard, medium, soft = found
    return TyreNomination(
        hard=hard,
        medium=medium,
        soft=soft,
        q3=q3["compound"] if q3 else None,
        mandatory_race=tuple(mandatory["lines"].split()) if mandatory else (),
    )
