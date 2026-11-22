"""The Rulebook page's search: regulation passages, the stewards' decisions that applied them, and the text."""

from __future__ import annotations

from datetime import UTC, datetime
import os
import re

import structlog

from app.config import ENABLE_LOCAL_MODELS, RULEBOOK_TOP_K
from app.data.fia_documents.store import FiaStoreError
from app.rag.pgvector_store import RULEBOOK_ENABLED, RulebookHit, search_strict as rulebook_search
from app.rag.rerank import rerank
from app.services import rulebook_answer, rulebook_decisions
from app.services.rulebook_decisions import article_codes

logger = structlog.get_logger()

PAGE_EXCERPTS = 3
_SECTION = re.compile(r"Section ([A-F]) \[([^\]]+)\]")


def resolve_rulebook_year(year: int | None = None) -> int:
    if year is not None:
        return year

    now = datetime.now(UTC)
    current_year = now.year
    if now.month == 12 and now.day > 10 and os.path.exists(f"data/raw/{current_year + 1}"):
        return current_year + 1
    return current_year


def _source(metadata: dict) -> str:
    section = _SECTION.search(metadata.get("filename", ""))
    if section:
        return f"Section {section[1]} · {section[2]}"
    return f"{metadata.get('type') or 'Regulatory'} Regulations"


def _article(cite: int, hit: RulebookHit) -> dict:
    metadata = hit.metadata or {}
    page = metadata.get("page")
    excerpt = " ".join(hit.page_content.split())
    return {
        "cite": cite,
        "codes": list(article_codes(excerpt)),
        "source": _source(metadata),
        "document": metadata.get("filename", "Unknown regulation PDF"),
        "page": int(page) + 1 if isinstance(page, (int, float)) else None,
        "excerpt": excerpt,
    }


def _payload(query: str, year: int, status: str, reason: str | None, **parts: object) -> dict:
    return {
        "query": query,
        "year": year,
        "status": status,
        "reason": reason,
        "articles": [],
        "decisions": None,
        "summary": None,
        **parts,
    }


def _regulation_hits(query: str, category: str | None, year: int) -> tuple[list, str | None]:
    """The reranked passages, or the reason the regulations were not searched."""
    if not RULEBOOK_ENABLED:
        return [], "The regulation index isn't set up on this server, so the regulations were not searched."
    if not ENABLE_LOCAL_MODELS:
        return [], (
            "Regulation search is off on this server: it needs a model this server doesn't have the memory "
            "to run. The regulations were not searched."
        )
    try:
        candidates = rulebook_search(query, year, category=category, k=RULEBOOK_TOP_K * 4)
        hits = rerank(query, candidates, PAGE_EXCERPTS) if candidates else []
    except Exception as exc:
        logger.warning("rulebook.search.failed", year=year, category=category, error=str(exc))
        return [], "The regulation search failed, so the regulations were not searched. Try again shortly."
    if not hits:
        return [], f"The FIA {year} F1 Regulations aren't in the search index yet."
    return hits, None


def search_rulebook(query: str, category: str | None = None, year: int | None = None) -> dict:
    clean_query = query.strip()
    resolved_year = resolve_rulebook_year(year)
    if not clean_query:
        return _payload(clean_query, resolved_year, "unavailable", "Enter a question to search the regulations.")

    hits, reason = _regulation_hits(clean_query, category, resolved_year)
    if hits:
        articles = [_article(cite, hit) for cite, hit in enumerate(hits, start=1)]
        codes = [tuple(article["codes"]) for article in articles]
        decisions = rulebook_decisions.matching(resolved_year, codes, first_cite=len(articles) + 1)
        summary = rulebook_answer.write_summary(clean_query, resolved_year, articles, decisions)
        return _payload(
            clean_query, resolved_year, "answered", None, articles=articles, decisions=decisions, summary=summary
        )

    try:
        decisions = rulebook_decisions.keyword_matching(resolved_year, clean_query)
    except FiaStoreError as exc:
        logger.warning("rulebook.decisions.unavailable", year=resolved_year, error=str(exc))
        return _payload(
            clean_query, resolved_year, "unavailable", f"{reason} The stewards' decisions could not be read either."
        )
    summary = rulebook_answer.write_summary(clean_query, resolved_year, [], decisions)
    return _payload(clean_query, resolved_year, "keyword", reason, decisions=decisions, summary=summary)
