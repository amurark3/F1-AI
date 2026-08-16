"""FIA rulebook vectors in Postgres (pgvector) — replaces the local ChromaDB.

The regulation chunks + embeddings live in Supabase, so:
  * deploys never rebuild a vector DB (no ~9-min ingest step, no 72MB artifact),
  * the corpus is durable across Render's ephemeral filesystem, and
  * both the chat tool and the Rules Search UI query one shared store.

Populated once by ``python -m app.rag.ingest`` (which reads the PDFs and calls
:func:`replace_all`). Everything degrades gracefully when ``DATABASE_URL`` is
unset or the DB is unreachable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

from app.utils.embeddings import EMBEDDING_DIM, embed, embed_batch, to_pgvector_literal

logger = structlog.get_logger()

RULEBOOK_ENABLED = bool(os.getenv("DATABASE_URL", "").strip())

_SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rulebook_chunk (
    id          BIGSERIAL PRIMARY KEY,
    source_year TEXT NOT NULL,
    doc_type    TEXT,
    filename    TEXT,
    page        INTEGER,
    content     TEXT NOT NULL,
    embedding   vector({EMBEDDING_DIM})
);

CREATE INDEX IF NOT EXISTS rulebook_chunk_year_idx ON rulebook_chunk (source_year);
CREATE INDEX IF NOT EXISTS rulebook_chunk_hnsw_idx
    ON rulebook_chunk USING hnsw (embedding vector_cosine_ops);

-- Supabase exposes every public table over PostgREST; without RLS the anon key
-- could truncate the corpus that ``python -m app.rag.ingest`` takes ~9 minutes
-- to rebuild.  Reads/writes here run as the owning role over plain Postgres,
-- which bypasses RLS, so no policy is needed.  Idempotent.
ALTER TABLE rulebook_chunk ENABLE ROW LEVEL SECURITY;
"""


@dataclass(frozen=True)
class RulebookHit:
    """A retrieved chunk. ``page_content``/``metadata`` mirror a LangChain
    Document so the existing cross-encoder reranker consumes it unchanged."""

    page_content: str
    metadata: dict = field(default_factory=dict)
    similarity: float = 0.0


def _connect():
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def ensure_schema() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA_SQL)


def count() -> int:
    """Number of stored rulebook chunks (0 when disabled/empty/unreachable)."""
    if not RULEBOOK_ENABLED:
        return 0
    try:
        with _connect() as conn:
            ensure_schema_conn(conn)
            row = conn.execute("SELECT COUNT(*) FROM rulebook_chunk").fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("rulebook_pg.count_failed", error=str(exc))
        return 0


def ensure_schema_conn(conn) -> None:
    conn.execute(_SCHEMA_SQL)


def replace_all(chunks: list[dict]) -> int:
    """Wipe and repopulate the rulebook table from ``chunks``.

    Each chunk: ``{source_year, doc_type, filename, page, content}``. Embeds the
    content in batch, truncates the table, and bulk-inserts. Returns the number
    of rows written.
    """
    if not RULEBOOK_ENABLED:
        raise RuntimeError("DATABASE_URL is not set — cannot populate the pgvector rulebook.")
    if not chunks:
        return 0

    embeddings = embed_batch([c["content"] for c in chunks])
    if embeddings is None:
        raise RuntimeError("Embedding model unavailable — cannot build rulebook vectors.")

    rows = [
        (
            str(c.get("source_year", "")),
            c.get("doc_type"),
            c.get("filename"),
            int(c["page"]) if c.get("page") is not None else None,
            c["content"],
            to_pgvector_literal(vec),
        )
        for c, vec in zip(chunks, embeddings)
    ]

    with _connect() as conn:
        ensure_schema_conn(conn)
        conn.execute("TRUNCATE rulebook_chunk RESTART IDENTITY")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rulebook_chunk (source_year, doc_type, filename, page, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector)",
                rows,
            )
    logger.info("rulebook_pg.populated", rows=len(rows))
    return len(rows)


def search(query: str, year: int, *, category: str | None = None, k: int = 24) -> list[RulebookHit]:
    """Return the ``k`` chunks most similar to ``query`` for a season.

    ``category`` optionally filters by doc type (Sporting/Technical/Financial).
    Empty list when disabled, the query can't be embedded, or on error.
    """
    if not RULEBOOK_ENABLED or not query.strip():
        return []
    vector = embed(query)
    if vector is None:
        return []
    literal = to_pgvector_literal(vector)

    where = "source_year = %s"
    params: list = [literal, str(year)]
    if category and category.lower() != "all":
        where += " AND doc_type = %s"
        params.append(category)
    params.append(literal)  # ORDER BY vector
    params.append(k)

    try:
        with _connect() as conn:
            ensure_schema_conn(conn)
            rows = conn.execute(
                f"""
                SELECT content, doc_type, filename, page,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM rulebook_chunk
                WHERE {where}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            ).fetchall()
    except Exception as exc:
        logger.warning("rulebook_pg.search_failed", year=year, error=str(exc))
        return []

    return [
        RulebookHit(
            page_content=r[0],
            metadata={
                "type": r[1] or "Regulatory",
                "filename": r[2] or "Unknown PDF",
                "page": r[3],
                "source_year": str(year),
            },
            similarity=round(float(r[4]), 4),
        )
        for r in rows
    ]
