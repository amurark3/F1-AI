"""Cross-encoder reranking for rulebook retrieval.

Vector similarity is recall-oriented: it returns plausible chunks but often
mis-orders them.  A cross-encoder scores each (query, chunk) pair jointly and
gives a far better ordering, so we over-fetch by similarity then rerank and keep
the best.

The model is loaded lazily and is entirely optional — if sentence-transformers
or the model is unavailable, :func:`rerank` returns the input order unchanged,
so retrieval never hard-fails.
"""

from __future__ import annotations

import os
import threading

import structlog

from app.config import ENABLE_LOCAL_MODELS

logger = structlog.get_logger()

RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

_reranker = None
_reranker_lock = threading.Lock()
_reranker_failed = False


def _get_reranker():
    global _reranker, _reranker_failed
    if not ENABLE_LOCAL_MODELS:
        # Second torch model in the query path. Same reasoning as the embedder:
        # the load is what exhausts memory, and an OOM kill is not catchable.
        return None
    if _reranker is not None:
        return _reranker
    if _reranker_failed:
        return None
    with _reranker_lock:
        if _reranker is not None:
            return _reranker
        if _reranker_failed:
            return None
        try:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(RERANK_MODEL_NAME)
            logger.info("rerank.model_loaded", model=RERANK_MODEL_NAME)
            return _reranker
        except Exception as exc:
            logger.warning("rerank.model_unavailable", error=str(exc))
            _reranker_failed = True
            return None


def rerank(query: str, docs: list, top_k: int) -> list:
    """Return the ``top_k`` docs most relevant to ``query``, best first.

    ``docs`` is a list of objects with a ``page_content`` attribute (LangChain
    Documents).  Falls back to the original order (truncated to ``top_k``) when
    the reranker can't be loaded.
    """
    if not docs:
        return []
    reranker = _get_reranker()
    if reranker is None:
        return docs[:top_k]
    try:
        pairs = [(query, getattr(d, "page_content", "")) for d in docs]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda ds: ds[1], reverse=True)
        return [doc for doc, _ in ranked[:top_k]]
    except Exception as exc:
        logger.warning("rerank.failed", error=str(exc))
        return docs[:top_k]
