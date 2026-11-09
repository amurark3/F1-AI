"""Tests for ``scripts.backfill_chat_embeddings`` — vectors for turns saved without one.

The script writes to the table that holds every user's chat history, so what is
pinned is that it touches exactly the rows it should:

* **Only NULL user/assistant rows.** A row that already has a vector (possibly
  written by the live API since the batch was read) keeps it, and a system turn
  stays unembedded, as ``save_message`` leaves it.
* **Dry run by default.** Without ``--apply`` it counts and writes nothing.
* **Idempotent and resumable.** A second run finds nothing to do; a run that
  stops part-way keeps the batches it committed.
* **Refuses rather than guesses.** No ``DATABASE_URL`` (it never reads
  ``backend/.env``, which points at production) or no local models is a
  non-zero exit before any connection is opened.

The database is an in-memory fake that applies the same predicates as the SQL;
separate tests pin those predicates in the SQL text itself.
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from scripts import backfill_chat_embeddings as script

_URL = "postgresql://backfill@localhost/f1ai"


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Table:
    """``chat_message`` as ``{id: (role, content, embedding)}``."""

    def __init__(self, rows: dict[int, tuple[str, str, str | None]]) -> None:
        self.rows = dict(rows)

    def _pending(self) -> list[tuple[int, str]]:
        return [
            (row_id, content)
            for row_id, (role, content, embedding) in sorted(self.rows.items())
            if embedding is None and role in {"user", "assistant"}
        ]

    def count(self) -> list[tuple]:
        return [(len(self._pending()),)]

    def batch(self, after_id: int, limit: int) -> list[tuple]:
        return [row for row in self._pending() if row[0] > after_id][:limit]

    def fill(self, params: list[tuple[str, int]]) -> int:
        written = 0
        for literal, row_id in params:
            role, content, embedding = self.rows[row_id]
            if embedding is None:
                self.rows = {**self.rows, row_id: (role, content, literal)}
                written += 1
        return written


class _Cursor:
    def __init__(self, table: _Table) -> None:
        self._table = table
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def executemany(self, statement: str, params) -> None:
        assert statement == script._FILL
        self.rowcount = self._table.fill(list(params))


class _Connection:
    def __init__(self, table: _Table, fail_on: str | None = None) -> None:
        self.table = table
        self.fail_on = fail_on
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def execute(self, statement: str, params=None) -> _Result:
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("server closed the connection unexpectedly")
        if statement == script._COUNT_PENDING:
            return _Result(self.table.count())
        if statement == script._NEXT_BATCH:
            return _Result(self.table.batch(*params))
        raise AssertionError(f"unexpected SQL: {statement}")

    def cursor(self) -> _Cursor:
        return _Cursor(self.table)

    def commit(self) -> None:
        self.commits += 1


def _history() -> _Table:
    return _Table(
        {
            1: ("user", "who wins Monaco", None),
            2: ("assistant", "Leclerc", "[0.900000]"),
            3: ("system", "you are a race engineer", None),
            4: ("user", "and Silverstone?", None),
            5: ("assistant", "Norris", None),
        }
    )


@pytest.fixture
def ready(monkeypatch):
    """A database URL and local models: the preconditions for a real run."""
    monkeypatch.setenv("DATABASE_URL", _URL)
    monkeypatch.setattr(script, "ENABLE_LOCAL_MODELS", True)


@pytest.fixture
def embedded(monkeypatch) -> list[list[str]]:
    """Every batch of texts handed to the shared embedder."""
    batches: list[list[str]] = []

    def embed_batch(texts):
        batches.append(list(texts))
        return [[0.5, float(len(text))] for text in texts]

    monkeypatch.setattr(script, "embed_batch", embed_batch)
    return batches


def _install(monkeypatch, conn: _Connection) -> _Connection:
    monkeypatch.setattr(script, "_connect", lambda: conn)
    return conn


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("url", [None, "", "   "])
def test_without_a_database_url_it_refuses_before_connecting(monkeypatch, capsys, url):
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(script, "ENABLE_LOCAL_MODELS", True)
    monkeypatch.setattr(script, "_connect", lambda: pytest.fail("no connection without a URL"))

    assert script.main(["--apply"]) == script.EXIT_NO_DATABASE
    assert "never reads backend/.env" in capsys.readouterr().out


@pytest.mark.unit
def test_with_local_models_off_it_refuses_before_connecting(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", _URL)
    monkeypatch.setattr(script, "ENABLE_LOCAL_MODELS", False)
    monkeypatch.setattr(script, "_connect", lambda: pytest.fail("nothing to embed with"))

    assert script.main([]) == script.EXIT_NO_MODELS
    assert "ENABLE_LOCAL_MODELS=true" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("size", ["0", "-5", "many"])
def test_a_batch_size_that_is_not_a_positive_integer_is_rejected(size):
    with pytest.raises(SystemExit) as exit_info:
        script.main(["--batch-size", size])

    assert exit_info.value.code == 2


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_dry_run_reports_the_count_and_writes_nothing(monkeypatch, capsys, ready):
    conn = _install(monkeypatch, _Connection(_history()))
    before = dict(conn.table.rows)
    monkeypatch.setattr(script, "embed_batch", lambda _texts: pytest.fail("a dry run embeds nothing"))

    assert script.main([]) == script.EXIT_OK

    out = capsys.readouterr().out
    assert "Chat turns without an embedding: 3" in out
    assert "Dry run: nothing written. Re-run with --apply to embed them." in out
    assert conn.table.rows == before
    assert conn.commits == 0


@pytest.mark.unit
@pytest.mark.parametrize("argv", [[], ["--apply"]])
def test_nothing_pending_is_a_clean_exit(monkeypatch, capsys, ready, argv):
    _install(monkeypatch, _Connection(_Table({1: ("user", "hi", "[0.100000]")})))
    monkeypatch.setattr(script, "embed_batch", lambda _texts: pytest.fail("nothing to embed"))

    assert script.main(argv) == script.EXIT_OK
    assert "Nothing to backfill." in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --apply
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_embeds_only_the_null_user_and_assistant_turns(monkeypatch, capsys, ready, embedded):
    conn = _install(monkeypatch, _Connection(_history()))

    assert script.main(["--apply", "--batch-size", "2"]) == script.EXIT_OK

    rows = conn.table.rows
    assert rows[1][2] == "[0.500000,15.000000]"
    assert rows[4][2] == "[0.500000,16.000000]"
    assert rows[5][2] == "[0.500000,6.000000]"
    assert rows[2][2] == "[0.900000]", "an existing vector is never rewritten"
    assert rows[3][2] is None, "system turns stay unembedded, as save_message leaves them"
    # Batched in id order, one commit per batch.
    assert embedded == [["who wins Monaco", "and Silverstone?"], ["Norris"]]
    assert conn.commits == 2
    out = capsys.readouterr().out
    assert "  batch 1: embedded 2 of 2 (through id 4)" in out
    assert "  batch 2: embedded 1 of 1 (through id 5)" in out
    assert "Done: embedded 3 turn(s); 0 already had a vector." in out


@pytest.mark.unit
def test_a_second_run_changes_nothing(monkeypatch, capsys, ready, embedded):
    conn = _install(monkeypatch, _Connection(_history()))
    script.main(["--apply"])
    after_first = dict(conn.table.rows)
    capsys.readouterr()

    assert script.main(["--apply"]) == script.EXIT_OK

    assert conn.table.rows == after_first
    assert len(embedded) == 1
    assert "Chat turns without an embedding: 0" in capsys.readouterr().out


@pytest.mark.unit
def test_a_turn_the_api_embedded_since_the_read_is_left_as_the_api_wrote_it(monkeypatch, capsys, ready):
    conn = _install(monkeypatch, _Connection(_history()))

    def embed_batch(texts):
        # The live API saves row 4's vector while this batch is being embedded.
        role, content, _ = conn.table.rows[4]
        conn.table.rows = {**conn.table.rows, 4: (role, content, "[0.700000]")}
        return [[0.5] for _ in texts]

    monkeypatch.setattr(script, "embed_batch", embed_batch)

    assert script.main(["--apply"]) == script.EXIT_OK

    assert conn.table.rows[4][2] == "[0.700000]"
    out = capsys.readouterr().out
    assert "  batch 1: embedded 2 of 3 (through id 5)" in out
    assert "Done: embedded 2 turn(s); 1 already had a vector." in out


@pytest.mark.unit
def test_an_embedder_failure_stops_the_run_and_keeps_the_committed_batches(monkeypatch, capsys, ready):
    conn = _install(monkeypatch, _Connection(_history()))
    results = iter([[[0.5], [0.5]], None])
    monkeypatch.setattr(script, "embed_batch", lambda _texts: next(results))

    assert script.main(["--apply", "--batch-size", "2"]) == script.EXIT_EMBED_FAILED

    assert conn.commits == 1
    assert conn.table.rows[1][2] == "[0.500000]"
    assert conn.table.rows[5][2] is None
    assert "Backfill stopped: the embedding model returned nothing. 2 turn(s) embedded" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("failing_statement", ["SELECT COUNT(*)", "SELECT id, content"])
def test_a_database_error_exits_2_with_the_reason(monkeypatch, capsys, ready, embedded, failing_statement):
    _install(monkeypatch, _Connection(_history(), fail_on=failing_statement))

    assert script.main(["--apply"]) == script.EXIT_DATABASE_ERROR
    assert "Backfill failed: server closed the connection unexpectedly." in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The SQL contract the fake above stands in for
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("statement", ["_COUNT_PENDING", "_NEXT_BATCH"])
def test_reads_select_only_null_user_and_assistant_turns(statement):
    sql = getattr(script, statement)

    assert "FROM chat_message" in sql
    assert "embedding IS NULL" in sql
    assert "role IN ('user', 'assistant')" in sql


@pytest.mark.unit
def test_batches_page_by_id_so_every_run_terminates():
    """Keyset paging: a row the UPDATE skipped can never be read again in the same run."""
    assert "id > %s" in script._NEXT_BATCH
    assert "ORDER BY id" in script._NEXT_BATCH
    assert "LIMIT %s" in script._NEXT_BATCH


@pytest.mark.unit
def test_the_write_only_fills_a_vector_that_is_still_null():
    assert script._FILL == "UPDATE chat_message SET embedding = %s::vector WHERE id = %s AND embedding IS NULL"


@pytest.mark.unit
def test_connect_opens_the_url_from_the_environment(monkeypatch):
    opened: list[tuple[str, dict]] = []
    psycopg = ModuleType("psycopg")
    psycopg.connect = lambda url, **kwargs: opened.append((url, kwargs)) or "conn"
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setenv("DATABASE_URL", _URL)

    assert script._connect() == "conn"
    # Not autocommit: each batch commits as a unit.
    assert opened == [(_URL, {})]
