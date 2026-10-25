"""Find and fetch the FIA's power-unit documents, politely.

fia.com publishes event documents as PDFs behind three kinds of page, with no
feed or API (layout verified October 2026):

``/documents/championships/fia-formula-one-world-championship-14``
    The index. Links every season page, ``…/season/season-<year>-<id>`` —
    2026 is ``season-2026-2072``. The id is read from here rather than
    hardcoded, because it changes every year.
season page
    Every event of the season (the current one marked ``event-title active``)
    and a link to each event's page.
event page
    One ``<li class="document-row">`` per document: the PDF link, a title such
    as "Doc 20 - Infringement - Car 63 - Changes to PU elements", and
    "Published on 09.10.26 14:03 CET".

The site serves two markups of the same page — a flat one, and one wrapping
every field in Drupal ``field-item`` divs — depending on the client. Rows are
read by the anchors both share (the row class, ``class="title"``,
``class="published"``) with tags stripped, never by a fixed nesting.

robots.txt asks for ten seconds between requests and disallows none of these
paths. :class:`PoliteFetcher` enforces that delay on every request it makes.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import io
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import unquote, urljoin, urlsplit

import requests
import structlog

from app.data.power_units.text import DocumentParseError, squash

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = structlog.get_logger()

FIA_BASE_URL = "https://www.fia.com"
DOCUMENTS_INDEX_URL = f"{FIA_BASE_URL}/documents/championships/fia-formula-one-world-championship-14"
#: robots.txt ``Crawl-delay``.
CRAWL_DELAY_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 60
USER_AGENT = "F1-AI power-unit tracker (github.com/amurark3/F1-AI; honours robots.txt crawl-delay)"

_SEASON_PATH = re.compile(
    r"(?P<path>/documents/championships/fia-formula-one-world-championship-14/season/season-(?P<year>\d{4})-\d+)(?=[\"'/?#])",
)
_EVENT_PATH = re.compile(r"(?P<path>/documents/championships/[^\"'<>\s]+?/season/season-\d{4}-\d+/event/[^\"'<>\s?#]+)")
_ACTIVE_EVENT = re.compile(r'class="event-title active"[^>]*>\s*(?P<name>[^<]+?)\s*<')
_ROW_MARKER = '<li class="document-row'
_PDF_LINK = re.compile(r'href="(?P<href>[^"]+\.pdf)"', re.IGNORECASE)
_PUBLISHED = re.compile(r'date-display-single"[^>]*>\s*(?P<when>[^<]+?)\s*<')
_TAG = re.compile(r"<[^>]+>")
_POWER_UNIT_TITLE = re.compile(r"\bPU\b|\bpower\s+unit", re.IGNORECASE)
# "Power Unit Information" is the race director's energy and overtake limits
# for the circuit — nothing to do with element usage.
_NOT_USAGE_TITLE = re.compile(r"power\s+unit\s+information", re.IGNORECASE)


class FetchError(RuntimeError):
    """A page or document could not be downloaded."""


@dataclass(frozen=True)
class EventPage:
    """One event of the season, as the season page links it."""

    name: str
    url: str


@dataclass(frozen=True)
class ListedDocument:
    """One row of an event page."""

    event: str
    title: str
    url: str
    published: str


def season_page_url(index_html: str, year: int) -> str | None:
    """The season page for ``year`` as the index links it, or ``None``."""
    for match in _SEASON_PATH.finditer(index_html):
        if int(match["year"]) == year:
            return urljoin(FIA_BASE_URL, match["path"])
    return None


def season_events(season_html: str) -> tuple[EventPage, ...]:
    """Every event the season page links, in first-seen order, without repeats."""
    events: dict[str, EventPage] = {}
    for match in _EVENT_PATH.finditer(season_html):
        path = match["path"]
        name = unquote(path.rsplit("/", 1)[-1])
        events.setdefault(name, EventPage(name=name, url=urljoin(FIA_BASE_URL, path)))
    return tuple(events.values())


def active_event(season_html: str) -> str | None:
    """The event the season page marks as current."""
    match = _ACTIVE_EVENT.search(season_html)
    return html.unescape(match["name"]) if match else None


def _rows(page_html: str) -> Iterator[str]:
    for chunk in page_html.split(_ROW_MARKER)[1:]:
        yield chunk.split("</li>", 1)[0]


def _listed(block: str, event: str) -> ListedDocument | None:
    link = _PDF_LINK.search(block)
    title_at = block.find('class="title"')
    published_at = block.find('class="published"')
    if link is None or title_at < 0 or published_at < title_at:
        return None
    # From the end of the title tag to the start of the tag carrying the
    # published date: everything between is the title, in either markup.
    title_html = block[block.index(">", title_at) + 1 : block.rfind("<", title_at, published_at)]
    title = squash(html.unescape(_TAG.sub(" ", title_html)))
    published = _PUBLISHED.search(block)
    return ListedDocument(
        event=event,
        title=title,
        url=urljoin(FIA_BASE_URL, html.unescape(link["href"])),
        published=published["when"] if published else "",
    )


def listed_documents(page_html: str, event: str) -> tuple[ListedDocument, ...]:
    """Every document row on an event page, newest first as the FIA lists them."""
    rows = (_listed(block, event) for block in _rows(page_html))
    return tuple(row for row in rows if row is not None)


def is_power_unit_title(title: str) -> bool:
    """Whether a listed title is worth downloading as power-unit evidence.

    Deliberately loose — anything mentioning PU — because the parsers decide
    what a document is from its text. A decision only about parc fermé is
    collected, read, and set aside as unrelated; one about engines that this
    filter skipped would simply be missing.
    """
    return bool(_POWER_UNIT_TITLE.search(title)) and not _NOT_USAGE_TITLE.search(title)


def pdf_text(data: bytes) -> str:
    """Text of every page of a PDF, in order.

    pypdf is imported here rather than at module scope: it is an ingest-only
    dependency (``requirements-ingest.txt``) that the web service never needs.
    """
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise DocumentParseError(f"PDF text could not be extracted: {exc}") from exc


class PoliteFetcher:
    """HTTP GET with the FIA's crawl delay between requests.

    ``cache_dir`` serves PDFs already on disk instead of downloading them again
    — a backfill re-run, or a run seeded from an earlier mirror, then costs the
    FIA nothing. Pages are never cached: they are what changes.
    """

    def __init__(
        self,
        *,
        delay_seconds: float = CRAWL_DELAY_SECONDS,
        session: requests.Session | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self._delay = delay_seconds
        self._session = session or requests.Session()
        self._cache_dir = cache_dir
        self._last_request: float | None = None
        self.requests_made = 0

    def _wait_turn(self) -> None:
        if self._last_request is None:
            return
        remaining = self._delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, url: str) -> bytes:
        self._wait_turn()
        try:
            response = self._session.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"GET {url} failed: {exc}") from exc
        finally:
            self._last_request = time.monotonic()
            self.requests_made += 1
        return response.content

    def page(self, url: str) -> str:
        """An HTML page, decoded."""
        return self._get(url).decode("utf-8", errors="replace")

    def document(self, url: str) -> bytes:
        """A PDF's bytes, from ``cache_dir`` when it already holds them."""
        cached = self._cache_dir / unquote(Path(urlsplit(url).path).name) if self._cache_dir else None
        if cached is not None and cached.is_file():
            return cached.read_bytes()
        data = self._get(url)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        return data
