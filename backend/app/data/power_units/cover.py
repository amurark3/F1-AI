"""The cover block every FIA document opens with.

::

    2026 SINGAPORE GRAND PRIX
    09 - 11 October 2026
    From The FIA Formula 1 Technical Delegate
    To The Stewards
    Document 10
    Date 09 October 2026
    Time 14:11
    Title Technical Delegate's Report
    Description PU Elements used per Driver up to now
    Enclosed 17 SIN GP 26 TDR1.pdf

Two things on it tie a document to an f1db round, because event names drift
between the FIA and f1db ("Bahrain Grand Prix" was held in Malaysia in 2026):
a Technical Delegate's report names the PDF it encloses after the round, and
the last day of the date range is the race day. The round number is read
first — Monaco and Hungary 2026 printed the wrong race day — but a stewards'
decision encloses nothing, so it has only the date. The document number
orders a weekend's documents — the stewards number every publication of an
event in sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import re

from app.data.power_units.text import clean

# "09 - 11 October 2026", "05 – 07 June 2026", or across a month end:
# "30 October - 01 November 2026". The FIA is not consistent about the rest:
# Austria 2026 abbreviated the month ("26 - 28 Jun 2026") and Mexico City 2026
# left the year off ("30 October - 01 November"), which the headline supplies.
_DATE_RANGE = re.compile(
    r"\b\d{1,2}(?:\s+[A-Za-z]+)?\s*[-–—]\s*(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)(?:\s+(?P<year>\d{4}))?\b",
)
_DATE_FORMATS = ("%d %B %Y", "%d %b %Y")
_HEADLINE = re.compile(r"^\s*(?P<season>\d{4})\s+(?P<event>[^\n]*?GRAND PRIX)\s*$", re.MULTILINE | re.IGNORECASE)
_DOCUMENT_NUMBER = re.compile(r"^\s*Document\s+(?P<number>\d+)\s*$", re.MULTILINE)
# "Enclosed 07 BCN-CAT GP 26 TDR8.pdf": the round, then the FIA's own event
# code (DUT, BAH, SIN, US — not f1db's), so only the number is read.
_ENCLOSED_ROUND = re.compile(r"^\s*Enclosed\s+(?P<round>\d{1,2})\s+\S+\s+GP\s+\d{2}\b", re.MULTILINE)

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
    #: The round the enclosed report is numbered for — a Technical Delegate's
    #: report only.
    round: int | None


def _parse_date(text: str, date_format: str) -> date | None:
    try:
        return datetime.strptime(text, date_format).replace(tzinfo=UTC).date()
    except ValueError:
        return None


def _race_day(head: str, season: int | None) -> date | None:
    match = _DATE_RANGE.search(head)
    if not match:
        return None
    year = match["year"] or season
    if year is None:
        return None
    text = f"{match['day']} {match['month']} {year}"
    return next((day for date_format in _DATE_FORMATS if (day := _parse_date(text, date_format))), None)


def parse_cover(text: str) -> Cover:
    """Read the cover block. Never raises: a missing field is ``None``."""
    head = "\n".join(clean(text).splitlines()[:_COVER_LINES])
    headline = _HEADLINE.search(head)
    number = _DOCUMENT_NUMBER.search(head)
    enclosed = _ENCLOSED_ROUND.search(head)
    season = int(headline["season"]) if headline else None
    return Cover(
        season=season,
        event=" ".join(headline["event"].split()).title() if headline else None,
        race_day=_race_day(head, season),
        document_number=int(number["number"]) if number else None,
        round=int(enclosed["round"]) if enclosed else None,
    )
