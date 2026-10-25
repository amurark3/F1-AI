"""Each element's season allowance — kept in the shared store, not in code.

One document, ``power_unit_allowances``::

    {"seasons": {"2026": {"elements": {
        "ICE": {"allowance": 4, "source": "fia_report",
                "document_title": "Doc 13 - New PU Elements for this Competition",
                "document_url": "https://www.fia.com/…", "stated_on": "2026-10-25",
                "updated_at": "…", "note": null}, …}}}}

The FIA restates every allowance in its *New PU Elements* reports — "the
fifth (5th) of the four (4) new internal combustion engines allowed" — so the
ingest job keeps this document current from the latest such statement per
element, together with the document that made it. That is how a regulation
change reaches the screen without a release: the FIA's next report states the
new figure, and the next run records it.

Why the *latest* statement: the first 2026 reports quoted the base allowance
of Article B8.2.2 ("one (1) of the two (2) new control electronics units" at
Australia) and later ones the total including the extra unit B8.2.3a grants
for 2026 ("of the three (3)"). The penalties applied all season match the
total.

A value can also be pinned by hand (``scripts/power_unit_allowances.py``) for
the rare case the reports get it wrong. A pinned value is never overwritten by
the job; when the FIA's latest statement disagrees with it, the screen says so.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

import structlog

from app.data.power_units.documents import parse_document
from app.data.power_units.elements import canonical_code
from app.data.power_units.new_elements import NewElementsReport
from app.data.power_units.sources import SourcesUnavailableError
from app.data.power_units.text import DocumentParseError
from app.data.store import DOCUMENT_POWER_UNIT_ALLOWANCES, document_store

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from app.data.power_units.sources import SeasonSources, SourceDocument
    from app.data.store_types import WriteResult

logger = structlog.get_logger()

SOURCE_FIA = "fia_report"
SOURCE_MANUAL = "manual"


@dataclass(frozen=True)
class AllowanceEntry:
    """One element's allowance and where it came from."""

    code: str
    allowance: int
    source: str
    document_title: str | None
    document_url: str | None
    #: Race day of the event whose report stated it, ISO format.
    stated_on: str | None
    updated_at: str
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "allowance": self.allowance,
            "source": self.source,
            "document_title": self.document_title,
            "document_url": self.document_url,
            "stated_on": self.stated_on,
            "updated_at": self.updated_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, code: str, raw: object) -> AllowanceEntry | None:
        """A stored entry, or ``None`` for one without a usable allowance."""
        if not isinstance(raw, dict) or not isinstance(raw.get("allowance"), int) or raw["allowance"] < 0:
            return None
        text = {
            key: value if isinstance(value := raw.get(key), str) else None
            for key in ("document_title", "document_url", "stated_on", "updated_at", "note")
        }
        source = raw.get("source")
        return cls(
            code=code,
            allowance=raw["allowance"],
            source=source if source in (SOURCE_FIA, SOURCE_MANUAL) else SOURCE_FIA,
            document_title=text["document_title"],
            document_url=text["document_url"],
            stated_on=text["stated_on"],
            updated_at=text["updated_at"] or "",
            note=text["note"],
        )


@dataclass(frozen=True)
class StatedAllowance:
    """An allowance as one Technical Delegate's report states it."""

    code: str
    allowance: int
    race_day: date | None
    document_number: int | None
    title: str
    url: str


def _statements(source: SourceDocument, year: int) -> list[StatedAllowance]:
    try:
        parsed = parse_document(source.text or "")
    except DocumentParseError:
        return []
    if not isinstance(parsed.body, NewElementsReport):
        return []
    return [
        StatedAllowance(code, count, parsed.cover.race_day, parsed.cover.document_number, source.title, source.url)
        for raw, count in parsed.body.stated_allowance.items()
        if (code := canonical_code(raw, year)) is not None
    ]


def statements_in(sources: SeasonSources) -> list[StatedAllowance]:
    """Every allowance the season's current reports state, in no particular order."""
    return [
        statement
        for source in sources.documents
        if source.text is not None and source.withdrawn is None
        for statement in _statements(source, sources.year)
    ]


def latest_statements(statements: Iterable[StatedAllowance]) -> dict[str, StatedAllowance]:
    """The most recent statement of each element's allowance."""
    latest: dict[str, StatedAllowance] = {}
    for statement in sorted(statements, key=lambda item: (item.race_day or date.min, item.document_number or 0)):
        latest[statement.code] = statement
    return latest


def _read_payload() -> dict:
    result = document_store.read(DOCUMENT_POWER_UNIT_ALLOWANCES)
    if not result.ok:
        raise SourcesUnavailableError(result.error or "power-unit allowances could not be read")
    return result.payload or {}


def _season(payload: dict, year: int) -> dict:
    seasons = payload.get("seasons")
    season = seasons.get(str(year)) if isinstance(seasons, dict) else None
    elements = season.get("elements") if isinstance(season, dict) else None
    return elements if isinstance(elements, dict) else {}


def load_allowances(year: int) -> dict[str, AllowanceEntry]:
    """``{code: entry}`` for the season; empty when nothing is known yet.

    Raises :class:`SourcesUnavailableError` when the store cannot be read.
    """
    entries = (AllowanceEntry.from_dict(code, raw) for code, raw in _season(_read_payload(), year).items())
    return {entry.code: entry for entry in entries if entry is not None}


def save_allowances(year: int, entries: Mapping[str, AllowanceEntry]) -> WriteResult:
    """Replace one season's allowances, keeping every other season as stored."""
    payload = _read_payload()
    seasons = payload.get("seasons")
    merged = {
        **(seasons if isinstance(seasons, dict) else {}),
        str(year): {"elements": {code: entry.as_dict() for code, entry in entries.items()}},
    }
    result = document_store.write(DOCUMENT_POWER_UNIT_ALLOWANCES, {**payload, "seasons": merged})
    logger.info("power_units.allowances_saved", year=year, elements=sorted(entries), ok=result.ok)
    return result


def _from_statement(statement: StatedAllowance, now: str) -> AllowanceEntry:
    return AllowanceEntry(
        code=statement.code,
        allowance=statement.allowance,
        source=SOURCE_FIA,
        document_title=statement.title,
        document_url=statement.url,
        stated_on=statement.race_day.isoformat() if statement.race_day else None,
        updated_at=now,
    )


def refresh_from_reports(sources: SeasonSources, now: str) -> tuple[str, ...]:
    """Bring the stored allowances in line with the FIA's latest statements.

    Returns the codes whose allowance changed. Pinned entries are left alone,
    and nothing is written when nothing changed.
    """
    stored = load_allowances(sources.year)
    updated = dict(stored)
    for code, statement in latest_statements(statements_in(sources)).items():
        current = stored.get(code)
        if current is not None and current.source == SOURCE_MANUAL:
            continue
        if current is None or current.allowance != statement.allowance:
            updated[code] = _from_statement(statement, now)
        elif current.document_url != statement.url:
            # Same figure, newer wording: keep pointing at the latest document.
            updated[code] = replace(_from_statement(statement, now), updated_at=current.updated_at)
    changed = tuple(
        sorted(
            code for code, entry in updated.items() if code not in stored or stored[code].allowance != entry.allowance
        )
    )
    if updated != stored:
        save_allowances(sources.year, updated)
    return changed


def pin(year: int, code: str, allowance: int, note: str) -> WriteResult:
    """Fix one element's allowance by hand; the ingest job will not change it."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pinned = AllowanceEntry(code, allowance, SOURCE_MANUAL, None, None, None, now, note)
    return save_allowances(year, {**load_allowances(year), code: pinned})


def unpin(year: int, code: str) -> WriteResult:
    """Drop a pinned value; the next ingest run takes the FIA's figure again."""
    entries = {key: entry for key, entry in load_allowances(year).items() if key != code}
    return save_allowances(year, entries)
