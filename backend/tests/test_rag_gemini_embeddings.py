"""Tests for app.rag.gemini_embeddings — Gemini vectors for rulebook search.

The risk is a spent free-tier quota stalling or breaking a search. A failed
query must return None (the search carries on with keywords) and rest Gemini so
the next searches don't hit the spent quota again. The Google client is faked at
``genai.Client``; the real request config types are kept so a wrong field fails.
"""

from __future__ import annotations

from types import SimpleNamespace

from google import genai
import pytest

from app.config import GEMINI_EMBEDDING_DIM, GEMINI_EMBEDDING_MODEL, LLM_ACCOUNT_COOLDOWN_SECONDS
from app.rag import gemini_embeddings


class _QuotaError(Exception):
    code = 429


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(gemini_embeddings, "_resting_until", 0.0)


def _install_client(monkeypatch, vectors: list[list[float]] | None) -> list[dict]:
    """Fake ``genai.Client``; returns the recorded constructor and request kwargs."""
    calls: list[dict] = []

    class _Models:
        def embed_content(self, **kwargs) -> SimpleNamespace:
            calls.append(kwargs)
            embeddings = None if vectors is None else [SimpleNamespace(values=v) for v in vectors]
            return SimpleNamespace(embeddings=embeddings)

    class _Client:
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)
            self.models = _Models()

    monkeypatch.setattr(genai, "Client", _Client)
    return calls


@pytest.mark.unit
def test_unavailable_without_a_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "  ")
    monkeypatch.setattr(gemini_embeddings, "_embed", pytest.fail)

    assert gemini_embeddings.available() is False
    assert gemini_embeddings.embed_query("pit lane") is None


@pytest.mark.unit
def test_embed_query_sends_a_retrieval_query_with_one_attempt_and_a_timeout(monkeypatch, with_key):
    calls = _install_client(monkeypatch, [[0.5] * GEMINI_EMBEDDING_DIM])

    assert gemini_embeddings.embed_query("can I overtake behind the safety car") == [0.5] * GEMINI_EMBEDDING_DIM

    client_kwargs, request = calls
    assert client_kwargs["api_key"] == "test-key"
    assert client_kwargs["http_options"].retry_options.attempts == 1
    assert client_kwargs["http_options"].timeout == 5000
    assert request["model"] == GEMINI_EMBEDDING_MODEL
    assert request["contents"] == ["can I overtake behind the safety car"]
    assert request["config"].task_type == "RETRIEVAL_QUERY"
    assert request["config"].output_dimensionality == GEMINI_EMBEDDING_DIM


@pytest.mark.unit
def test_embed_documents_sends_retrieval_document_and_keeps_input_order(monkeypatch, with_key):
    first, second = [0.1] * GEMINI_EMBEDDING_DIM, [0.2] * GEMINI_EMBEDDING_DIM
    calls = _install_client(monkeypatch, [first, second])

    assert gemini_embeddings.embed_documents(["a", "b"]) == [first, second]
    assert calls[1]["config"].task_type == "RETRIEVAL_DOCUMENT"


@pytest.mark.unit
@pytest.mark.parametrize(
    "vectors",
    [None, [[0.1] * GEMINI_EMBEDDING_DIM], [[0.1] * 3, [0.1] * 3]],
    ids=["no embeddings", "one vector for two texts", "wrong width"],
)
def test_a_malformed_response_raises_rather_than_storing_bad_vectors(monkeypatch, with_key, vectors):
    _install_client(monkeypatch, vectors)

    with pytest.raises(ValueError, match="for 2 texts"):
        gemini_embeddings.embed_documents(["a", "b"])


@pytest.mark.unit
def test_a_failed_query_returns_none_and_rests_gemini(monkeypatch, with_key):
    clock = [1000.0]
    monkeypatch.setattr(gemini_embeddings.time, "monotonic", lambda: clock[0])

    def spent_quota(_texts, _task):
        raise _QuotaError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(gemini_embeddings, "_embed", spent_quota)

    assert gemini_embeddings.embed_query("pit lane") is None
    assert gemini_embeddings._resting_until == 1000.0 + LLM_ACCOUNT_COOLDOWN_SECONDS

    # While resting, no request is sent at all.
    monkeypatch.setattr(gemini_embeddings, "_embed", pytest.fail)
    assert gemini_embeddings.embed_query("pit lane") is None

    clock[0] += LLM_ACCOUNT_COOLDOWN_SECONDS
    assert gemini_embeddings.available() is True
