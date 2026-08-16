"""Tests for app.rag.pgvector_store — the FIA rulebook corpus in Postgres.

Two risks live here. The first is availability: the store is reached on every
rules search and every chat rulebook tool call, so an unset ``DATABASE_URL`` or
an unreachable Supabase must degrade to "no results", never to a 500. The
second is correctness of the SQL contract — the parameter order of the two
similarity statements, the ``::vector`` casts, and the truncate-then-insert
sequence in :func:`replace_all`. A silent parameter swap there would return
plausible-looking but wrong regulations.

The ``psycopg`` boundary is faked wholesale: no connection is ever opened, and
the recorded statements are asserted against directly.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    # `Self` lands in typing at 3.11; this runs on 3.10, and `from __future__
    # import annotations` means the name is never evaluated at runtime.
    from typing_extensions import Self

from app.rag import pgvector_store


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def executemany(self, statement: str, rows) -> None:
        self._conn.executemany_calls.append((statement, list(rows)))


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
        self.executemany_calls: list[tuple[str, list]] = []
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> bool:
        self.closed = True
        return False

    def execute(self, statement: str, params=None) -> _FakeResult:
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("connection reset by peer")
        self.statements.append((statement, params))
        return _FakeResult(self.rows)

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


@pytest.fixture
def enabled_store(monkeypatch):
    """Turn the store on and hand back a recording connection."""
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    conn = _FakeConnection()
    monkeypatch.setattr(pgvector_store, "_connect", lambda: conn)
    return conn


def _install_connection(monkeypatch, conn: _FakeConnection) -> _FakeConnection:
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(pgvector_store, "_connect", lambda: conn)
    return conn


# ---------------------------------------------------------------------------
# Enablement flag and connection construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgresql://user:pw@db.example.com/postgres", True),
        ("   ", False),  # whitespace-only is as good as unset
        ("", False),
    ],
)
def test_rulebook_enabled_follows_database_url(monkeypatch, reload_module, database_url, expected):
    monkeypatch.setenv("DATABASE_URL", database_url)

    reloaded = reload_module("app.rag.pgvector_store")

    assert reloaded.RULEBOOK_ENABLED is expected


@pytest.mark.unit
def test_rulebook_disabled_when_database_url_is_absent(monkeypatch, reload_module):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert reload_module("app.rag.pgvector_store").RULEBOOK_ENABLED is False


@pytest.mark.unit
def test_connect_uses_autocommit_so_ddl_is_not_left_in_a_transaction(monkeypatch):
    calls: list[tuple] = []

    def fake_connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        return _FakeConnection()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db.example.com/postgres")

    pgvector_store._connect()

    assert calls == [("postgresql://user:pw@db.example.com/postgres", {"autocommit": True})]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ensure_schema_creates_the_extension_table_and_indexes(enabled_store):
    pgvector_store.ensure_schema()

    ddl = enabled_store.statements[0][0]
    assert "CREATE EXTENSION IF NOT EXISTS vector" in ddl
    assert "CREATE TABLE IF NOT EXISTS rulebook_chunk" in ddl
    assert "USING hnsw (embedding vector_cosine_ops)" in ddl


@pytest.mark.unit
def test_schema_vector_width_matches_the_shared_embedder():
    # A mismatch here makes every INSERT fail at runtime, not at deploy time.
    from app.utils.embeddings import EMBEDDING_DIM

    assert f"vector({EMBEDDING_DIM})" in pgvector_store._SCHEMA_SQL


@pytest.mark.unit
def test_ensure_schema_conn_reuses_the_caller_connection(enabled_store):
    pgvector_store.ensure_schema_conn(enabled_store)

    assert len(enabled_store.statements) == 1


# ---------------------------------------------------------------------------
# count()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_count_returns_zero_when_disabled(monkeypatch):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", False)
    monkeypatch.setattr(pgvector_store, "_connect", lambda: pytest.fail("must not connect while disabled"))

    assert pgvector_store.count() == 0


@pytest.mark.unit
def test_count_returns_the_stored_row_count(monkeypatch):
    _install_connection(monkeypatch, _FakeConnection(rows=[(4212,)]))

    assert pgvector_store.count() == 4212


@pytest.mark.unit
def test_count_returns_zero_when_the_query_yields_no_row(monkeypatch):
    _install_connection(monkeypatch, _FakeConnection(rows=[]))

    assert pgvector_store.count() == 0


@pytest.mark.unit
def test_count_degrades_to_zero_when_the_database_is_unreachable(monkeypatch):
    def exploding_connect():
        raise OSError("could not translate host name")

    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(pgvector_store, "_connect", exploding_connect)

    assert pgvector_store.count() == 0


# ---------------------------------------------------------------------------
# replace_all()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replace_all_refuses_to_run_when_disabled(monkeypatch):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        pgvector_store.replace_all([{"content": "x"}])


@pytest.mark.unit
def test_replace_all_writes_nothing_for_an_empty_corpus(enabled_store):
    assert pgvector_store.replace_all([]) == 0
    assert enabled_store.statements == []


@pytest.mark.unit
def test_replace_all_raises_when_the_embedder_is_unavailable(monkeypatch, enabled_store):
    # The deployed default: ENABLE_LOCAL_MODELS off means embed_batch is None.
    monkeypatch.setattr(pgvector_store, "embed_batch", lambda _texts: None)

    with pytest.raises(RuntimeError, match="Embedding model unavailable"):
        pgvector_store.replace_all([{"content": "Article 1"}])


@pytest.mark.unit
def test_replace_all_truncates_before_inserting(monkeypatch):
    conn = _install_connection(monkeypatch, _FakeConnection())
    monkeypatch.setattr(pgvector_store, "embed_batch", lambda texts: [[0.5, 0.25] for _ in texts])

    written = pgvector_store.replace_all(
        [
            {"source_year": 2025, "doc_type": "Sporting", "filename": "sporting.pdf", "page": 3, "content": "A"},
            {"source_year": "2026", "doc_type": "Technical", "filename": "tech.pdf", "page": None, "content": "B"},
        ]
    )

    assert written == 2
    # Order matters: a truncate issued after the insert would wipe the corpus.
    assert "TRUNCATE rulebook_chunk RESTART IDENTITY" in conn.statements[1][0]
    statement, rows = conn.executemany_calls[0]
    assert "%s::vector" in statement
    assert rows == [
        ("2025", "Sporting", "sporting.pdf", 3, "A", "[0.500000,0.250000]"),
        ("2026", "Technical", "tech.pdf", None, "B", "[0.500000,0.250000]"),
    ]


@pytest.mark.unit
def test_replace_all_defaults_missing_metadata_fields(monkeypatch):
    conn = _install_connection(monkeypatch, _FakeConnection())
    monkeypatch.setattr(pgvector_store, "embed_batch", lambda texts: [[1.0] for _ in texts])

    pgvector_store.replace_all([{"content": "orphan chunk"}])

    assert conn.executemany_calls[0][1] == [("", None, None, None, "orphan chunk", "[1.000000]")]


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_search_returns_nothing_for_a_blank_query(monkeypatch, query):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(pgvector_store, "_connect", lambda: pytest.fail("a blank query must not reach the database"))

    assert pgvector_store.search(query, 2025) == []


@pytest.mark.unit
def test_search_returns_nothing_when_disabled(monkeypatch):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", False)

    assert pgvector_store.search("pit lane", 2025) == []


@pytest.mark.unit
def test_search_returns_nothing_when_the_query_cannot_be_embedded(monkeypatch):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: None)
    monkeypatch.setattr(pgvector_store, "_connect", lambda: pytest.fail("no vector means no query"))

    assert pgvector_store.search("pit lane", 2025) == []


@pytest.mark.unit
def test_search_binds_the_vector_year_and_limit_in_statement_order(monkeypatch):
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[]))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    pgvector_store.search("pit lane", 2025, k=7)

    statement, params = conn.statements[1]
    assert "AND doc_type" not in statement
    # The same literal is bound twice: once for the similarity projection and
    # once for the ORDER BY distance. Swapping these silently breaks ranking.
    assert params == ["[0.500000]", "2025", "[0.500000]", 7]


@pytest.mark.unit
@pytest.mark.parametrize("category", [None, "all", "All", "ALL"])
def test_search_without_a_real_category_queries_every_doc_type(monkeypatch, category):
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[]))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    pgvector_store.search("pit lane", 2025, category=category)

    assert conn.statements[1][0] == pgvector_store._SEARCH_ALL_CATEGORIES


@pytest.mark.unit
def test_search_with_a_category_adds_the_doc_type_predicate(monkeypatch):
    conn = _install_connection(monkeypatch, _FakeConnection(rows=[]))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    pgvector_store.search("pit lane", 2026, category="Sporting", k=3)

    statement, params = conn.statements[1]
    assert statement == pgvector_store._SEARCH_BY_CATEGORY
    assert params == ["[0.500000]", "2026", "Sporting", "[0.500000]", 3]


@pytest.mark.unit
def test_search_maps_rows_into_rulebook_hits(monkeypatch):
    _install_connection(
        monkeypatch,
        _FakeConnection(rows=[("Article 34.7 ...", "Sporting", "2025_sporting.pdf", 42, 0.876543)]),
    )
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    hits = pgvector_store.search("pit lane", 2025)

    assert hits == [
        pgvector_store.RulebookHit(
            page_content="Article 34.7 ...",
            metadata={"type": "Sporting", "filename": "2025_sporting.pdf", "page": 42, "source_year": "2025"},
            similarity=0.8765,
        )
    ]


@pytest.mark.unit
def test_search_substitutes_placeholders_for_null_metadata(monkeypatch):
    _install_connection(monkeypatch, _FakeConnection(rows=[("body", None, None, None, 0.5)]))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    hit = pgvector_store.search("pit lane", 2025)[0]

    assert hit.metadata == {"type": "Regulatory", "filename": "Unknown PDF", "page": None, "source_year": "2025"}


@pytest.mark.unit
def test_search_degrades_to_empty_when_the_query_fails(monkeypatch):
    _install_connection(monkeypatch, _FakeConnection(fail_on="SELECT content"))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])

    assert pgvector_store.search("pit lane", 2025) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("call", "expected_event"),
    [
        (lambda: pgvector_store.search("pit lane", 2025), "rulebook_pg.search_failed"),
        (pgvector_store.count, "rulebook_pg.count_failed"),
    ],
)
def test_degraded_reads_are_logged_rather_than_swallowed(monkeypatch, call, expected_event):
    """Both read paths return a neutral value on failure — that has to be visible."""
    warnings: list[tuple[str, dict]] = []

    _install_connection(monkeypatch, _FakeConnection(fail_on="SELECT "))
    monkeypatch.setattr(pgvector_store, "embed", lambda _q: [0.5])
    monkeypatch.setattr(
        pgvector_store,
        "logger",
        SimpleNamespace(warning=lambda event, **kw: warnings.append((event, kw)), info=lambda *a, **kw: None),
    )

    call()

    assert [event for event, _ in warnings] == [expected_event]
    assert "connection reset by peer" in warnings[0][1]["error"]


@pytest.mark.unit
def test_rulebook_hit_is_immutable():
    hit = pgvector_store.RulebookHit(page_content="body")

    with pytest.raises(AttributeError):
        hit.similarity = 1.0  # type: ignore[misc]


@pytest.mark.unit
def test_rulebook_hit_defaults_to_an_empty_metadata_dict():
    first = pgvector_store.RulebookHit(page_content="a")
    second = pgvector_store.RulebookHit(page_content="b")

    first.metadata["page"] = 1
    assert second.metadata == {}, "each hit needs its own metadata dict, not a shared default"
