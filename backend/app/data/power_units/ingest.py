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
by (see :mod:`.rescission` for the four ways it withdraws one). A document
missing from the page is only judged withdrawn when the page lists documents
numbered both below and above it: a page that lists nothing, or one cut short,
is a page this module could not read in full, not a withdrawal.

Every run finishes by bringing the stored allowances in line with the latest
figures the FIA's reports state (:mod:`.allowances`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import re
from typing import TYPE_CHECKING

import structlog

from app.data.power_units.allowances import refresh_from_reports
from app.data.power_units.documents import parse_document
from app.data.power_units.fia_site import (
    DOCUMENTS_INDEX_URL,
    EventPage,
    FetchError,
    ListedDocument,
    PoliteFetcher,
    active_event,
    is_power_unit_title,
    listed_documents,
    pdf_text,
    season_events,
    season_page_url,
)
from app.data.power_units.rescission import is_withdrawal_notice_title, marks_withdrawn
from app.data.power_units.sources import SeasonSources, SourceDocument, load_season, save_season
from app.data.power_units.text import DocumentParseError

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = structlog.get_logger()

WITHDRAWN_UNLISTED = "no longer listed on the FIA event page"
_TITLE_NUMBER = re.compile(r"^\s*Doc\s+(?P<number>\d+)\b", re.IGNORECASE)


class IngestError(RuntimeError):
    """The FIA site did not offer what a run needs to proceed."""


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wanted(title: str) -> bool:
    return is_power_unit_title(title) or is_withdrawal_notice_title(title)


def _events_to_check(
    events: tuple[EventPage, ...],
    current: str | None,
    collected: Iterable[SourceDocument],
    all_events: bool,
) -> tuple[EventPage, ...]:
    if all_events:
        return events
    covered = {document.event for document in collected}
    return tuple(event for event in events if event.name == current or event.name not in covered)


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
    base = SourceDocument(
        url=listed.url,
        event=listed.event,
        title=listed.title,
        published=listed.published,
        sha256="",
        fetched_at=_now(),
        text=None,
    )
    try:
        data = fetcher.document(listed.url)
    except FetchError as exc:
        reason = f"download failed: {exc}"
        return _Collected(replace(base, error=reason), reason)
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = pdf_text(data)
    except DocumentParseError as exc:
        return _Collected(replace(base, sha256=digest, error=str(exc)), str(exc))
    return _Collected(replace(base, sha256=digest, text=text), _parse_failure(text))


def _listing(fetcher: PoliteFetcher, year: int) -> tuple[tuple[EventPage, ...], str | None]:
    season_url = season_page_url(fetcher.page(DOCUMENTS_INDEX_URL), year)
    if season_url is None:
        raise IngestError(f"the FIA documents index lists no {year} season")
    season_html = fetcher.page(season_url)
    events = season_events(season_html)
    if not events:
        raise IngestError(f"the {year} season page links no events")
    return events, active_event(season_html)


def _merge(existing: tuple[SourceDocument, ...], fresh: list[SourceDocument]) -> tuple[SourceDocument, ...]:
    """Fresh copies replace held ones by URL; nothing held is ever dropped."""
    by_url = {document.url: document for document in existing}
    by_url.update({document.url: document for document in fresh})
    return tuple(by_url.values())


def _title_number(title: str) -> int | None:
    match = _TITLE_NUMBER.match(title)
    return int(match["number"]) if match else None


def _resettled(document: SourceDocument, listing: tuple[ListedDocument, ...]) -> SourceDocument:
    """``document`` as its event page now shows it: current title, withdrawn or not."""
    current = next((item for item in listing if item.url == document.url), None)
    if current is not None:
        marked = f"marked on the FIA event page: {current.title}" if marks_withdrawn(current.title) else None
        return replace(document, title=current.title, withdrawn=marked)
    numbers = [number for number in (_title_number(item.title) for item in listing) if number is not None]
    own = _title_number(document.title)
    if own is None or not numbers or not min(numbers) <= own <= max(numbers):
        return document
    return replace(document, withdrawn=WITHDRAWN_UNLISTED)


def _settle_withdrawn(
    documents: tuple[SourceDocument, ...],
    listings: dict[str, tuple[ListedDocument, ...]],
) -> tuple[SourceDocument, ...]:
    """Re-judge every held document of each event page this run read in full."""
    return tuple(
        _resettled(document, listings[document.event]) if listings.get(document.event) else document
        for document in documents
    )


def ingest_season(year: int, fetcher: PoliteFetcher, *, all_events: bool = False) -> IngestReport:
    """Collect every power-unit document of ``year`` not already stored.

    Raises :class:`~app.data.power_units.sources.SourcesUnavailableError` when
    the store cannot be read, :class:`IngestError` when the FIA site does not
    list the season, and :class:`FetchError` when one of its pages cannot be
    fetched — a run that cannot see the whole picture writes nothing.
    """
    existing = load_season(year)
    events, current = _listing(fetcher, year)
    targets = _events_to_check(events, current, existing.documents, all_events)

    held = {document.url for document in existing.documents if document.text is not None}
    listings = {event.name: listed_documents(fetcher.page(event.url), event.name) for event in targets}
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
        failed=tuple(f"{item.document.title}: {item.problem}" for item in collected if item.problem),
        written=False,
        withdrawn=tuple(
            document.title for document in documents if document.withdrawn and not was_withdrawn.get(document.url)
        ),
    )
    if documents != existing.documents:
        result = save_season(SeasonSources(year=year, documents=documents, updated_at=_now()))
        logger.info("power_units.ingested", year=year, added=len(report.added), failed=len(report.failed), ok=result.ok)
        report = replace(report, written=result.ok, write_error=None if result.ok else result.error)
    return replace(
        report,
        allowances_changed=refresh_from_reports(SeasonSources(year=year, documents=documents), _now()),
    )
