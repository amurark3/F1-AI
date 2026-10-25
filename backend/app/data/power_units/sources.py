"""The stored corpus: every collected power-unit document's text, by season.

One document in the shared store, ``power_unit_sources``::

    {"seasons": {"2026": {"updated_at": "…", "documents": [
        {"url": …, "event": "Singapore Grand Prix", "title": "Doc 10 - …",
         "published": "09.10.26 12:30", "sha256": …, "fetched_at": …,
         "text": "2026 SINGAPORE GRAND PRIX …", "error": null}, …]}}}

Only the ingest job writes it. The web service only reads it, so a
long-running server cannot overwrite a newer corpus with the copy it loaded
at boot — the hazard that erases out-of-process writes to the prediction
cache.

A document whose download or text extraction failed is kept with ``text``
unset and the reason in ``error``: the screen lists it as unread, and the next
ingest run tries it again.

A document the FIA later takes back is kept, with the reason in
``withdrawn``. It happens when a decision is corrected — at Belgium 2026 the
stewards replaced two decisions and only the corrected ones stayed listed —
and counting both would double the penalty. See
:mod:`app.data.power_units.rescission` for every way it is noticed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.data.store import DOCUMENT_POWER_UNIT_SOURCES, document_store

if TYPE_CHECKING:
    from app.data.store_types import WriteResult

logger = structlog.get_logger()

_TEXT_FIELDS = ("url", "event", "title", "published", "sha256", "fetched_at")


class SourcesUnavailableError(RuntimeError):
    """The store could not be read, so nothing may be concluded — or written."""


@dataclass(frozen=True)
class SourceDocument:
    """One collected FIA document."""

    url: str
    event: str
    title: str
    published: str
    sha256: str
    fetched_at: str
    text: str | None
    error: str | None = None
    #: Why the FIA no longer stands by the document; ``None`` while it does.
    withdrawn: str | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "event": self.event,
            "title": self.title,
            "published": self.published,
            "sha256": self.sha256,
            "fetched_at": self.fetched_at,
            "text": self.text,
            "error": self.error,
            "withdrawn": self.withdrawn,
        }

    @classmethod
    def from_dict(cls, raw: object) -> SourceDocument | None:
        """A stored entry, or ``None`` for one missing its identity fields."""
        if not isinstance(raw, dict) or not all(isinstance(raw.get(key), str) for key in _TEXT_FIELDS):
            return None
        optional = {key: raw.get(key) for key in ("text", "error", "withdrawn")}
        return cls(
            **{key: raw[key] for key in _TEXT_FIELDS},
            **{key: value if isinstance(value, str) else None for key, value in optional.items()},
        )


@dataclass(frozen=True)
class SeasonSources:
    """Every document collected for one season."""

    year: int
    documents: tuple[SourceDocument, ...]
    updated_at: str | None = None


def _read_payload() -> dict:
    result = document_store.read(DOCUMENT_POWER_UNIT_SOURCES)
    if not result.ok:
        raise SourcesUnavailableError(result.error or "power-unit sources could not be read")
    return result.payload or {}


def _season_entry(payload: dict, year: int) -> dict:
    seasons = payload.get("seasons")
    entry = seasons.get(str(year)) if isinstance(seasons, dict) else None
    return entry if isinstance(entry, dict) else {}


def load_season(year: int) -> SeasonSources:
    """The season's corpus; empty when nothing has been collected yet.

    Raises :class:`SourcesUnavailableError` when the store cannot be read —
    an outage must never look like a season with no documents.
    """
    entry = _season_entry(_read_payload(), year)
    raw_documents = entry.get("documents")
    documents = tuple(
        document
        for document in (SourceDocument.from_dict(raw) for raw in (raw_documents or []))
        if document is not None
    )
    updated_at = entry.get("updated_at")
    return SeasonSources(
        year=year,
        documents=documents,
        updated_at=updated_at if isinstance(updated_at, str) else None,
    )


def save_season(season: SeasonSources) -> WriteResult:
    """Replace one season's corpus, keeping every other season as stored.

    Reads first so other seasons survive; a failed read raises instead of
    writing, because writing on top of an unread document would drop them.
    """
    payload = _read_payload()
    seasons = payload.get("seasons")
    merged = {
        **(seasons if isinstance(seasons, dict) else {}),
        str(season.year): {
            "updated_at": season.updated_at,
            "documents": [document.as_dict() for document in season.documents],
        },
    }
    result = document_store.write(DOCUMENT_POWER_UNIT_SOURCES, {**payload, "seasons": merged})
    logger.info(
        "power_units.sources_saved",
        year=season.year,
        documents=len(season.documents),
        ok=result.ok,
        durable=result.durable,
    )
    return result
