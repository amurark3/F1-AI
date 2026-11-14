"""Qualifying classification from OpenF1's ``session_result``: the order a post-qualifying call starts from.

``docs/DATA_SOURCES.md`` names OpenF1 ``session_result`` the first source for a
session's classification once it has run, ahead of Jolpica. Until P0b.10 the
qualifying order came from FastF1 alone (Jolpica's results, plus F1's live
timing for laps), and that is how production lost R20's post-qualifying call on
2026-11-11:

* FastF1 caps each process at 500 requests an hour across every API it calls
  and raises ``RateLimitExceededError`` ("any API: 500 calls/h") past that.
* Since F1's live-timing archive went behind a login (2026-10-15), every FastF1
  session load sends about a dozen requests to it and its mirror that fail.
  Failures are never cached, so the next load sends them again.
* After a boot, the prefetch sweep over the season's races spends about 360 of
  the 500 in a few minutes, and each prediction compute about 60 more. R19's
  qualifying load still fit; R20's, eleven seconds later, was refused. The call
  fell back to pre-qualifying, and the compute endpoint rightly refused to file
  it under the post-qualifying tab.

OpenF1 is reached through its own client, outside that budget. Codes are the
session entry list's (OpenF1's ``name_acronym``, the codes the weekend entry
list and so the grid use); names and teams are f1db's
(:mod:`app.data.canonical_names`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastf1.exceptions import RateLimitExceededError
import structlog

from app.data.canonical_names import CODE_UNRESOLVED, driver_identity, feed_number, team_display_name
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import entry_list, find_session, session_ended

if TYPE_CHECKING:
    from app.data.openf1.sessions import EntryDriver

logger = structlog.get_logger()

OPENF1_SOURCE = "openf1"

# The calendar lookup behind ``find_session`` is FastF1's schedule: ValueError or
# KeyError for a season it cannot read, OSError for the network, and FastF1's
# own request cap, which is how this order came to be needed.
_LOOKUP_ERRORS = (OpenF1UnavailableError, RateLimitExceededError, ValueError, KeyError, OSError)


def _classified_position(row: dict) -> int | None:
    """The row's qualifying position, or None for a car with no place in the order.

    A car disqualified from qualifying (Lawson, Mexico City 2026, FIA document
    57) comes with no position; one flagged ``dsq`` or ``dns`` is left out even
    if a position is set. The grid places such a car, as it does any entered
    driver without a time.
    """
    position = row.get("position")
    if row.get("dsq") or row.get("dns") or not isinstance(position, int) or isinstance(position, bool):
        return None
    return position


def _entry_code(entry: EntryDriver | None) -> str | None:
    """The entry list's code; it prints a car OpenF1 sent without an acronym under its number."""
    return entry.code if entry is not None and entry.code.isalpha() else None


def _order_row(number: int, entry: EntryDriver | None, position: int, year: int) -> dict:
    """One classified car, coded like the FastF1 path: the feed's code, else f1db's, else labelled."""
    name = entry.name if entry is not None else None
    driver = driver_identity(year, code=_entry_code(entry), number=number, name=name)
    code = _entry_code(entry) or driver.code
    row = {
        "driver_code": code or "",
        "driver_name": driver.name or code or "",
        "team": team_display_name(year, entry.team if entry is not None else None),
        "position": position,
    }
    if code:
        return row
    logger.warning(
        "predictions.driver_code_unresolved",
        year=year,
        number=number,
        name=driver.name,
        position=position,
        source=OPENF1_SOURCE,
    )
    return {**row, CODE_UNRESOLVED: True, "driver_number": number}


def qualifying_order(rows: list[dict], entries: dict[int, EntryDriver], year: int) -> list[dict]:
    """OpenF1 ``session_result`` rows as driver dicts in qualifying order, keyed like the FastF1 path."""
    placed = sorted(
        (position, number)
        for row in rows
        if (position := _classified_position(row)) is not None
        and (number := feed_number(row.get("driver_number"))) is not None
    )
    return [_order_row(number, entries.get(number), position, year) for position, number in placed]


def load_openf1_qualifying(year: int, round_num: int) -> list[dict]:
    """The round's qualifying order from OpenF1, or ``[]`` when OpenF1 cannot give one.

    Only a session that has ended and settled is read: mid-session the result
    is a running order. A result with no entry list is not trusted, since car
    numbers alone would not match the grid's codes.
    """
    try:
        with new_client() as client:
            session = find_session(client, year, round_num, "Q")
            if session is None or not session_ended(session):
                return []
            rows = get_json(client, "session_result", {"session_key": session.session_key})
            entries = entry_list(client, session.session_key) if rows else {}
    except _LOOKUP_ERRORS as exc:
        logger.warning("predictions.openf1_qualifying_unavailable", year=year, round=round_num, error=str(exc))
        return []
    if not entries:
        return []
    return qualifying_order(rows, entries, year)
