"""Structured FIA rulebook search for Race Control surfaces."""

from __future__ import annotations

import math
import os
import threading
from datetime import datetime
from typing import Any

import structlog

from app.config import CHROMA_DB_PATH, EMBEDDING_MODEL_NAME, RULEBOOK_TOP_K

logger = structlog.get_logger()

_vector_db = None
_vector_lock = threading.Lock()


def resolve_rulebook_year(year: int | None = None) -> int:
    if year is not None:
        return year

    now = datetime.now()
    current_year = now.year
    if now.month == 12 and now.day > 10 and os.path.exists(f"data/raw/{current_year + 1}"):
        return current_year + 1
    return current_year


def _get_vector_db():
    global _vector_db
    if _vector_db is not None:
        return _vector_db

    with _vector_lock:
        if _vector_db is not None:
            return _vector_db

        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        logger.info("rulebook.vector.initializing", db_path=CHROMA_DB_PATH, model=EMBEDDING_MODEL_NAME)
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        _vector_db = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=embeddings)
        logger.info("rulebook.vector.ready")
        return _vector_db


def _metadata_value(metadata: dict[str, Any], key: str, default: str = "") -> str:
    value = metadata.get(key, default)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return str(value)


def _build_filter(year: int, category: str | None) -> dict:
    filters: list[dict] = [{"source_year": str(year)}]
    if category and category.lower() != "all":
        filters.append({"type": category})

    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def fallback_rulebook_search(query: str, category: str | None = None, year: int | None = None, error: str | None = None) -> dict:
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
            "snippet": "Citation preview unavailable because the local vector search could not answer this request.",
        }],
    }


def search_rulebook(query: str, category: str | None = None, year: int | None = None) -> dict:
    clean_query = query.strip()
    resolved_year = resolve_rulebook_year(year)

    if not clean_query:
        return fallback_rulebook_search(
            query,
            category,
            resolved_year,
            "Enter a regulation question before searching.",
        )

    if not os.path.exists(CHROMA_DB_PATH):
        return fallback_rulebook_search(
            clean_query,
            category,
            resolved_year,
            "Rulebook vector database not found. Run `python app/rag/ingest.py` from the backend directory.",
        )

    try:
        vector_db = _get_vector_db()
        docs = vector_db.as_retriever(search_kwargs={
            "k": RULEBOOK_TOP_K,
            "filter": _build_filter(resolved_year, category),
        }).invoke(clean_query)
    except Exception as exc:
        logger.warning("rulebook.search.failed", year=resolved_year, category=category, error=str(exc))
        return fallback_rulebook_search(clean_query, category, resolved_year, str(exc))

    if not docs:
        return {
            "answer": f"No cited regulation excerpts matched '{clean_query}' in the {resolved_year} {category or 'All'} corpus.",
            "source": "chroma-rag",
            "error": None,
            "citations": [],
        }

    citations = []
    for doc in docs:
        metadata = doc.metadata or {}
        page = _metadata_value(metadata, "page_label") or _metadata_value(metadata, "page")
        citations.append({
            "document": _metadata_value(metadata, "filename", _metadata_value(metadata, "source", "Unknown regulation PDF")),
            "year": _metadata_value(metadata, "source_year", str(resolved_year)),
            "category": _metadata_value(metadata, "type", category or "All"),
            "page": page or None,
            "snippet": doc.page_content.replace("\n", " ").strip()[:700],
        })

    return {
        "answer": (
            f"Found {len(citations)} cited regulation excerpt{'s' if len(citations) != 1 else ''} "
            f"for this ops question. Review the snippets before making a final sporting, technical, or financial call."
        ),
        "source": "chroma-rag",
        "error": None,
        "citations": citations,
    }
