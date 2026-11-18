"""Keep the stored FIA documents in step with every event page of a season.

One run reads the FIA index and the season page, then the page of every event
that needs looking at:

* the event the season page marks as current — documents keep arriving there
  from Thursday's first note until Sunday night's last decision;
* every event with nothing collected yet, at most ``max_new_events`` of them
  per run: a past weekend is about 85 documents, fifteen minutes at the crawl
  delay, so a scheduled run can backfill a season a few events at a time and
  still check the current event promptly;
* every event already collected, with ``all_events`` — which notices a
  document the FIA takes back after its weekend.

Every document an event page lists is collected, whatever its kind (see
:mod:`.kinds`), but only once: a document already held with its text is never
downloaded again, and one whose download or extraction failed is tried again
the next time its page is read. Each event's documents are saved as soon as
that event is done, so a run cut short keeps what it collected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.data.fia_documents import store
from app.data.fia_documents.listing import download, read_event_pages, resettled, season_listing

if TYPE_CHECKING:
    from app.data.fia_documents.site import ListedDocument, PoliteFetcher

logger = structlog.get_logger()


@dataclass(frozen=True)
class IngestReport:
    """What one run did."""

    year: int
    events_checked: tuple[str, ...]
    #: Titles of the documents collected with their text.
    added: tuple[str, ...]
    #: ``"<title>: <reason>"`` per unread document, and a line per unreadable event page.
    failed: tuple[str, ...]
    #: Held documents this run found the FIA has taken back.
    withdrawn: tuple[str, ...] = ()
    #: Events with nothing collected that this run left for a later one (``max_new_events``).
    deferred: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failed


def _ingest_event(fetcher: PoliteFetcher, year: int, event: str, listing: tuple[ListedDocument, ...]) -> IngestReport:
    """Collect one event page's new documents and re-judge the ones held; save what changed."""
    held = {document.url: document for document in store.load_event(year, event)}
    collected = [download(fetcher, item) for item in listing if item.url not in held or held[item.url].text is None]
    merged = {**held, **{document.url: document for document, _problem in collected}}
    changed = tuple(
        document for document in (resettled(document, listing) for document in merged.values())
        if document != held.get(document.url)
    )  # fmt: skip
    if changed:
        store.save(year, changed)
    was_withdrawn = {url for url, document in held.items() if document.withdrawn}
    return IngestReport(
        year=year,
        events_checked=(event,),
        added=tuple(document.title for document, problem in collected if problem is None),
        failed=tuple(f"{document.title}: {problem}" for document, problem in collected if problem),
        withdrawn=tuple(
            document.title for document in changed if document.withdrawn and document.url not in was_withdrawn
        ),
    )


def ingest_season(
    year: int,
    fetcher: PoliteFetcher,
    *,
    all_events: bool = False,
    max_new_events: int | None = None,
) -> IngestReport:
    """Collect every document of ``year`` not already held.

    Raises :class:`~app.data.fia_documents.store.FiaStoreError` when the store
    cannot be read or written, :class:`~app.data.fia_documents.listing.IngestError`
    when the FIA site does not list the season, and
    :class:`~app.data.fia_documents.site.FetchError` when the index or season
    page cannot be fetched. An event page that cannot be fetched is reported and
    skipped; that event's held documents stay exactly as they were.
    """
    events, current = season_listing(fetcher, year)
    covered = store.events(year)
    new = [event for event in events if event.name != current and event.name not in covered]
    started = new if max_new_events is None else new[:max_new_events]
    targets = tuple(
        event for event in events if event.name == current or event in started or (all_events and event.name in covered)
    )
    deferred = tuple(event.name for event in new[len(started) :])
    listings, unreachable = read_event_pages(fetcher, targets)
    done = [_ingest_event(fetcher, year, event, items) for event, items in listings.items()]
    report = IngestReport(
        year=year,
        events_checked=tuple(event.name for event in targets),
        added=tuple(title for result in done for title in result.added),
        failed=(*unreachable, *(line for result in done for line in result.failed)),
        withdrawn=tuple(title for result in done for title in result.withdrawn),
        deferred=deferred,
    )
    logger.info(
        "fia_documents.ingested",
        year=year,
        events=len(targets),
        added=len(report.added),
        failed=len(report.failed),
        deferred=len(deferred),
    )
    return report
