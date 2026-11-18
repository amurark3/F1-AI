"""What the FIA lists for a season, and what that says about documents already held.

Shared by every ingest of FIA documents: read the season's event list, read
event pages (a page that fails is reported, never fatal), download one listed
document, and re-judge a held document against its event page as it reads now.

A document missing from the page is only judged withdrawn when the page lists
documents numbered both below and above it: a page that lists nothing, or one
cut short, is a page that could not be read in full, not a withdrawal.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import re
from typing import TYPE_CHECKING

from app.data.fia_documents.document import SourceDocument
from app.data.fia_documents.rescission import marks_withdrawn
from app.data.fia_documents.site import (
    DOCUMENTS_INDEX_URL,
    EventPage,
    FetchError,
    ListedDocument,
    PoliteFetcher,
    active_event,
    listed_documents,
    pdf_text,
    season_events,
    season_page_url,
)
from app.data.fia_documents.text import DocumentParseError

if TYPE_CHECKING:
    from collections.abc import Iterable

WITHDRAWN_UNLISTED = "no longer listed on the FIA event page"
_TITLE_NUMBER = re.compile(r"^\s*Doc\s+(?P<number>\d+)\b", re.IGNORECASE)


class IngestError(RuntimeError):
    """The FIA site did not offer what a run needs to proceed."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def season_listing(fetcher: PoliteFetcher, year: int) -> tuple[tuple[EventPage, ...], str | None]:
    """The season's events and the one the FIA marks as current.

    Raises :class:`IngestError` when the index lists no such season or the
    season page links no events, and :class:`FetchError` when either page
    cannot be fetched.
    """
    season_url = season_page_url(fetcher.page(DOCUMENTS_INDEX_URL), year)
    if season_url is None:
        raise IngestError(f"the FIA documents index lists no {year} season")
    season_html = fetcher.page(season_url)
    events = season_events(season_html)
    if not events:
        raise IngestError(f"the {year} season page links no events")
    return events, active_event(season_html)


def events_to_check(
    events: tuple[EventPage, ...],
    current: str | None,
    collected: Iterable[SourceDocument],
    all_events: bool,
) -> tuple[EventPage, ...]:
    """Every event with ``all_events``; otherwise the current one and those with nothing collected."""
    if all_events:
        return events
    covered = {document.event for document in collected}
    return tuple(event for event in events if event.name == current or event.name not in covered)


def read_event_pages(
    fetcher: PoliteFetcher,
    events: Iterable[EventPage],
) -> tuple[dict[str, tuple[ListedDocument, ...]], tuple[str, ...]]:
    """Every event page that answered, and a line for each one that did not.

    A page left unread is tried again by a later run.
    """
    listings: dict[str, tuple[ListedDocument, ...]] = {}
    unreachable: list[str] = []
    for event in events:
        try:
            listings[event.name] = listed_documents(fetcher.page(event.url), event.name)
        except FetchError as exc:
            unreachable.append(f"{event.name} event page: {exc}")
    return listings, tuple(unreachable)


def download(fetcher: PoliteFetcher, listed: ListedDocument) -> tuple[SourceDocument, str | None]:
    """Download and read one listed document, and why it has no text, if it has none.

    A failure is recorded on the document, never raised: the document is kept
    without text and a later run tries it again.
    """
    base = SourceDocument(
        url=listed.url,
        event=listed.event,
        title=listed.title,
        published=listed.published,
        sha256="",
        fetched_at=now(),
        text=None,
    )
    try:
        data = fetcher.document(listed.url)
    except FetchError as exc:
        reason = f"download failed: {exc}"
        return replace(base, error=reason), reason
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = pdf_text(data)
    except DocumentParseError as exc:
        return replace(base, sha256=digest, error=str(exc)), str(exc)
    return replace(base, sha256=digest, text=text), None


def title_number(title: str) -> int | None:
    """The FIA's document number from a listed title ("Doc 86 - …"), or ``None``."""
    match = _TITLE_NUMBER.match(title)
    return int(match["number"]) if match else None


def resettled(document: SourceDocument, listing: tuple[ListedDocument, ...]) -> SourceDocument:
    """``document`` as its event page now shows it: current title, withdrawn or not."""
    current = next((item for item in listing if item.url == document.url), None)
    if current is not None:
        marked = f"marked on the FIA event page: {current.title}" if marks_withdrawn(current.title) else None
        return replace(document, title=current.title, withdrawn=marked)
    numbers = [number for number in (title_number(item.title) for item in listing) if number is not None]
    own = title_number(document.title)
    if own is None or not numbers or not min(numbers) <= own <= max(numbers):
        return document
    return replace(document, withdrawn=WITHDRAWN_UNLISTED)
