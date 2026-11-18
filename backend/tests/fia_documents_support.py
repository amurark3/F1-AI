"""The 2026 Mexico City GP's documents as fia.com served them (fetched 2026-11-18).

Every penalty, grid, deleted-lap, classification, entry-list and Pirelli
document of R19, each title with its extracted text.
"""

from __future__ import annotations

import json
from pathlib import Path

MEXICO_2026: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "fixtures" / "fia_documents" / "mexico_2026_texts.json").read_text(encoding="utf-8")
)


def mexico(number: int) -> tuple[str, str]:
    """Document ``number``'s title and text."""
    title = next(title for title in MEXICO_2026 if title.startswith(f"Doc {number} - "))
    return title, MEXICO_2026[title]["text"]
