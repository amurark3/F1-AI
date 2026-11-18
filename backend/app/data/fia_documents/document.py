"""One FIA document as collected: where it came from, and its text.

Text rather than facts is stored, so a parser fix applies to every document
already collected without asking the FIA for anything again.

A document whose download or text extraction failed is kept with ``text``
unset and the reason in ``error``; the next run that reads its event page tries
it again. A document the FIA later takes back is kept, with the reason in
``withdrawn`` (see :mod:`.rescission`).
"""

from __future__ import annotations

from dataclasses import dataclass

_TEXT_FIELDS = ("url", "event", "title", "published", "sha256", "fetched_at")


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
