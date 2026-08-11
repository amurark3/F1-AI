"""Tests for app.rag.rerank — the optional cross-encoder over rulebook hits.

This is the second torch model in the query path, and the risk it carries is
that it becomes load-bearing. Retrieval must keep working when the model is
disabled (the deployed default), when the load fails, and when ``predict``
raises mid-request — in every case by falling back to the vector order rather
than propagating an error. The other half of the contract is that when the
model *is* available its scores actually reorder the documents.

The lazy ``sentence_transformers`` import is satisfied with a fake module so
torch is never imported.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.rag import rerank as rerank_module


@pytest.fixture(autouse=True)
def _reset_reranker_state():
    """Clear the process-global reranker so each test starts cold."""
    rerank_module._reranker = None
    rerank_module._reranker_failed = False
    yield
    rerank_module._reranker = None
    rerank_module._reranker_failed = False


class _Doc:
    """Stand-in for a LangChain Document / RulebookHit."""

    def __init__(self, text: str) -> None:
        self.page_content = text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"_Doc({self.page_content!r})"


class _FakeCrossEncoder:
    """Scores each pair by a caller-supplied table keyed on chunk text."""

    def __init__(self, name: str = "fake", scores: dict[str, float] | None = None) -> None:
        self.name = name
        self._scores = scores or {}
        self.pairs: list[tuple[str, str]] = []

    def predict(self, pairs):
        self.pairs = list(pairs)
        return [self._scores.get(chunk, 0.0) for _query, chunk in pairs]


def _install_fake_sentence_transformers(monkeypatch, factory):
    """Register a fake ``sentence_transformers`` for the lazy import."""
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=factory))


@pytest.mark.unit
def test_get_reranker_returns_none_when_local_models_disabled(monkeypatch):
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", False)
    _install_fake_sentence_transformers(monkeypatch, lambda *_: pytest.fail("torch must not be imported when disabled"))

    assert rerank_module._get_reranker() is None


@pytest.mark.unit
def test_get_reranker_loads_and_memoises_the_model(monkeypatch):
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", True)
    built: list[str] = []

    def factory(name):
        built.append(name)
        return _FakeCrossEncoder(name)

    _install_fake_sentence_transformers(monkeypatch, factory)

    first = rerank_module._get_reranker()
    second = rerank_module._get_reranker()

    assert first is second
    assert built == [rerank_module.RERANK_MODEL_NAME], "the cross-encoder must be constructed exactly once"


@pytest.mark.unit
def test_get_reranker_returns_the_cached_model_without_taking_the_lock(monkeypatch):
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", True)
    cached = _FakeCrossEncoder()
    rerank_module._reranker = cached

    assert rerank_module._get_reranker() is cached


@pytest.mark.unit
def test_load_failure_is_latched_and_not_retried(monkeypatch):
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", True)
    attempts: list[int] = []

    def failing_factory(_name):
        attempts.append(1)
        raise OSError("model download failed")

    _install_fake_sentence_transformers(monkeypatch, failing_factory)

    assert rerank_module._get_reranker() is None
    assert rerank_module._reranker_failed is True

    # The latch must short-circuit before the lock — a repeated 30s download
    # attempt per request is the failure mode this guards.
    assert rerank_module._get_reranker() is None
    assert len(attempts) == 1


@pytest.mark.unit
def test_failed_latch_short_circuits_inside_the_lock(monkeypatch):
    """The post-lock ``_reranker_failed`` re-check is the double-checked arm.

    It only executes when another thread latched the failure while this caller
    was blocked, so it is driven by flipping the flag from the lock itself.
    """
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", True)
    real_lock = rerank_module._reranker_lock

    class _LatchingLock:
        def __enter__(self):
            rerank_module._reranker_failed = True
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(rerank_module, "_reranker_lock", _LatchingLock())
    _install_fake_sentence_transformers(monkeypatch, lambda *_: pytest.fail("must not load once the latch is set"))

    assert rerank_module._get_reranker() is None


@pytest.mark.unit
def test_model_set_while_waiting_on_lock_is_returned(monkeypatch):
    """The post-lock ``_reranker`` re-check: another thread won the race."""
    monkeypatch.setattr(rerank_module, "ENABLE_LOCAL_MODELS", True)
    winner = _FakeCrossEncoder("winner")
    real_lock = rerank_module._reranker_lock

    class _PopulatingLock:
        def __enter__(self):
            rerank_module._reranker = winner
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(rerank_module, "_reranker_lock", _PopulatingLock())

    assert rerank_module._get_reranker() is winner


@pytest.mark.unit
def test_rerank_returns_empty_list_for_no_docs(monkeypatch):
    monkeypatch.setattr(rerank_module, "_get_reranker", lambda: pytest.fail("no model load for an empty result set"))

    assert rerank_module.rerank("pit lane", [], top_k=5) == []


@pytest.mark.unit
def test_rerank_preserves_vector_order_when_the_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(rerank_module, "_get_reranker", lambda: None)
    docs = [_Doc("a"), _Doc("b"), _Doc("c")]

    assert rerank_module.rerank("pit lane", docs, top_k=2) == docs[:2]


@pytest.mark.unit
def test_rerank_orders_by_cross_encoder_score_best_first(monkeypatch):
    docs = [_Doc("low"), _Doc("high"), _Doc("mid")]
    model = _FakeCrossEncoder(scores={"low": 0.1, "mid": 0.5, "high": 0.9})
    monkeypatch.setattr(rerank_module, "_get_reranker", lambda: model)

    ranked = rerank_module.rerank("pit lane speed limit", docs, top_k=3)

    assert [d.page_content for d in ranked] == ["high", "mid", "low"]
    # The cross-encoder must see the query paired with each chunk, not the
    # chunks alone — that pairing is the whole point of the model.
    assert model.pairs == [
        ("pit lane speed limit", "low"),
        ("pit lane speed limit", "high"),
        ("pit lane speed limit", "mid"),
    ]


@pytest.mark.unit
def test_rerank_truncates_to_top_k(monkeypatch):
    docs = [_Doc(name) for name in ("a", "b", "c", "d")]
    model = _FakeCrossEncoder(scores={"a": 0.1, "b": 0.4, "c": 0.9, "d": 0.2})
    monkeypatch.setattr(rerank_module, "_get_reranker", lambda: model)

    ranked = rerank_module.rerank("q", docs, top_k=2)

    assert [d.page_content for d in ranked] == ["c", "b"]


@pytest.mark.unit
def test_rerank_uses_empty_text_for_docs_without_page_content(monkeypatch):
    model = _FakeCrossEncoder(scores={"": 1.0})
    monkeypatch.setattr(rerank_module, "_get_reranker", lambda: model)

    ranked = rerank_module.rerank("q", [object()], top_k=1)

    assert len(ranked) == 1
    assert model.pairs == [("q", "")]


@pytest.mark.unit
def test_rerank_falls_back_to_vector_order_when_predict_raises(monkeypatch):
    class _Exploding:
        def predict(self, _pairs):
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(rerank_module, "_get_reranker", _Exploding)
    docs = [_Doc("a"), _Doc("b"), _Doc("c")]

    assert rerank_module.rerank("q", docs, top_k=2) == docs[:2]
