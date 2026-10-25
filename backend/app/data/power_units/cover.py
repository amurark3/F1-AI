"""The cover block every FIA document opens with.

::

    2026 SINGAPORE GRAND PRIX
    09 - 11 October 2026
    From The FIA Formula 1 Technical Delegate
    To The Stewards
    Document 10
    Date 09 October 2026
    Time 14:11

The last day of the date range is the race day, which is how a document is
tied to an f1db round: event names drift between the FIA and f1db ("Bahrain
Grand Prix" was held in Malaysia in 2026), the race date does not. The
document number orders a weekend's documents — the stewards number every
publication of an event in sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import re

from app.data.power_units.text import clean

# "09 - 11 October 2026", "05 – 07 June 2026", or across a month end:
# "30 October - 01 November 2026".
_DATE_RANGE = re.compile(
    r"\b\d{1,2}(?:\s+[A-Za-z]+)?\s*[-–—]\s*(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\b",
)
_HEADLINE = re.compile(r"^\s*(?P<season>\d{4})\s+(?P<event>[^\n]*?GRAND PRIX)\s*$", re.MULTILINE | re.IGNORECASE)
_DOCUMENT_NUMBER = re.compile(r"^\s*Document\s+(?P<number>\d+)\s*$", re.MULTILINE)

# The cover is the first few lines; searching further would pick up a date
# quoted in the body of a decision.
_COVER_LINES = 12


@dataclass(frozen=True)
class Cover:
    """What the cover block says, each field ``None`` when it is not there."""

    season: int | None
    event: str | None
    race_day: date | None
    document_number: int | None


def _race_day(head: str) -> date | None:
    match = _DATE_RANGE.search(head)
    if not match:
        return None
    try:
        parsed = datetime.strptime(f"{match['day']} {match['month']} {match['year']}", "%d %B %Y").replace(
            tzinfo=UTC,
        )
    except ValueError:
        return None
    return parsed.date()


def parse_cover(text: str) -> Cover:
    """Read the cover block. Never raises: a missing field is ``None``."""
    head = "\n".join(clean(text).splitlines()[:_COVER_LINES])
    headline = _HEADLINE.search(head)
    number = _DOCUMENT_NUMBER.search(head)
    return Cover(
        season=int(headline["season"]) if headline else None,
        event=" ".join(headline["event"].split()).title() if headline else None,
        race_day=_race_day(head),
        document_number=int(number["number"]) if number else None,
    )
