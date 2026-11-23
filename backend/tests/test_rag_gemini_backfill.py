"""Tests for app.rag.gemini_backfill — filling Gemini vectors for stored passages.

The backfill runs against the free tier's daily quota, so it must: touch only
rows still missing a vector, stop cleanly on a 429 with honest counts, and pick
up where it stopped on the next run. The table is faked as a dict of rows.
"""

from __future__ import annotations

from typing import Self

import pytest

from app.rag import gemini_backfill, gemini_embeddings, pgvector_store


class _QuotaError(Exception):
    code = 429


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple:
        return self._rows[0]


class _Table:
    """``rulebook_chunk`` reduced to id → (content, gemini vector or None)."""

    def __init__(self, contents: list[str], filled: set[int] = frozenset()) -> None:
        self.rows = {i: (c, "[seed]" if i in filled else None) for i, c in enumerate(contents, start=1)}
        self.updates: list[int] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def _missing(self) -> list[tuple]:
        return [(i, c) for i, (c, v) in sorted(self.rows.items()) if v is None]

    def execute(self, statement: str, params: list | None = None) -> _Result:
        if statement == gemini_backfill._NEXT_BATCH:
            return _Result(self._missing()[: params[0]])
        assert statement == gemini_backfill._REMAINING
        return _Result([(len(self._missing()),)])

    def cursor(self) -> Self:
        return self

    def executemany(self, statement: str, rows: list[tuple]) -> None:
        assert statement == gemini_backfill._STORE
        for literal, row_id in rows:
            self.rows[row_id] = (self.rows[row_id][0], literal)
            self.updates.append(row_id)


def _install(monkeypatch, table: _Table) -> None:
    monkeypatch.setattr(pgvector_store, "connect", lambda: table)


@pytest.mark.unit
def test_backfill_fills_only_missing_rows_in_batches_and_paces_each_batch(monkeypatch):
    table = _Table(["a", "b", "c", "d", "e"], filled={2})
    _install(monkeypatch, table)
    batches: list[list[str]] = []
    monkeypatch.setattr(
        gemini_embeddings, "embed_documents", lambda texts: batches.append(texts) or [[0.5] for _ in texts]
    )
    sleeps: list[float] = []

    result = gemini_backfill.backfill(batch_size=2, sleep=sleeps.append)

    assert batches == [["a", "c"], ["d", "e"]]
    assert table.updates == [1, 3, 4, 5]  # row 2 already had a vector
    assert table.rows[1] == ("a", "[0.500000]")
    assert result == gemini_backfill.BackfillResult(filled=4, remaining=0)
    assert sleeps == [gemini_backfill.pace_seconds(b) for b in batches]


@pytest.mark.unit
def test_backfill_stops_on_the_quota_and_a_rerun_continues(monkeypatch):
    table = _Table(["a", "b", "c"])
    _install(monkeypatch, table)
    calls = iter([[[0.5]], _QuotaError("429 RESOURCE_EXHAUSTED")])

    def embed(_texts):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gemini_embeddings, "embed_documents", embed)

    stopped = gemini_backfill.backfill(batch_size=1, sleep=lambda _s: None)

    assert (stopped.filled, stopped.remaining, stopped.quota_stop) == (1, 2, True)

    monkeypatch.setattr(gemini_embeddings, "embed_documents", lambda texts: [[0.5] for _ in texts])
    resumed = gemini_backfill.backfill(batch_size=1, sleep=lambda _s: None)

    assert (resumed.filled, resumed.remaining) == (2, 0)
    assert table.updates == [1, 2, 3]


@pytest.mark.unit
def test_pacing_honours_whichever_per_minute_budget_is_tighter():
    many_short = ["x"] * gemini_backfill.TEXTS_PER_MINUTE
    one_long = ["x" * gemini_backfill.TOKENS_PER_MINUTE * 4]

    assert gemini_backfill.pace_seconds(many_short) == pytest.approx(60)
    assert gemini_backfill.pace_seconds(one_long) == pytest.approx(60)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("enabled", "key", "printed"),
    [(False, "k", "DATABASE_URL is not set"), (True, " ", "GOOGLE_API_KEY is not set")],
)
def test_main_refuses_without_a_database_or_key(monkeypatch, capsys, enabled, key, printed):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", enabled)
    monkeypatch.setenv("GOOGLE_API_KEY", key)
    monkeypatch.setattr(gemini_backfill, "backfill", pytest.fail)

    assert gemini_backfill.main() == 1
    assert printed in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error", "code", "printed"),
    [
        (None, 0, "3 filled, 2 remaining."),
        (_QuotaError("spent"), 0, "Rerun later to continue."),
        (RuntimeError("401 bad key"), 1, "Stopped on an error: 401 bad key"),
    ],
)
def test_main_exit_code_separates_a_quota_stop_from_a_failure(monkeypatch, capsys, error, code, printed):
    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", True)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    result = gemini_backfill.BackfillResult(filled=3, remaining=2, error=error)
    monkeypatch.setattr(gemini_backfill, "backfill", lambda: result)

    assert gemini_backfill.main() == code
    assert printed in capsys.readouterr().out
