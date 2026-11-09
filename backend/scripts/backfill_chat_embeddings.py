"""Embed the chat turns that were saved without a vector, so recall can find them.

    cd backend
    DATABASE_URL=<target> ENABLE_LOCAL_MODELS=true python -m scripts.backfill_chat_embeddings          # dry run
    DATABASE_URL=<target> ENABLE_LOCAL_MODELS=true python -m scripts.backfill_chat_embeddings --apply  # writes

While the API ran without local models (Render's 512 MB), ``save_message``
stored every chat turn with a NULL embedding, and recall only searches rows
that have one. This fills those rows with the shared embedder in
``app.utils.embeddings``, the model and width the API itself uses, so the
history becomes recallable once the API runs with ``ENABLE_LOCAL_MODELS=true``.

What it touches:

* Only user and assistant turns, as ``save_message`` embeds; system turns stay
  NULL.
* Only rows whose embedding is still NULL, on read and again on write, so a
  second run changes nothing and a turn the live API embeds mid-run keeps the
  API's vector.
* One batch per transaction: an interrupted run keeps what it committed, and
  the next run carries on from there.

``DATABASE_URL`` comes from the environment only. Unlike the other scripts
this one never reads ``backend/.env``, which points at production, so a write
always goes where it was deliberately aimed.

Exit status: 0 done or nothing to do; 1 the embedder returned nothing (the
batches before it are kept); 2 the database could not be read or written; 3 no
``DATABASE_URL``; 4 local models are disabled.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

from app.config import ENABLE_LOCAL_MODELS
from app.utils.embeddings import embed_batch, to_pgvector_literal

if TYPE_CHECKING:
    from collections.abc import Iterator

    import psycopg

EXIT_OK = 0
EXIT_EMBED_FAILED = 1
EXIT_DATABASE_ERROR = 2
EXIT_NO_DATABASE = 3
EXIT_NO_MODELS = 4

DEFAULT_BATCH_SIZE = 64

NO_DATABASE = (
    "DATABASE_URL is not set. Export the URL of the database to backfill; "
    "this script never reads backend/.env, which points at production."
)
NO_MODELS = (
    "local models are disabled, so there is no model to embed with. "
    "Run it where the API's model fits, with ENABLE_LOCAL_MODELS=true."
)

# Every statement is written out whole, so no SQL is built at runtime. The
# role filter mirrors ``save_message``, which embeds user and assistant turns only.
_COUNT_PENDING = """
    SELECT COUNT(*) FROM chat_message
    WHERE embedding IS NULL AND role IN ('user', 'assistant')
"""

# Keyset paging on id: a row the UPDATE skipped can never come back in the same
# run, so every run terminates.
_NEXT_BATCH = """
    SELECT id, content FROM chat_message
    WHERE embedding IS NULL AND role IN ('user', 'assistant') AND id > %s
    ORDER BY id
    LIMIT %s
"""

# ``embedding IS NULL`` again on write: a turn the live API embedded after the
# batch was read keeps the API's vector.
_FILL = "UPDATE chat_message SET embedding = %s::vector WHERE id = %s AND embedding IS NULL"


@dataclass(frozen=True)
class Batch:
    """One committed batch: rows read, rows actually filled, and where it ended."""

    read: int
    written: int
    last_id: int


class EmbedderUnavailableError(RuntimeError):
    """The shared embedder returned nothing for a batch."""


def _batch_size(value: str) -> int:
    try:
        size = int(value)
    except ValueError:
        size = 0
    if size < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return size


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed chat turns stored without a vector.")
    parser.add_argument("--apply", action="store_true", help="write the vectors (default: count only)")
    parser.add_argument("--batch-size", type=_batch_size, default=DEFAULT_BATCH_SIZE, help="turns per transaction")
    return parser.parse_args(argv)


def _refusal() -> tuple[int, str] | None:
    """The exit status and reason this run cannot go ahead, or ``None``."""
    if not os.getenv("DATABASE_URL", "").strip():
        return EXIT_NO_DATABASE, NO_DATABASE
    if not ENABLE_LOCAL_MODELS:
        return EXIT_NO_MODELS, NO_MODELS
    return None


def _connect() -> psycopg.Connection:
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"])


def _count_pending(conn: psycopg.Connection) -> int:
    row = conn.execute(_COUNT_PENDING).fetchone()
    return int(row[0]) if row else 0


def _fill_batches(conn: psycopg.Connection, batch_size: int) -> Iterator[Batch]:
    """Embed and write the pending turns in id order, committing each batch."""
    last_id = 0
    while rows := conn.execute(_NEXT_BATCH, (last_id, batch_size)).fetchall():
        vectors = embed_batch([content for _, content in rows])
        if vectors is None:
            raise EmbedderUnavailableError
        params = [(to_pgvector_literal(vector), row_id) for (row_id, _), vector in zip(rows, vectors, strict=True)]
        with conn.cursor() as cur:
            cur.executemany(_FILL, params)
            written = cur.rowcount
        conn.commit()
        last_id = rows[-1][0]
        yield Batch(read=len(rows), written=written, last_id=last_id)


def _apply(conn: psycopg.Connection, batch_size: int) -> int:
    embedded = 0
    skipped = 0
    try:
        for number, batch in enumerate(_fill_batches(conn, batch_size), start=1):
            embedded += batch.written
            skipped += batch.read - batch.written
            print(f"  batch {number}: embedded {batch.written} of {batch.read} (through id {batch.last_id})")
    except EmbedderUnavailableError:
        print(
            f"Backfill stopped: the embedding model returned nothing. {embedded} turn(s) embedded "
            "before it stopped are kept; re-run to continue."
        )
        return EXIT_EMBED_FAILED
    print(f"Done: embedded {embedded} turn(s); {skipped} already had a vector.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    refusal = _refusal()
    if refusal:
        status, reason = refusal
        print(f"Backfill refused: {reason}")
        return status
    try:
        with _connect() as conn:
            pending = _count_pending(conn)
            print(f"Chat turns without an embedding: {pending}")
            if pending == 0:
                print("Nothing to backfill.")
                return EXIT_OK
            if not args.apply:
                print("Dry run: nothing written. Re-run with --apply to embed them.")
                return EXIT_OK
            return _apply(conn, args.batch_size)
    except Exception as exc:
        print(f"Backfill failed: {exc}. Batches committed before the failure are kept; re-run to continue.")
        return EXIT_DATABASE_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
