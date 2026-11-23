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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

from dataclasses import dataclass, field
import os

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

-- Keyword search needs no model: Postgres keeps the stemmed words itself.
ALTER TABLE rulebook_chunk
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX IF NOT EXISTS rulebook_chunk_tsv_idx ON rulebook_chunk USING gin (content_tsv);
"""


@dataclass(frozen=True)
class RulebookHit:
    """A retrieved chunk. ``page_content``/``metadata`` mirror a LangChain
    Document so the existing cross-encoder reranker consumes it unchanged."""

    page_content: str
    metadata: dict = field(default_factory=dict)
    similarity: float = 0.0


def _connect() -> psycopg.Connection:
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


def ensure_schema_conn(conn: psycopg.Connection) -> None:
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
        for c, vec in zip(chunks, embeddings, strict=False)
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


# The statements are written out rather than assembled from a WHERE fragment,
# so no SQL is built at runtime. The only difference between the two of each
# pair is the optional doc-type predicate.
_SEARCH_ALL_CATEGORIES = """
    SELECT content, doc_type, filename, page,
           1 - (embedding <=> %s::vector) AS similarity
    FROM rulebook_chunk
    WHERE source_year = %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""

_SEARCH_BY_CATEGORY = """
    SELECT content, doc_type, filename, page,
           1 - (embedding <=> %s::vector) AS similarity
    FROM rulebook_chunk
    WHERE source_year = %s AND doc_type = %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""

# Keyword half: the question becomes an OR of its stemmed words (a question
# rarely has every word in one passage, which websearch_to_tsquery would need).
# A question of only stopwords yields a NULL query and so no rows. "article" is
# left out: nearly every page says it, so it would outrank the number beside it.
_KEYWORDS_ALL_CATEGORIES = """
    WITH q AS (
        SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS query
        FROM unnest(tsvector_to_array(to_tsvector('english', %s))) AS lexeme
        WHERE lexeme <> 'articl'
    )
    SELECT content, doc_type, filename, page, ts_rank_cd(content_tsv, q.query, 32) AS rank
    FROM rulebook_chunk, q
    WHERE source_year = %s AND content_tsv @@ q.query
    ORDER BY rank DESC
    LIMIT %s
"""

_KEYWORDS_BY_CATEGORY = """
    WITH q AS (
        SELECT to_tsquery('simple', string_agg(quote_literal(lexeme), ' | ')) AS query
        FROM unnest(tsvector_to_array(to_tsvector('english', %s))) AS lexeme
        WHERE lexeme <> 'articl'
    )
    SELECT content, doc_type, filename, page, ts_rank_cd(content_tsv, q.query, 32) AS rank
    FROM rulebook_chunk, q
    WHERE source_year = %s AND doc_type = %s AND content_tsv @@ q.query
    ORDER BY rank DESC
    LIMIT %s
"""

_YEAR_INDEXED = "SELECT EXISTS (SELECT 1 FROM rulebook_chunk WHERE source_year = %s)"

_RRF_OFFSET = 60


def year_indexed(year: int) -> bool:
    """Whether any regulation text is stored for the season (False when disabled)."""
    if not RULEBOOK_ENABLED:
        return False
    with _connect() as conn:
        ensure_schema_conn(conn)
        return bool(conn.execute(_YEAR_INDEXED, [str(year)]).fetchone()[0])


def search(query: str, year: int, *, category: str | None = None, k: int = 24) -> list[RulebookHit]:
    """Return up to ``k`` chunks for ``query`` in a season, best first.

    ``category`` optionally filters by doc type (Sporting/Technical/Financial).
    Empty list when disabled or on error.
    """
    if not RULEBOOK_ENABLED or not query.strip():
        return []
    try:
        return _find(query, year, category, k)
    except Exception:  # the database failure was already logged
        return []


def search_strict(query: str, year: int, *, category: str | None = None, k: int = 24) -> list[RulebookHit]:
    """:func:`search`, but a failed query raises, so "nothing found" differs from "could not search"."""
    if not RULEBOOK_ENABLED or not query.strip():
        return []
    return _find(query, year, category, k)


def _find(query: str, year: int, category: str | None, k: int) -> list[RulebookHit]:
    """Keyword hits always, merged with nearest-vector hits when a query embedder is loaded.

    Logs, then raises, when the database fails.
    """
    by_category = bool(category) and category.lower() != "all"
    scope = [category] if by_category else []
    keyword_sql = _KEYWORDS_BY_CATEGORY if by_category else _KEYWORDS_ALL_CATEGORIES
    vector = embed(query)
    try:
        with _connect() as conn:
            ensure_schema_conn(conn)
            keyword_rows = conn.execute(keyword_sql, [query, str(year), *scope, k]).fetchall()
            semantic_rows = []
            if vector is not None:
                literal = to_pgvector_literal(vector)
                vector_sql = _SEARCH_BY_CATEGORY if by_category else _SEARCH_ALL_CATEGORIES
                # Statement order: similarity vector, year, [category], ORDER BY vector, limit.
                params = [literal, str(year), *scope, literal, k]
                semantic_rows = conn.execute(vector_sql, params).fetchall()
    except Exception as exc:
        logger.warning("rulebook_pg.search_failed", year=year, error=str(exc))
        raise
    return _fuse([_hit(r, year) for r in keyword_rows], [_hit(r, year) for r in semantic_rows])[:k]


def _hit(row: tuple, year: int) -> RulebookHit:
    return RulebookHit(
        page_content=row[0],
        metadata={
            "type": row[1] or "Regulatory",
            "filename": row[2] or "Unknown PDF",
            "page": row[3],
            "source_year": str(year),
        },
        similarity=round(float(row[4]), 4),
    )


def _fuse(*rankings: list[RulebookHit]) -> list[RulebookHit]:
    """Reciprocal rank fusion: a chunk scores 1/(60+rank) in each list that holds it."""
    scores: dict[str, float] = {}
    first: dict[str, RulebookHit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.page_content] = scores.get(hit.page_content, 0.0) + 1 / (_RRF_OFFSET + rank)
            first.setdefault(hit.page_content, hit)
    return [first[content] for content in sorted(scores, key=lambda c: -scores[c])]
