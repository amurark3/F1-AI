"""Tests for app.data.memory — conversation memory and personalization.

Three risks are pinned here.

**Never break the chat.** Every function is called on the request path of a
user conversation. With ``DATABASE_URL`` unset, an unreachable Postgres, or a
model that will not load, each one must degrade to a no-op / empty result and
never raise into the streaming handler.

**Never load torch by accident.** ``ENABLE_LOCAL_MODELS`` is off by default and
this module holds a *second* copy of the embedding model, so it needs its own
gate. The enabled path is exercised through a fake ``sentence_transformers``
injected into ``sys.modules`` — no torch import, no real model.

**SQL parameter order.** Both recall statements interpolate the query vector
twice (similarity select and ORDER BY) around the user and thread predicates.
A swap there returns confidently wrong memories, so the recorded parameters
are asserted against directly.

The ``psycopg`` boundary is faked wholesale; no connection is ever opened.
"""

from __future__ import annotations

from datetime import datetime
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.data import memory


class _FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConnection:
    """Records every statement so the SQL contract can be asserted on."""

    def __init__(self, rows: list[tuple] | None = None, fail_on: str | None = None) -> None:
        self.rows = rows or []
        self.fail_on = fail_on
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def execute(self, statement: str, params=None) -> _FakeResult:
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("connection reset by peer")
        self.statements.append((statement, params))
        return _FakeResult(self.rows)


class _FakeEmbedder:
    def __init__(self, vector=(0.5, 0.25)) -> None:
        self.vector = list(vector)
        self.calls: list[tuple[str, dict]] = []

    def encode(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return self.vector


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Schema flag and embedder are process-global singletons."""
    memory._schema_ready = False
    memory._embedder = None
    memory._embedder_failed = False
    yield
    memory._schema_ready = False
    memory._embedder = None
    memory._embedder_failed = False


@pytest.fixture
def enabled(monkeypatch):
    """Turn memory on and short-circuit embedding to a fixed vector."""
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "_embed", lambda text: [0.5, 0.25])


def _install_connection(monkeypatch, conn: _FakeConnection) -> _FakeConnection:
    monkeypatch.setattr(memory, "_connect", lambda: conn)
    return conn


def _install_fake_psycopg(monkeypatch, connect) -> None:
    """Register a fake ``psycopg`` package (plus ``psycopg.types.json``)."""
    json_module = ModuleType("psycopg.types.json")
    json_module.Jsonb = lambda value: ("jsonb", value)
    types_module = ModuleType("psycopg.types")
    types_module.json = json_module
    root = ModuleType("psycopg")
    root.connect = connect
    root.types = types_module

    monkeypatch.setitem(sys.modules, "psycopg", root)
    monkeypatch.setitem(sys.modules, "psycopg.types", types_module)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", json_module)


# ---------------------------------------------------------------------------
# Connection + schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connect_opens_an_autocommit_connection_to_the_configured_url(monkeypatch):
    opened: list[tuple[str, dict]] = []
    conn = _FakeConnection()
    _install_fake_psycopg(monkeypatch, lambda url, **kwargs: opened.append((url, kwargs)) or conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/f1")

    assert memory._connect() is conn
    # Autocommit: every statement here is a standalone upsert or read, and a
    # forgotten commit would silently drop writes.
    assert opened == [("postgresql://localhost/f1", {"autocommit": True})]


@pytest.mark.unit
def test_schema_is_created_once_per_process():
    conn = _FakeConnection()

    memory._ensure_schema(conn)
    memory._ensure_schema(conn)

    assert len(conn.statements) == 1
    assert "CREATE TABLE IF NOT EXISTS chat_message" in conn.statements[0][0]
    assert f"vector({memory.EMBEDDING_DIM})" in conn.statements[0][0]


@pytest.mark.unit
def test_schema_creation_short_circuits_inside_the_lock(monkeypatch):
    """The post-lock re-check: another thread created the schema while we waited."""
    real_lock = memory._schema_lock

    class _LatchingLock:
        def __enter__(self):
            memory._schema_ready = True
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(memory, "_schema_lock", _LatchingLock())
    conn = _FakeConnection()

    memory._ensure_schema(conn)

    assert conn.statements == []


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_model_is_loaded_when_local_models_are_disabled(monkeypatch):
    monkeypatch.setattr(memory, "ENABLE_LOCAL_MODELS", False)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=lambda *_: pytest.fail("torch must not be imported when disabled")),
    )

    assert memory._get_embedder() is None


@pytest.mark.unit
def test_the_embedder_is_loaded_once_and_memoised(monkeypatch):
    monkeypatch.setattr(memory, "ENABLE_LOCAL_MODELS", True)
    built: list[str] = []
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=lambda name: built.append(name) or _FakeEmbedder()),
    )

    first = memory._get_embedder()

    assert memory._get_embedder() is first
    assert built == [memory.EMBEDDING_MODEL_NAME]


@pytest.mark.unit
def test_a_load_failure_is_latched_and_not_retried(monkeypatch):
    monkeypatch.setattr(memory, "ENABLE_LOCAL_MODELS", True)
    attempts: list[int] = []

    def failing(_name):
        attempts.append(1)
        raise OSError("no space left on device")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=failing))

    assert memory._get_embedder() is None
    assert memory._get_embedder() is None
    assert len(attempts) == 1, "a failed load must not be retried on every chat turn"


@pytest.mark.unit
@pytest.mark.parametrize("latched_field", ["_embedder", "_embedder_failed"])
def test_another_thread_winning_the_load_race_is_honoured(monkeypatch, latched_field):
    """The two post-lock re-checks, driven from inside the lock acquisition."""
    monkeypatch.setattr(memory, "ENABLE_LOCAL_MODELS", True)
    winner = _FakeEmbedder()
    real_lock = memory._embedder_lock

    class _LatchingLock:
        def __enter__(self):
            setattr(memory, latched_field, winner if latched_field == "_embedder" else True)
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(memory, "_embedder_lock", _LatchingLock())
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=lambda *_: pytest.fail("the race was already won")),
    )

    expected = winner if latched_field == "_embedder" else None
    assert memory._get_embedder() is expected


@pytest.mark.unit
def test_embed_normalises_and_returns_plain_floats(monkeypatch):
    embedder = _FakeEmbedder()
    monkeypatch.setattr(memory, "_get_embedder", lambda: embedder)

    vector = memory._embed("who wins Monaco")

    assert vector == [0.5, 0.25]
    # Cosine distance in pgvector assumes unit-length vectors.
    assert embedder.calls[0][1] == {"normalize_embeddings": True}


@pytest.mark.unit
def test_embed_returns_none_without_a_model(monkeypatch):
    monkeypatch.setattr(memory, "_get_embedder", lambda: None)

    assert memory._embed("anything") is None


@pytest.mark.unit
def test_embed_swallows_encode_failures(monkeypatch):
    class _Exploding:
        def encode(self, *_args, **_kwargs):
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(memory, "_get_embedder", _Exploding)

    assert memory._embed("boom") is None


@pytest.mark.unit
def test_vector_literal_matches_postgres_syntax_at_six_places():
    assert memory._vec_literal([1.0, -0.5, 1 / 3]) == "[1.000000,-0.500000,0.333333]"


# ---------------------------------------------------------------------------
# save_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("memory_enabled", "user_id", "content"),
    [
        (False, "u1", "hello"),
        (True, "", "hello"),
        (True, "u1", ""),
    ],
)
def test_save_message_is_a_no_op_when_there_is_nothing_to_store(monkeypatch, memory_enabled, user_id, content):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", memory_enabled)
    monkeypatch.setattr(memory, "_connect", lambda: pytest.fail("no connection should be opened"))

    assert memory.save_message(user_id, "t1", "user", content) is None


@pytest.mark.unit
def test_save_message_stores_the_embedding_alongside_the_turn(monkeypatch, enabled):
    conn = _install_connection(monkeypatch, _FakeConnection())

    memory.save_message("u1", "t1", "user", "who wins Monaco")

    statement, params = conn.statements[-1]
    assert "embedding" in statement
    assert "%s::vector" in statement
    assert params == ("u1", "t1", "user", "who wins Monaco", "[0.500000,0.250000]")


@pytest.mark.unit
def test_a_system_turn_is_stored_without_an_embedding(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "_embed", lambda text: pytest.fail("only user/assistant turns are embedded"))
    conn = _install_connection(monkeypatch, _FakeConnection())

    memory.save_message("u1", "t1", "system", "you are a race engineer")

    statement, params = conn.statements[-1]
    assert "embedding" not in statement
    assert params == ("u1", "t1", "system", "you are a race engineer")


@pytest.mark.unit
def test_a_turn_that_cannot_be_embedded_is_still_stored(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "_embed", lambda text: None)
    conn = _install_connection(monkeypatch, _FakeConnection())

    memory.save_message("u1", "t1", "assistant", "Verstappen")

    assert "embedding" not in conn.statements[-1][0]


@pytest.mark.unit
def test_a_database_outage_never_breaks_the_chat_turn(monkeypatch, enabled):
    _install_connection(monkeypatch, _FakeConnection(fail_on="INSERT INTO chat_message"))

    assert memory.save_message("u1", "t1", "user", "hi") is None


# ---------------------------------------------------------------------------
# recall_relevant
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("memory_enabled", "user_id", "query"),
    [(False, "u1", "q"), (True, "", "q"), (True, "u1", "")],
)
def test_recall_returns_nothing_when_there_is_nothing_to_search(monkeypatch, memory_enabled, user_id, query):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", memory_enabled)
    monkeypatch.setattr(memory, "_connect", lambda: pytest.fail("no connection should be opened"))

    assert memory.recall_relevant(user_id, query) == []


@pytest.mark.unit
def test_recall_returns_nothing_when_the_query_cannot_be_embedded(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "_embed", lambda text: None)
    monkeypatch.setattr(memory, "_connect", lambda: pytest.fail("no vector, no search"))

    assert memory.recall_relevant("u1", "q") == []


@pytest.mark.unit
def test_recall_across_all_threads_binds_the_vector_twice_around_the_user(monkeypatch, enabled):
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[]))

    memory.recall_relevant("u1", "monaco", k=7)

    statement, params = conn.statements[-1]
    assert "thread_id <>" not in statement
    # sim-select vector, user, ORDER BY vector, limit.
    assert params == ["[0.500000,0.250000]", "u1", "[0.500000,0.250000]", 7]


@pytest.mark.unit
def test_recall_excluding_a_thread_binds_the_thread_between_the_vectors(monkeypatch, enabled):
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[]))

    memory.recall_relevant("u1", "monaco", k=4, exclude_thread="t9")

    statement, params = conn.statements[-1]
    assert "thread_id <> %s" in statement
    assert params == ["[0.500000,0.250000]", "u1", "t9", "[0.500000,0.250000]", 4]


@pytest.mark.unit
def test_recall_maps_rows_onto_the_public_shape(monkeypatch, enabled):
    rows = [
        ("user", "who wins Monaco", "t1", datetime(2026, 5, 24, 14, 30), 0.87654),
        ("assistant", "Leclerc", "t2", None, 0.5),
    ]
    _install_connection(monkeypatch, _FakeConnection(rows=rows))

    recalled = memory.recall_relevant("u1", "monaco")

    assert recalled[0] == {
        "role": "user",
        "content": "who wins Monaco",
        "thread_id": "t1",
        "created_at": "2026-05-24T14:30:00",
        "similarity": 0.877,
    }
    assert recalled[1]["created_at"] is None


@pytest.mark.unit
def test_recall_degrades_to_an_empty_list_on_a_database_error(monkeypatch, enabled):
    _install_connection(monkeypatch, _FakeConnection(fail_on="SELECT role"))

    assert memory.recall_relevant("u1", "monaco") == []


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("memory_enabled", "user_id"), [(False, "u1"), (True, "")])
def test_get_profile_is_empty_without_memory_or_a_user(monkeypatch, memory_enabled, user_id):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", memory_enabled)
    monkeypatch.setattr(memory, "_connect", lambda: pytest.fail("no connection should be opened"))

    assert memory.get_profile(user_id) == {}


@pytest.mark.unit
def test_get_profile_returns_the_stored_row(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_connection(monkeypatch, _FakeConnection(rows=[("VER", "Red Bull", {"units": "metric"})]))

    assert memory.get_profile("u1") == {
        "favorite_driver": "VER",
        "favorite_team": "Red Bull",
        "prefs": {"units": "metric"},
    }


@pytest.mark.unit
def test_get_profile_defaults_missing_prefs_to_an_empty_dict(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_connection(monkeypatch, _FakeConnection(rows=[("VER", None, None)]))

    assert memory.get_profile("u1")["prefs"] == {}


@pytest.mark.unit
def test_get_profile_is_empty_for_an_unknown_user(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_connection(monkeypatch, _FakeConnection(rows=[]))

    assert memory.get_profile("nobody") == {}


@pytest.mark.unit
def test_get_profile_degrades_on_a_database_error(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_connection(monkeypatch, _FakeConnection(fail_on="SELECT favorite_driver"))

    assert memory.get_profile("u1") == {}


@pytest.mark.unit
def test_set_profile_is_a_no_op_without_memory(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", False)
    _install_fake_psycopg(monkeypatch, lambda *a, **k: pytest.fail("no connection should be opened"))

    assert memory.set_profile("u1", favorite_driver="VER") == {}


@pytest.mark.unit
def test_set_profile_upserts_and_returns_the_merged_profile(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_fake_psycopg(monkeypatch, lambda *a, **k: None)
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[("VER", "Red Bull", {"units": "metric"})]))

    profile = memory.set_profile("u1", favorite_driver="VER", prefs={"units": "metric"})

    upsert, params = conn.statements[-2]
    assert "ON CONFLICT (user_id) DO UPDATE" in upsert
    # COALESCE keeps a field the caller did not supply rather than nulling it.
    assert "COALESCE(EXCLUDED.favorite_team, user_profile.favorite_team)" in upsert
    assert params == ("u1", "VER", None, ("jsonb", {"units": "metric"}))
    assert profile["favorite_driver"] == "VER"


@pytest.mark.unit
def test_set_profile_still_returns_the_profile_after_a_write_failure(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    _install_fake_psycopg(monkeypatch, lambda *a, **k: None)
    _install_connection(monkeypatch, _FakeConnection(fail_on="INSERT INTO user_profile"))

    assert memory.set_profile("u1", favorite_team="Ferrari") == {}


# ---------------------------------------------------------------------------
# build_memory_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("memory_enabled", "user_id"), [(False, "u1"), (True, "")])
def test_no_memory_context_without_memory_or_a_user(monkeypatch, memory_enabled, user_id):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", memory_enabled)

    assert memory.build_memory_context(user_id, "q") == ""


@pytest.mark.unit
def test_memory_context_is_empty_when_nothing_is_known(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "get_profile", lambda user_id: {})
    monkeypatch.setattr(memory, "recall_relevant", lambda *a, **k: [])

    assert memory.build_memory_context("u1", "q") == ""


@pytest.mark.unit
def test_memory_context_describes_the_user_and_the_recalled_turns(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "get_profile", lambda user_id: {"favorite_driver": "VER", "favorite_team": "Red Bull"})
    monkeypatch.setattr(
        memory,
        "recall_relevant",
        lambda *a, **k: [
            {"role": "user", "content": "I love Monaco", "similarity": 0.9},
            {"role": "assistant", "content": "too weak to recall", "similarity": 0.2},
        ],
    )

    context = memory.build_memory_context("u1", "monaco", thread_id="t1")

    assert "ABOUT THIS USER: favourite driver is VER; supports Red Bull." in context
    assert "- (user) I love Monaco" in context
    # Below the 0.35 similarity floor: a weak match would poison the prompt.
    assert "too weak to recall" not in context


@pytest.mark.unit
def test_memory_context_excludes_the_current_thread_from_recall(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "get_profile", lambda user_id: {"favorite_team": "Ferrari"})
    seen: list[dict] = []
    monkeypatch.setattr(memory, "recall_relevant", lambda *a, **k: seen.append(k) or [])

    context = memory.build_memory_context("u1", "monaco", thread_id="t7")

    # Recalling the live thread back into its own prompt is duplication, not memory.
    assert seen == [{"k": 3, "exclude_thread": "t7"}]
    assert context == "ABOUT THIS USER: supports Ferrari."


@pytest.mark.unit
def test_recalled_content_is_truncated_before_entering_the_prompt(monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_ENABLED", True)
    monkeypatch.setattr(memory, "get_profile", lambda user_id: {})
    monkeypatch.setattr(
        memory, "recall_relevant", lambda *a, **k: [{"role": "user", "content": "x" * 500, "similarity": 0.9}]
    )

    context = memory.build_memory_context("u1", "q")

    assert context == "RELEVANT PAST CONVERSATION:\n- (user) " + "x" * 200
