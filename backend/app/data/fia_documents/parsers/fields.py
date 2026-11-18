"""Readers shared by the stewards' documents: the header, numbers, and ruling notes.

A grid or classification closes with notes in one shape::

    Car 77 - 50 place grid penalty - Additional power unit elements have been used - Stewards' document no. 17
    Car 30 - Permitted to start - Stewards' document no. 58

:func:`ruled_notes` reads them, wherever a line break falls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from app.data.fia_documents.text import squash

_NUMBER_WORDS = {
    word: value
    for value, word in enumerate(
        ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"), start=0
    )
}
#: A count as the stewards write it: "50" or "one".
NUMBER = r"\d+|" + "|".join(_NUMBER_WORDS)

# English month names whatever the locale: the FIA prints "31 October 2026".
_MONTHS = {
    name: index
    for index, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
_DOCUMENT = re.compile(r"\bDocument\s+(?P<number>\d+)\b")
_DATE = re.compile(r"\bDate\s+(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]+)\s+(?P<year>\d{4})\b")
_NOTE = re.compile(r"\bCar\s+(?P<car>\d{1,2})\s+-\s+(?P<body>.+?)(?=\s+Car\s+\d{1,2}\s+-\s+|\Z)")
_NOTE_DOCUMENT = re.compile(r"\s*-?\s*Stewards'?\s+document\s+no\.?\s*(?P<number>\d+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class RuledNote:
    """One car's line under a grid's or classification's notes or penalties."""

    car: int
    #: What happened to the car: "50 place grid penalty", "Permitted to start".
    ruling: str
    #: Why, when the line says: "Additional power unit elements have been used".
    reason: str | None
    #: The stewards' document behind it.
    document: int | None


def number(token: str) -> int:
    """``"50"`` → 50, ``"one"`` → 1."""
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


def document_number(text: str) -> int | None:
    match = _DOCUMENT.search(text)
    return int(match["number"]) if match else None


def document_date(text: str) -> str | None:
    """The header's date as ISO (``"2026-10-31"``): the day a local time of day belongs to."""
    match = _DATE.search(text)
    if match is None:
        return None
    month = _MONTHS.get(match["month"])
    try:
        return date(int(match["year"]), month, int(match["day"])).isoformat() if month else None
    except ValueError:  # "31 November"
        return None


def ruled_notes(block: str) -> tuple[RuledNote, ...]:
    """Every "Car N - ruling - reason - Stewards' document no. N" line in ``block``."""
    notes = []
    for match in _NOTE.finditer(squash(block)):
        body = match["body"]
        cited = _NOTE_DOCUMENT.search(body)
        if cited:
            body = body[: cited.start()]
        ruling, _, reason = body.partition(" - ")
        notes.append(
            RuledNote(
                car=int(match["car"]),
                ruling=ruling.strip(),
                reason=reason.strip() or None,
                document=int(cited["number"]) if cited else None,
            )
        )
    return tuple(notes)
