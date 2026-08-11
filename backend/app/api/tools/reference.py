"""Reference lookups: the FIA rulebook and read-only SQL over f1db."""

from __future__ import annotations

from datetime import datetime, timezone
import os

from langchain_core.tools import tool
import structlog

from app.config import RULEBOOK_TOP_K
from app.data.f1db_query import F1DB_SCHEMA_DOC, QueryValidationError, run_readonly_query
from app.rag.rerank import rerank

logger = structlog.get_logger()


@tool
def consult_rulebook(query: str, year: int | None = None) -> str:
    """
    Searches the official FIA regulations (Sporting, Technical, Financial)
    for text relevant to `query`.

    The regulations are stored as vector embeddings in Postgres (pgvector),
    populated by running `python -m app.rag.ingest`.

    Args:
        query: A natural-language question, e.g. "What is the penalty for
               exceeding the pit-lane speed limit?"
        year:  The season year to restrict results to (e.g. 2025).
               Defaults intelligently to the current season; switches to the
               next year's regulations in late December when available.
    """
    # --- Year resolution logic ---
    if year is None:
        now = datetime.now(timezone.utc)
        current_year = now.year
        # After mid-December the season is over; prefer next-year regs if present.
        season_ended = now.month == 12 and now.day > 10

        if season_ended and os.path.exists(f"data/raw/{current_year + 1}"):
            year = current_year + 1
            logger.info("rulebook.year_resolved", year=year, reason="season_over")
        else:
            year = current_year
            logger.info("rulebook.year_resolved", year=year, reason="current_season")

    logger.info("tool.consult_rulebook", year=year, query=query)

    try:
        from app.rag.pgvector_store import RULEBOOK_ENABLED, search as rulebook_search

        if not RULEBOOK_ENABLED:
            return "Rulebook search is unavailable — DATABASE_URL is not configured."

        # Over-fetch by vector similarity from pgvector, then cross-encoder rerank
        # down to RULEBOOK_TOP_K. Similarity is recall-oriented; the reranker fixes
        # the ordering so the most on-point articles surface first.
        candidates = rulebook_search(query, year, k=RULEBOOK_TOP_K * 4)
        if not candidates:
            return f"No regulations found for '{query}' in the {year} rulebook."

        docs = rerank(query, candidates, RULEBOOK_TOP_K)

        results = []
        for doc in docs:
            meta = doc.metadata
            doc_type = meta.get("type", "Regulatory")
            filename = meta.get("filename", "Unknown PDF")
            # PyPDFLoader stores a 0-indexed page; display it 1-indexed.
            page = meta.get("page")
            page_str = f", p.{int(page) + 1}" if isinstance(page, (int, float)) else ""
            citation = f"{doc_type} Regulations {year} ({filename}{page_str})"
            content = doc.page_content.replace("\n", " ").strip()
            results.append(f"**Source:** {citation}\n**Excerpt:** ...{content[:700]}...")

        header = (
            f"Found {len(results)} relevant passage(s) in the {year} FIA regulations. "
            f"Cite the Source line(s) in your answer.\n"
        )
        return header + "\n\n".join(results)

    except Exception as e:
        return f"Rulebook lookup failed: {e}"


@tool
def query_f1_database(sql: str) -> str:
    """
    Runs a READ-ONLY SQL query against the local f1db database — the full
    history of Formula 1 from 1950 to the present.

    Use this for ANY factual/statistical F1 question that the other, more
    specific tools do not directly answer — historical records, head-to-head
    career comparisons, "most/fewest/best/worst" superlatives, results at a
    given circuit across many seasons, wet-weather records, nationality
    breakdowns, streaks, and so on.

    Write a single SQLite SELECT (or WITH ... SELECT) statement. Only read
    queries are permitted. Results are capped; add ORDER BY and your own LIMIT
    for "top N" questions. After you get rows back, explain them in plain
    language — do not just dump the table. The database schema is provided
    below.
    """
    logger.info("tool.query_f1_database", sql=sql)
    try:
        result = run_readonly_query(sql)
    except QueryValidationError as exc:
        return f"Query rejected: {exc}"
    except Exception as exc:
        logger.warning("tool.query_f1_database.error", error=str(exc))
        return f"Query failed: {exc}. Check table/column names against the schema and try again."

    rows = result["rows"]
    columns = result["columns"]
    if not rows:
        return f"Query ran successfully but returned no rows.\n\nSQL:\n{result['sql']}"

    lines = [f"Returned {result['row_count']} row(s).", ""]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    lines.extend("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |" for row in rows)
    return "\n".join(lines)


# The f1db schema is appended to the tool description (not the docstring) so the
# model sees the full table/column reference when deciding how to write SQL.
query_f1_database.description = query_f1_database.description.rstrip() + "\n\nSCHEMA:\n" + F1DB_SCHEMA_DOC
