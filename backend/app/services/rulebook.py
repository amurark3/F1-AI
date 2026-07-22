"""Structured FIA rulebook search for Race Control surfaces (pgvector-backed)."""

from __future__ import annotations

import os
from datetime import datetime

import structlog

from app.config import RULEBOOK_TOP_K
from app.rag.pgvector_store import RULEBOOK_ENABLED
from app.rag.pgvector_store import search as rulebook_search
from app.rag.rerank import rerank

logger = structlog.get_logger()


def resolve_rulebook_year(year: int | None = None) -> int:
    if year is not None:
        return year

    now = datetime.now()
    current_year = now.year
    if now.month == 12 and now.day > 10 and os.path.exists(f"data/raw/{current_year + 1}"):
        return current_year + 1
    return current_year


def fallback_rulebook_search(
    query: str, category: str | None = None, year: int | None = None, error: str | None = None
) -> dict:
    resolved_year = resolve_rulebook_year(year)
    document = category if category and category != "All" else "FIA regulations corpus"

    return {
        "answer": "Rulebook search is unavailable because the cited regulation index could not be loaded. No uncited regulation answer was generated.",
        "source": "fallback",
        "error": error,
        "citations": [{
            "document": document,
            "year": str(resolved_year),
            "category": category or "All",
            "page": None,
            "snippet": "Citation preview unavailable because the vector search could not answer this request.",
        }],
    }


def _page_label(page) -> str | None:
    # pgvector stores a 0-indexed page; present it 1-indexed for humans.
    if isinstance(page, (int, float)):
        return str(int(page) + 1)
    return None


def search_rulebook(query: str, category: str | None = None, year: int | None = None) -> dict:
    clean_query = query.strip()
    resolved_year = resolve_rulebook_year(year)

    if not clean_query:
        return fallback_rulebook_search(
            query, category, resolved_year, "Enter a regulation question before searching."
        )

    if not RULEBOOK_ENABLED:
        return fallback_rulebook_search(
            clean_query, category, resolved_year,
            "Rulebook vector store not configured (DATABASE_URL unset). Run `python -m app.rag.ingest`.",
        )

    try:
        # Over-fetch by similarity from pgvector, then cross-encoder rerank.
        candidates = rulebook_search(
            clean_query, resolved_year, category=category, k=RULEBOOK_TOP_K * 4
        )
        hits = rerank(clean_query, candidates, RULEBOOK_TOP_K)
    except Exception as exc:
        logger.warning("rulebook.search.failed", year=resolved_year, category=category, error=str(exc))
        return fallback_rulebook_search(clean_query, category, resolved_year, str(exc))

    if not hits:
        return {
            "answer": f"No cited regulation excerpts matched '{clean_query}' in the {resolved_year} {category or 'All'} corpus.",
            "source": "pgvector-rag",
            "error": None,
            "citations": [],
        }

    citations = []
    for hit in hits:
        metadata = hit.metadata or {}
        citations.append({
            "document": metadata.get("filename", "Unknown regulation PDF"),
            "year": str(metadata.get("source_year", resolved_year)),
            "category": metadata.get("type", category or "All"),
            "page": _page_label(metadata.get("page")),
            "snippet": hit.page_content.replace("\n", " ").strip()[:700],
        })

    return {
        "answer": (
            f"Found {len(citations)} cited regulation excerpt{'s' if len(citations) != 1 else ''} "
            f"for this ops question. Review the snippets before making a final sporting, technical, or financial call."
        ),
        "source": "pgvector-rag",
        "error": None,
        "citations": citations,
    }
