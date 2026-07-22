"""Shared sentence-transformers embedder (all-MiniLM-L6-v2, 384-dim).

One model instance in memory, reused by conversation memory and the rulebook
RAG so the weights aren't loaded twice. Lazy (imported/loaded on first use, not
at app startup — sentence-transformers pulls in torch) and optional (returns
None if the model can't be loaded, so callers degrade gracefully).
"""

from __future__ import annotations

import threading

import structlog

from app.config import EMBEDDING_MODEL_NAME

logger = structlog.get_logger()

# Output dimensionality of all-MiniLM-L6-v2.
EMBEDDING_DIM = 384

_model = None
_lock = threading.Lock()
_failed = False


def get_embedder():
    """Return the shared SentenceTransformer, or None if unavailable."""
    global _model, _failed
    if _model is not None:
        return _model
    if _failed:
        return None
    with _lock:
        if _model is not None:
            return _model
        if _failed:
            return None
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("embeddings.model_loaded", model=EMBEDDING_MODEL_NAME)
            return _model
        except Exception as exc:
            logger.error("embeddings.load_failed", error=str(exc))
            _failed = True
            return None


def embed(text: str) -> list[float] | None:
    """Embed a single string (normalized for cosine similarity)."""
    model = get_embedder()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]
    except Exception as exc:
        logger.warning("embeddings.embed_failed", error=str(exc))
        return None


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed many strings at once (normalized). None if the model is unavailable."""
    model = get_embedder()
    if model is None:
        return None
    try:
        vectors = model.encode(
            texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False
        )
        return [[float(x) for x in v] for v in vectors]
    except Exception as exc:
        logger.warning("embeddings.embed_batch_failed", error=str(exc))
        return None


def to_pgvector_literal(vector: list[float]) -> str:
    """Render a vector as pgvector text form: '[0.1,0.2,...]' (cast ::vector in SQL)."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
