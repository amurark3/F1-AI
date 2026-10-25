"""What the screen says about its own numbers: how fresh, and where each limit came from.

*Freshness* reads the ingest job's status record: when fia.com was last
checked, when that last changed anything, and whether the last check worked.
A check older than :data:`STALE_AFTER` is flagged — the job runs at least
daily, so a day without one means it has stopped, and the numbers on screen
are as of the last run that worked.

*Allowances* come from the shared store (see
:mod:`app.data.power_units.allowances`), each with the FIA document that
stated it or a note that it was pinned by hand. Where the FIA's latest
statement disagrees with the stored figure, the screen says so rather than
picking one silently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.data.power_units.allowances import SOURCE_MANUAL
from app.data.power_units.elements import elements_for
from app.data.power_units.status import load_status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.data.power_units.allowances import AllowanceEntry
    from app.services.power_units.evidence import AllowanceStatement, Evidence

STALE_AFTER = timedelta(hours=26)


def _parse(moment: str | None) -> datetime | None:
    if not moment:
        return None
    try:
        parsed = datetime.fromisoformat(moment)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def freshness(year: int, corpus_updated_at: str | None, now: datetime) -> dict:
    """When the corpus was last checked and changed, and whether that is stale."""
    status = load_status(year)
    checked_at = status.checked_at if status else None
    checked = _parse(checked_at)
    return {
        "checked_at": checked_at,
        "changed_at": (status.changed_at if status else None) or corpus_updated_at,
        "outcome": status.outcome if status else None,
        "error": status.error if status else None,
        "stale": checked is None or now - checked > STALE_AFTER,
    }


def _source(entry: AllowanceEntry) -> dict:
    return {
        "kind": entry.source,
        "title": entry.document_title,
        "url": entry.document_url,
        "stated_on": entry.stated_on,
        "updated_at": entry.updated_at,
        "note": entry.note,
    }


def element_payload(year: int, entries: Mapping[str, AllowanceEntry]) -> list[dict]:
    """Every element of the season with its stored allowance and its provenance."""
    return [
        {
            "code": element.code,
            "name": element.name,
            "allowance": entries[element.code].allowance if element.code in entries else None,
            "allowance_source": _source(entries[element.code]) if element.code in entries else None,
        }
        for element in elements_for(year)
    ]


def _latest(statements: tuple[AllowanceStatement, ...]) -> dict[str, AllowanceStatement]:
    """The FIA's latest statement per element; statements arrive in document order."""
    return {item.code: item for item in statements}


def _warning(code: str, entry: AllowanceEntry | None, stated: AllowanceStatement) -> str | None:
    said = f"the FIA's latest report ({stated.ref.title}) states {stated.allowance}"
    if entry is None:
        return f"No {code} allowance is stored yet, so no {code} unit is marked as beyond it; {said}."
    if entry.allowance == stated.allowance:
        return None
    if entry.source == SOURCE_MANUAL:
        return f"{code} is pinned at {entry.allowance} by hand, while {said}."
    return f"The stored {code} allowance is {entry.allowance}, while {said}; it updates on the next collection run."


def allowance_warnings(evidence: Evidence, entries: Mapping[str, AllowanceEntry]) -> list[str]:
    """Every element whose stored allowance the FIA's latest statement does not back."""
    warnings = (_warning(code, entries.get(code), stated) for code, stated in _latest(evidence.statements).items())
    return [warning for warning in warnings if warning is not None]
