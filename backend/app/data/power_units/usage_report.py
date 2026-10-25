"""The Technical Delegate's report *PU Elements used per Driver up to now*.

::

    N° Car Driver ICE TC EXH MGU
    -K ES PU-
    CE
    PU-
    ANC
    81 McLaren Mercedes Oscar Piastri 4 3 3 2 3 3 4

Published once per Grand Prix before the cars run, so each row is that car's
running total going *into* the weekend: George Russell's Singapore row shows
four engines, and his fifth was declared hours later.

The column headings break across lines wherever the PDF wrapped them, so they
are read by squeezing the header together and splitting it against the known
codes, longest first — "PU-CE" must not be read as "PU" plus "CE". The codes
come from the document rather than being assumed: 2025's report counts MGU-H,
CE and EX where 2026's counts EXH, PU-CE and PU-ANC.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import TYPE_CHECKING

from app.data.power_units.text import DocumentParseError, clean, squash

if TYPE_CHECKING:
    from collections.abc import Mapping

# Every element code any season's report has printed, longest first so the
# greedy split below never stops at a prefix.
PRINTED_CODES: tuple[str, ...] = ("PU-ANC", "PU-CE", "MGU-H", "MGU-K", "ICE", "EXH", "TC", "ES", "CE", "EX")

_TABLE_START = re.compile(r"^\s*N\s*°", re.MULTILINE)
_ROW_START = re.compile(r"^\s*\d{1,2}\s+\S")
_DRIVER_HEADING = "Driver"


@dataclass(frozen=True)
class UsageRow:
    """One car's running totals, keyed by element code as printed."""

    car_number: int
    #: Team, power unit and driver as printed, e.g. "McLaren Mercedes Oscar Piastri".
    entrant: str
    counts: Mapping[str, int]


@dataclass(frozen=True)
class UsageReport:
    """Every car's totals going into the weekend."""

    codes: tuple[str, ...]
    rows: tuple[UsageRow, ...]


def _split_codes(squeezed: str) -> tuple[str, ...]:
    codes: list[str] = []
    rest = squeezed
    while rest:
        code = next((candidate for candidate in PRINTED_CODES if rest.startswith(candidate)), None)
        if code is None:
            raise DocumentParseError(f"unrecognised column heading near {rest[:12]!r}")
        codes.append(code)
        rest = rest[len(code) :]
    return tuple(codes)


def _header_and_body(text: str) -> tuple[str, list[str]]:
    start = _TABLE_START.search(text)
    if start is None:
        raise DocumentParseError("usage report has no table heading")
    lines = text[start.start() :].splitlines()
    first_row = next((index for index, line in enumerate(lines) if _ROW_START.match(line)), len(lines))
    return "".join("".join(lines[:first_row]).split()), lines[first_row:]


def _row_pattern(columns: int) -> re.Pattern[str]:
    return re.compile(rf"^\s*(?P<car>\d{{1,2}})\s+(?P<entrant>.+?)(?P<counts>(?:\s+\d{{1,2}}){{{columns}}})\s*$")


def parse_usage_report(text: str) -> UsageReport:
    """Read the totals table. Raises :class:`DocumentParseError` on any doubt."""
    header, body = _header_and_body(clean(text))
    marker = header.find(_DRIVER_HEADING)
    if marker < 0:
        raise DocumentParseError("usage report heading has no Driver column")
    codes = _split_codes(header[marker + len(_DRIVER_HEADING) :])
    if not codes:
        raise DocumentParseError("usage report lists no element columns")

    pattern = _row_pattern(len(codes))
    rows: list[UsageRow] = []
    seen: set[int] = set()
    for line in body:
        match = pattern.match(line)
        if match is None:
            continue
        car = int(match["car"])
        if car in seen:
            raise DocumentParseError(f"car {car} appears twice in the usage report")
        seen.add(car)
        counts = MappingProxyType(dict(zip(codes, (int(value) for value in match["counts"].split()), strict=True)))
        rows.append(UsageRow(car_number=car, entrant=squash(match["entrant"]), counts=counts))

    if not rows:
        raise DocumentParseError("usage report has no driver rows")
    return UsageReport(codes=codes, rows=tuple(rows))
