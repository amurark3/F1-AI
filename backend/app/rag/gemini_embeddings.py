"""Gemini embeddings for the rulebook: meaning search with no model in memory.

The web process embeds one question per search (``RETRIEVAL_QUERY``); the
backfill embeds stored passages (``RETRIEVAL_DOCUMENT``). Both use the chat
fallback's free-tier key, so a question must never wait on a spent quota: a
query that fails rests Gemini for ``LLM_ACCOUNT_COOLDOWN_SECONDS`` and the
search carries on with keywords alone.
"""

from __future__ import annotations

import os
import time

import structlog

from app.config import (
    GEMINI_EMBEDDING_DIM,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_TIMEOUT_SECONDS,
    LLM_ACCOUNT_COOLDOWN_SECONDS,
)

logger = structlog.get_logger()

_resting_until = 0.0


def available() -> bool:
    """A key is set and Gemini is not resting after a failed query."""
    return bool(os.getenv("GOOGLE_API_KEY", "").strip()) and time.monotonic() >= _resting_until


def embed_query(text: str) -> list[float] | None:
    """The question's vector, or None when Gemini is unavailable or the call fails."""
    global _resting_until
    if not available():
        return None
    try:
        return _embed([text], "RETRIEVAL_QUERY")[0]
    except Exception as exc:
        _resting_until = time.monotonic() + LLM_ACCOUNT_COOLDOWN_SECONDS
        logger.warning("gemini_embeddings.query_failed", status=getattr(exc, "code", None), error=str(exc))
        return None


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Passage vectors in input order. Raises on any failure, so the backfill can stop and report."""
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    from google import genai
    from google.genai import types

    timeout_ms = int(GEMINI_EMBEDDING_TIMEOUT_SECONDS * 1000)
    client = genai.Client(
        api_key=os.environ["GOOGLE_API_KEY"],
        # No retries: a retry against a spent quota only spends the wait.
        http_options=types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)),
    )
    response = client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=GEMINI_EMBEDDING_DIM),
    )
    vectors = [list(e.values or []) for e in response.embeddings or []]
    if len(vectors) != len(texts) or any(len(v) != GEMINI_EMBEDDING_DIM for v in vectors):
        raise ValueError(f"Gemini returned {len(vectors)} vectors for {len(texts)} texts")
    return vectors
