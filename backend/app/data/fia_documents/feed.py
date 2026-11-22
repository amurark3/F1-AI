"""A race weekend's FIA documents as a feed of typed events (the weekend live feed).

The ingest job (``scripts.ingest_fia_documents``, every five minutes over a
weekend) keeps the store current; this module only reads it. Each document is
one event: its number, title, kind and publication time as fia.com lists them
(``published``, and ``published_at``, the same instant in UTC),
plus what its parser reads from it (a penalty, a starting grid, deleted laps,
a classification, the entry list, the Pirelli compounds).
A document no parser covers yet still appears, with ``data`` empty, and one
whose text could not be read or parsed says why in ``unread``: the feed never
hides a decision because its PDF was awkward.

A client polls with ``after``, the highest document number it holds, and gets
only what is newer. The FIA numbers an event's documents in publication order.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import re
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.data.f1db_results import race_schedule
from app.data.fia_documents import store
from app.data.fia_documents.kinds import (
    KIND_CLASSIFICATION,
    KIND_DELETED_LAPS,
    KIND_ENTRY_LIST,
    KIND_GRID,
    KIND_PENALTY,
    KIND_PIRELLI,
    document_kind,
)
from app.data.fia_documents.listing import title_number
from app.data.fia_documents.parsers.classifications import parse_classification
from app.data.fia_documents.parsers.deleted_laps import parse_deleted_laps
from app.data.fia_documents.parsers.entry_list import parse_driver_change, parse_entry_list
from app.data.fia_documents.parsers.grids import parse_starting_grid
from app.data.fia_documents.parsers.pirelli import parse_pirelli_preview
from app.data.fia_documents.parsers.stewards import parse_stewards_decision
from app.data.fia_documents.rescission import withdrawn_numbers
from app.data.fia_documents.text import DocumentParseError, compact
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.data.fia_documents.document import SourceDocument

#: The ingest runs every five minutes, so a minute's reuse loses nothing new.
FEED_TTL_SECONDS = 60.0
_STARTING_GRID = re.compile(r"\bstarting\s+grid\b", re.IGNORECASE)
_DRIVER_CHANGE = re.compile(r"\bdriver\s+change\b", re.IGNORECASE)
#: fia.com prints its publication times as Paris wall-clock time, with no zone.
FIA_ZONE = ZoneInfo("Europe/Paris")
_CACHE: TtlCache[tuple[int, int], tuple[str | None, tuple[dict, ...]]] = TtlCache()


def _grid(document: SourceDocument) -> object | None:
    # The grid kind also holds parc fermé reports and permissions to start: only the grids parse.
    return parse_starting_grid(document.text or "") if _STARTING_GRID.search(document.title) else None


def _entries(document: SourceDocument) -> object:
    # The entry-list kind is the list itself and the stewards' driver-change decisions.
    text = document.text or ""
    return parse_driver_change(text) if _DRIVER_CHANGE.search(document.title) else parse_entry_list(text)


_PARSERS: dict[str, Callable[[SourceDocument], object | None]] = {
    KIND_PENALTY: lambda document: parse_stewards_decision(document.title, document.text or ""),
    KIND_GRID: _grid,
    KIND_DELETED_LAPS: lambda document: parse_deleted_laps(document.text or ""),
    KIND_CLASSIFICATION: lambda document: parse_classification(document.text or ""),
    KIND_ENTRY_LIST: _entries,
    KIND_PIRELLI: lambda document: parse_pirelli_preview(document.text or ""),
}


def published_at(published: str) -> str | None:
    """fia.com's printed time ("02.11.26 02:50", Paris wall clock) in UTC, ISO; ``None`` when it doesn't parse."""
    try:
        local = datetime.strptime(published.strip(), "%d.%m.%y %H:%M").replace(tzinfo=FIA_ZONE)
    except ValueError:
        return None
    return local.astimezone(UTC).isoformat()


def document_event(document: SourceDocument) -> dict:
    """One document as a feed event."""
    kind = document_kind(document.title)
    parse = _PARSERS.get(kind)
    data, unread = None, document.error
    if parse is not None and document.text is not None:
        try:
            parsed = parse(document)
        except DocumentParseError as exc:
            unread = str(exc)
        else:
            data = asdict(parsed) if parsed is not None else None
    return {
        "number": title_number(document.title),
        "title": document.title,
        "kind": kind,
        "published": document.published,
        "published_at": published_at(document.published),
        "url": document.url,
        "withdrawn": document.withdrawn,
        "data": data,
        "unread": unread,
    }


def fia_event(year: int, round_number: int) -> str | None:
    """The FIA's name for a round's event, as the store holds it; ``None`` before its first document."""
    name = next((race["name"] for race in race_schedule(year) if race["round"] == round_number), None)
    if name is None:
        return None
    wanted = compact(name)
    return next((event for event in sorted(store.events(year)) if compact(event) == wanted), None)


def _with_withdrawals(documents: tuple[SourceDocument, ...]) -> tuple[dict, ...]:
    """Events newest first; a document a later notice takes back reads "withdrawn by Doc N"."""
    events = [document_event(document) for document in documents]
    taken_back: dict[int, int] = {}
    for document, event in zip(documents, events, strict=True):
        for number in withdrawn_numbers(document.text or "", event["number"]):
            taken_back[number] = event["number"]
    stamped = (
        {**event, "withdrawn": f"withdrawn by Doc {taken_back[event['number']]}"}
        if event["withdrawn"] is None and event["number"] in taken_back
        else event
        for event in events
    )
    return tuple(sorted(stamped, key=lambda item: item["number"] or 0, reverse=True))


def _events(year: int, round_number: int) -> tuple[str | None, tuple[dict, ...]]:
    cached = _CACHE.get((year, round_number))
    if cached is not None:
        return cached
    event = fia_event(year, round_number)
    documents = store.load_event(year, event) if event else ()
    events = _with_withdrawals(documents)
    _CACHE.put((year, round_number), (event, events), FEED_TTL_SECONDS)
    return event, events


def weekend_feed(year: int, round_number: int, after: int | None = None) -> dict:
    """The round's documents newest first; with ``after``, only those numbered above it.

    Raises :class:`~app.data.fia_documents.store.FiaStoreError` when the store cannot be read.
    """
    event, events = _events(year, round_number)
    numbers = [item["number"] for item in events if item["number"] is not None]
    return {
        "year": year,
        "round": round_number,
        "event": event,
        "latest": max(numbers, default=None),
        "events": [item for item in events if after is None or (item["number"] or 0) > after],
    }
