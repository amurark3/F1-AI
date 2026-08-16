"""Tests for app.utils.embeddings — the lazily loaded shared embedder.

The module holds process-global state (``_model``, ``_failed``) guarded by a
lock, so every test resets it. The behaviour that matters:

* torch is never imported when ``ENABLE_LOCAL_MODELS`` is off;
* a load failure is latched, not retried on every call;
* every failure path degrades to ``None`` rather than raising.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.utils import embeddings


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Clear the memoised model between tests so each starts cold."""
    embeddings._model = None
    embeddings._failed = False
    yield
    embeddings._model = None
    embeddings._failed = False


class _FakeModel:
    """Minimal SentenceTransformer stand-in."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[tuple] = []

    def encode(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if isinstance(text, list):
            return [[0.5] * 3 for _ in text]
        return [0.5, 0.25, 0.125]


def _install_fake_sentence_transformers(monkeypatch, factory):
    """Register a fake ``sentence_transformers`` module for the lazy import."""
    module = SimpleNamespace(SentenceTransformer=factory)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)


@pytest.mark.unit
def test_get_embedder_returns_none_when_local_models_disabled(monkeypatch):
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", False)

    # A sentinel that would explode if the lazy import were reached.
    _install_fake_sentence_transformers(monkeypatch, lambda *_: pytest.fail("torch must not be imported when disabled"))

    assert embeddings.get_embedder() is None


@pytest.mark.unit
def test_get_embedder_loads_and_memoises_the_model(monkeypatch):
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", True)
    built: list[str] = []

    def factory(name):
        built.append(name)
        return _FakeModel(name)

    _install_fake_sentence_transformers(monkeypatch, factory)

    first = embeddings.get_embedder()
    second = embeddings.get_embedder()

    assert first is second, "the model must be loaded once and reused"
    assert built == [embeddings.EMBEDDING_MODEL_NAME]


@pytest.mark.unit
def test_get_embedder_returns_cached_model_without_taking_the_lock(monkeypatch):
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", True)
    cached = _FakeModel()
    embeddings._model = cached

    assert embeddings.get_embedder() is cached


@pytest.mark.unit
def test_load_failure_is_latched_and_not_retried(monkeypatch):
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", True)
    attempts: list[int] = []

    def failing_factory(_name):
        attempts.append(1)
        raise OSError("no space left on device")

    _install_fake_sentence_transformers(monkeypatch, failing_factory)

    assert embeddings.get_embedder() is None
    assert embeddings._failed is True

    # Second call must short-circuit on the latch, not re-attempt the load.
    assert embeddings.get_embedder() is None
    assert len(attempts) == 1


@pytest.mark.unit
def test_failed_latch_short_circuits_inside_the_lock(monkeypatch):
    """The post-lock ``_failed`` re-check is the double-checked-locking arm.

    It only runs when another thread latched the failure while this caller was
    blocked on the lock, so it is driven here by flipping the flag from inside
    the lock acquisition itself.
    """
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", True)

    real_lock = embeddings._lock

    class _LatchingLock:
        def __enter__(self):
            embeddings._failed = True
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(embeddings, "_lock", _LatchingLock())
    _install_fake_sentence_transformers(monkeypatch, lambda *_: pytest.fail("must not load once the latch is set"))

    assert embeddings.get_embedder() is None


@pytest.mark.unit
def test_model_set_while_waiting_on_lock_is_returned(monkeypatch):
    """The post-lock ``_model`` re-check: another thread won the race."""
    monkeypatch.setattr(embeddings, "ENABLE_LOCAL_MODELS", True)
    winner = _FakeModel("winner")
    real_lock = embeddings._lock

    class _PopulatingLock:
        def __enter__(self):
            embeddings._model = winner
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(embeddings, "_lock", _PopulatingLock())

    assert embeddings.get_embedder() is winner


@pytest.mark.unit
def test_embed_returns_plain_floats(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(embeddings, "get_embedder", lambda: model)

    vector = embeddings.embed("pit window")

    assert vector == [0.5, 0.25, 0.125]
    assert all(isinstance(x, float) for x in vector)
    # Cosine similarity in pgvector assumes normalized vectors.
    assert model.calls[0][1]["normalize_embeddings"] is True


@pytest.mark.unit
def test_embed_returns_none_without_a_model(monkeypatch):
    monkeypatch.setattr(embeddings, "get_embedder", lambda: None)

    assert embeddings.embed("anything") is None


@pytest.mark.unit
def test_embed_swallows_encode_errors(monkeypatch):
    class _Exploding:
        def encode(self, *_args, **_kwargs):
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(embeddings, "get_embedder", _Exploding)

    assert embeddings.embed("boom") is None


@pytest.mark.unit
def test_embed_batch_returns_one_vector_per_input(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(embeddings, "get_embedder", lambda: model)

    vectors = embeddings.embed_batch(["a", "b"])

    assert vectors == [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]]
    assert model.calls[0][1]["show_progress_bar"] is False


@pytest.mark.unit
def test_embed_batch_returns_none_without_a_model(monkeypatch):
    monkeypatch.setattr(embeddings, "get_embedder", lambda: None)

    assert embeddings.embed_batch(["a"]) is None


@pytest.mark.unit
def test_embed_batch_swallows_encode_errors(monkeypatch):
    class _Exploding:
        def encode(self, *_args, **_kwargs):
            raise ValueError("empty batch")

    monkeypatch.setattr(embeddings, "get_embedder", _Exploding)

    assert embeddings.embed_batch([]) is None


@pytest.mark.unit
def test_to_pgvector_literal_matches_postgres_syntax():
    assert embeddings.to_pgvector_literal([1.0, -0.5]) == "[1.000000,-0.500000]"


@pytest.mark.unit
def test_to_pgvector_literal_fixes_precision_at_six_places():
    # Guards the stored-vector format: a change here silently invalidates every
    # embedding already written to pgvector.
    assert embeddings.to_pgvector_literal([1 / 3]) == "[0.333333]"


@pytest.mark.unit
def test_to_pgvector_literal_handles_empty_vector():
    assert embeddings.to_pgvector_literal([]) == "[]"


@pytest.mark.unit
def test_embedding_dim_matches_minilm():
    assert embeddings.EMBEDDING_DIM == 384
