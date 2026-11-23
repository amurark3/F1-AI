"""Fill ``rulebook_chunk.embedding_gemini`` for every passage that lacks one.

``python -m app.rag.gemini_backfill`` embeds the NULL rows in batches, paced
under the free tier's tokens-per-minute limit. A spent quota (429) stops it
cleanly with the filled and remaining counts; rerunning continues from the rows
still NULL. Rows without a Gemini vector are still found by keywords.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys
import time
from typing import TYPE_CHECKING

import structlog

from app.rag import gemini_embeddings, pgvector_store
from app.utils.embeddings import to_pgvector_literal

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

BATCH_SIZE = 20
# Free tier, measured 2026-11-22: every text in a batch counts as one request
# against 100 a minute. shortcut: fixed budgets under that and an assumed 30k
# tokens/minute (4 characters a token); update them if AI Studio's limits change.
TEXTS_PER_MINUTE = 90
TOKENS_PER_MINUTE = 25_000
_CHARS_PER_TOKEN = 4
_QUOTA_EXHAUSTED = 429

_NEXT_BATCH = "SELECT id, content FROM rulebook_chunk WHERE embedding_gemini IS NULL ORDER BY id LIMIT %s"
_STORE = "UPDATE rulebook_chunk SET embedding_gemini = %s::vector WHERE id = %s"
_REMAINING = "SELECT COUNT(*) FROM rulebook_chunk WHERE embedding_gemini IS NULL"


@dataclass(frozen=True)
class BackfillResult:
    filled: int
    remaining: int
    error: Exception | None = None

    @property
    def quota_stop(self) -> bool:
        return getattr(self.error, "code", None) == _QUOTA_EXHAUSTED


def pace_seconds(texts: list[str]) -> float:
    """How long to wait after sending ``texts`` to stay under both per-minute budgets."""
    tokens = sum(len(t) for t in texts) / _CHARS_PER_TOKEN
    return 60 * max(len(texts) / TEXTS_PER_MINUTE, tokens / TOKENS_PER_MINUTE)


def backfill(*, batch_size: int = BATCH_SIZE, sleep: Callable[[float], None] = time.sleep) -> BackfillResult:
    """Embed NULL rows until none are left or Gemini refuses; report what happened."""
    filled = 0
    error: Exception | None = None
    with pgvector_store.connect() as conn:
        while rows := conn.execute(_NEXT_BATCH, [batch_size]).fetchall():
            texts = [row[1] for row in rows]
            try:
                vectors = gemini_embeddings.embed_documents(texts)
            except Exception as exc:
                logger.warning("gemini_backfill.stopped", status=getattr(exc, "code", None), error=str(exc))
                error = exc
                break
            with conn.cursor() as cur:
                cur.executemany(
                    _STORE, [(to_pgvector_literal(v), row[0]) for row, v in zip(rows, vectors, strict=True)]
                )
            filled += len(rows)
            sleep(pace_seconds(texts))
        remaining = int(conn.execute(_REMAINING).fetchone()[0])
    logger.info("gemini_backfill.done", filled=filled, remaining=remaining)
    return BackfillResult(filled=filled, remaining=remaining, error=error)


def main() -> int:
    """Exit 0 when done or stopped by the quota (rerun later); 1 on any other failure."""
    if not pgvector_store.RULEBOOK_ENABLED:
        print("DATABASE_URL is not set — nothing to backfill.")
        return 1
    if not os.getenv("GOOGLE_API_KEY", "").strip():
        print("GOOGLE_API_KEY is not set — cannot embed with Gemini.")
        return 1
    result = backfill()
    print(f"Gemini backfill: {result.filled} filled, {result.remaining} remaining.")
    if result.error is None:
        return 0
    if result.quota_stop:
        print("Stopped on Gemini's quota (429). Rerun later to continue.")
        return 0
    print(f"Stopped on an error: {result.error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
