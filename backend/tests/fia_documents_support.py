"""The 2026 Mexico City GP's documents as fia.com served them (fetched 2026-11-18).

Every penalty, grid, deleted-lap, classification, entry-list and Pirelli
document of R19, each title with its extracted text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.data.fia_documents import feed, store
from app.data.fia_documents.document import SourceDocument
from app.data.fia_documents.store import FileFiaStore

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pytest

MEXICO_EVENT = "Mexico City Grand Prix"

MEXICO_2026: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "fixtures" / "fia_documents" / "mexico_2026_texts.json").read_text(encoding="utf-8")
)


def mexico(number: int) -> tuple[str, str]:
    """Document ``number``'s title and text."""
    title = next(title for title in MEXICO_2026 if title.startswith(f"Doc {number} - "))
    return title, MEXICO_2026[title]["text"]


def held(title: str) -> SourceDocument:
    """R19's document ``title`` as the store holds it."""
    entry = MEXICO_2026[title]
    return SourceDocument(
        url=entry["url"],
        event=MEXICO_EVENT,
        title=title,
        published=entry["published"],
        sha256="0" * 64,
        fetched_at="2026-11-18T09:00:00+00:00",
        text=entry["text"],
    )


def hold(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    documents: Iterable[SourceDocument] | None = None,
    round_number: int = 19,
) -> FileFiaStore:
    """A store holding ``documents`` (every R19 document by default), with the calendar naming ``round_number`` Mexico."""
    files = FileFiaStore(root)
    files.save(2026, list(documents) if documents is not None else [held(title) for title in MEXICO_2026])
    monkeypatch.setattr(store, "STORE", files)
    monkeypatch.setattr(feed, "race_schedule", lambda year: [{"round": round_number, "name": MEXICO_EVENT}])
    return files
