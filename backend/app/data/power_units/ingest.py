"""Keep the stored power-unit corpus in step with what the FIA has published.

One run reads the FIA index and the season page, then the page of every event
that needs looking at:

* the event the season page marks as current — documents keep arriving there
  from Thursday's first report until Sunday night's last decision;
* every event with no document collected yet — which on the first run is all
  of them, so a backfill is just the first run;
* every event, with ``all_events`` — the daily run, which is what notices a
  document the FIA takes back after its weekend has moved off the season page.

Only documents not already held are downloaded (and ones whose earlier
download or text extraction failed, which are tried again). A scheduled run in
a quiet week therefore costs the FIA three page requests.

Each new document is parsed as soon as it is read, so a template change shows
up in this run's report — and the job's exit status — rather than first on
the screen.

Every event page read also settles which held documents the FIA still stands
by (see :mod:`app.data.fia_documents.rescission` for the four ways it
withdraws one, and :mod:`app.data.fia_documents.listing` for when a missing
document counts as withdrawn).

Every run finishes by bringing the stored allowances in line with the latest
figures the FIA's reports state (:mod:`.allowances`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import TYPE_CHECKING

import structlog

from app.data.fia_documents.listing import (
    download,
    events_to_check,
    now,
    read_event_pages,
    resettled,
    season_listing,
)
from app.data.fia_documents.rescission import is_withdrawal_notice_title
from app.data.fia_documents.text import DocumentParseError
from app.data.power_units.allowances import refresh_from_reports
from app.data.power_units.documents import parse_document
from app.data.power_units.sources import SeasonSources, load_season, save_season

if TYPE_CHECKING:
    from app.data.fia_documents.document import SourceDocument
    from app.data.fia_documents.site import ListedDocument, PoliteFetcher

logger = structlog.get_logger()

_POWER_UNIT_TITLE = re.compile(r"\bPU\b|\bpower\s+unit", re.IGNORECASE)
# "Power Unit Information" is the race director's energy and overtake limits
# for the circuit — nothing to do with element usage.
_NOT_USAGE_TITLE = re.compile(r"power\s+unit\s+information", re.IGNORECASE)


@dataclass(frozen=True)
class IngestReport:
    """What one run did."""

    year: int
    events_checked: tuple[str, ...]
    added: tuple[str, ...]
    #: ``"<title>: <reason>"`` for each document that could not be read.
    failed: tuple[str, ...]
    written: bool
    #: Held documents this run found the FIA has taken back.
    withdrawn: tuple[str, ...] = ()
    #: Element codes whose stored allowance this run changed.
    allowances_changed: tuple[str, ...] = ()
    write_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed and self.write_error is None


def is_power_unit_title(title: str) -> bool:
    """Whether a listed title is worth downloading as power-unit evidence.

    Deliberately loose — anything mentioning PU — because the parsers decide
    what a document is from its text. A decision only about parc fermé is
    collected, read, and set aside as unrelated; one about engines that this
    filter skipped would simply be missing.
    """
    return bool(_POWER_UNIT_TITLE.search(title)) and not _NOT_USAGE_TITLE.search(title)


def _wanted(title: str) -> bool:
    return is_power_unit_title(title) or is_withdrawal_notice_title(title)


def _parse_failure(text: str) -> str | None:
    try:
        parse_document(text)
    except DocumentParseError as exc:
        return str(exc)
    return None


@dataclass(frozen=True)
class _Collected:
    document: SourceDocument
    #: Why the document cannot be used yet — download, extraction or parse.
    problem: str | None = None


def _collect(fetcher: PoliteFetcher, listed: ListedDocument) -> _Collected:
    """Download and read one document; failures are recorded, not raised.

    Only a failure that leaves no text is stored on the document: a parse
    failure is reported for this run, but the text is kept, because the parser
    runs again at read time and a fixed parser should not inherit a stale error.
    """
    document, problem = download(fetcher, listed)
    if document.text is None:
        return _Collected(document, problem)
    return _Collected(document, _parse_failure(document.text))


def _merge(existing: tuple[SourceDocument, ...], fresh: list[SourceDocument]) -> tuple[SourceDocument, ...]:
    """Fresh copies replace held ones by URL; nothing held is ever dropped."""
    by_url = {document.url: document for document in existing}
    by_url.update({document.url: document for document in fresh})
    return tuple(by_url.values())


def _settle_withdrawn(
    documents: tuple[SourceDocument, ...],
    listings: dict[str, tuple[ListedDocument, ...]],
) -> tuple[SourceDocument, ...]:
    """Re-judge every held document of each event page this run read in full."""
    return tuple(
        resettled(document, listings[document.event]) if listings.get(document.event) else document
        for document in documents
    )


def ingest_season(year: int, fetcher: PoliteFetcher, *, all_events: bool = False) -> IngestReport:
    """Collect every power-unit document of ``year`` not already stored.

    Raises :class:`~app.data.power_units.sources.SourcesUnavailableError` when
    the store cannot be read, :class:`IngestError` when the FIA site does not
    list the season, and :class:`FetchError` when the index or season page
    cannot be fetched — without those a run cannot see what to collect, so it
    writes nothing. An event page that cannot be fetched is reported and
    skipped: every other event still collects, and that event's held documents
    stay exactly as they were, because nothing is judged withdrawn from a page
    this run did not read.
    """
    existing = load_season(year)
    events, current = season_listing(fetcher, year)
    targets = events_to_check(events, current, existing.documents, all_events)

    held = {document.url for document in existing.documents if document.text is not None}
    listings, unreachable = read_event_pages(fetcher, targets)
    collected = [
        _collect(fetcher, listed)
        for items in listings.values()
        for listed in items
        if _wanted(listed.title) and listed.url not in held
    ]

    documents = _settle_withdrawn(_merge(existing.documents, [item.document for item in collected]), listings)
    was_withdrawn = {document.url: document.withdrawn for document in existing.documents}
    report = IngestReport(
        year=year,
        events_checked=tuple(event.name for event in targets),
        added=tuple(item.document.title for item in collected if not item.problem),
        failed=(*unreachable, *(f"{item.document.title}: {item.problem}" for item in collected if item.problem)),
        written=False,
        withdrawn=tuple(
            document.title for document in documents if document.withdrawn and not was_withdrawn.get(document.url)
        ),
    )
    if documents != existing.documents:
        result = save_season(SeasonSources(year=year, documents=documents, updated_at=now()))
        logger.info("power_units.ingested", year=year, added=len(report.added), failed=len(report.failed), ok=result.ok)
        report = replace(report, written=result.ok, write_error=None if result.ok else result.error)
    return replace(
        report,
        allowances_changed=refresh_from_reports(SeasonSources(year=year, documents=documents), now()),
    )
