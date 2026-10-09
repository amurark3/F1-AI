"""Tests for app.api.tools.reference — the FIA rulebook and read-only SQL.

The two tools the model uses when it needs a source rather than a result. The
risks are citation-shaped and trust-shaped:

* **The right season's regulations are searched.** The rules change every year,
  and an unqualified question must not silently answer from last year's book.
  The year only rolls forward once the season is over *and* the new text exists.
* **A passage is returned with a citation attached.** The header instructs the
  model to cite; a passage with a wrong page number is worse than no citation.
* **A rejected query is distinguishable from a broken one.** ``Query rejected``
  means the model wrote something disallowed and should rewrite it; ``Query
  failed`` means the SQL was allowed but wrong.

pgvector and the reranker are mocked at their import sites, and the f1db query
layer at the boundary the tool calls.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.tools import reference as reference_module
from app.api.tools.reference import consult_rulebook, query_f1_database
from app.data.f1db_query import QueryValidationError
from app.rag import pgvector_store


class _FakeDoc:
    """A LangChain Document as far as these tools are concerned."""

    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


def _install_rulebook(monkeypatch, *, enabled: bool = True, hits=None) -> list[dict]:
    """Patch the pgvector search and bypass the cross-encoder rerank."""
    calls: list[dict] = []

    def _search(query, year, *, category=None, k=24):
        calls.append({"query": query, "year": year, "k": k})
        if isinstance(hits, Exception):
            raise hits
        return list(hits or [])

    monkeypatch.setattr(pgvector_store, "RULEBOOK_ENABLED", enabled)
    monkeypatch.setattr(pgvector_store, "search", _search)
    # The reranker loads a torch model; order is not what these tests are about.
    monkeypatch.setattr(reference_module, "rerank", lambda query, docs, top_k: docs[:top_k])
    return calls


def _freeze_now(monkeypatch, moment: datetime) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Honour the requested zone as the real classmethod does — the tool
            # asks for UTC, and the month/day it reads depend on getting it.
            return moment.astimezone(tz) if tz else moment

    monkeypatch.setattr(reference_module, "datetime", _FrozenDatetime)


# ---------------------------------------------------------------------------
# consult_rulebook — year resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_explicit_year_is_searched_as_given(monkeypatch):
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "pit lane speed limit", "year": 2023})

    assert calls[0]["year"] == 2023


@pytest.mark.unit
def test_mid_season_an_unqualified_question_uses_the_current_regulations(monkeypatch):
    _freeze_now(monkeypatch, datetime(2026, 7, 4, tzinfo=timezone.utc))
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "parc fermé"})

    assert calls[0]["year"] == 2026


@pytest.mark.unit
def test_after_the_season_ends_next_years_regulations_are_used_once_they_exist(monkeypatch, tmp_path):
    """In late December the current book is history; the new one is what applies."""
    _freeze_now(monkeypatch, datetime(2026, 12, 20, tzinfo=timezone.utc))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw" / "2027").mkdir(parents=True)
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "engine allocation"})

    assert calls[0]["year"] == 2027


@pytest.mark.unit
def test_next_years_regulations_are_not_used_before_they_are_ingested(monkeypatch, tmp_path):
    """Rolling forward to a directory that does not exist would find nothing at all."""
    _freeze_now(monkeypatch, datetime(2026, 12, 20, tzinfo=timezone.utc))
    monkeypatch.chdir(tmp_path)
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "engine allocation"})

    assert calls[0]["year"] == 2026


@pytest.mark.unit
def test_early_december_is_still_the_current_season(monkeypatch, tmp_path):
    """The season is only treated as over after the 10th; races run before it."""
    _freeze_now(monkeypatch, datetime(2026, 12, 5, tzinfo=timezone.utc))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw" / "2027").mkdir(parents=True)
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "engine allocation"})

    assert calls[0]["year"] == 2026


# ---------------------------------------------------------------------------
# consult_rulebook — retrieval and citation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_search_over_fetches_before_reranking(monkeypatch):
    """Similarity is recall-oriented; the reranker needs candidates to reorder."""
    calls = _install_rulebook(monkeypatch, hits=[])

    consult_rulebook.invoke({"query": "safety car", "year": 2026})

    assert calls[0]["k"] == reference_module.RULEBOOK_TOP_K * 4


@pytest.mark.unit
def test_a_passage_is_returned_with_a_citable_source_line(monkeypatch):
    _install_rulebook(
        monkeypatch,
        hits=[
            _FakeDoc(
                "The pit lane speed limit is 80 km/h.",
                {"type": "Sporting", "filename": "2026_sporting_regs.pdf", "page": 33},
            )
        ],
    )

    answer = consult_rulebook.invoke({"query": "pit lane speed limit", "year": 2026})

    assert answer.startswith(
        "Found 1 relevant passage(s) in the 2026 FIA regulations. Cite the Source line(s) in your answer.\n"
    )
    # PyPDFLoader pages are 0-indexed; a citation must point at the printed page.
    assert "**Source:** Sporting Regulations 2026 (2026_sporting_regs.pdf, p.34)" in answer
    assert "**Excerpt:** ...The pit lane speed limit is 80 km/h...." in answer


@pytest.mark.unit
def test_newlines_inside_a_pdf_passage_are_flattened(monkeypatch):
    """PDF extraction breaks sentences mid-line; the raw form reads as fragments."""
    _install_rulebook(
        monkeypatch,
        hits=[_FakeDoc("The pit lane\nspeed limit\nis 80 km/h.", {"filename": "regs.pdf", "page": 0})],
    )

    answer = consult_rulebook.invoke({"query": "pit lane", "year": 2026})

    assert "The pit lane speed limit is 80 km/h." in answer


@pytest.mark.unit
def test_a_passage_missing_its_metadata_still_produces_a_citation(monkeypatch):
    """Ingest gaps must degrade to a vague citation, not a KeyError."""
    _install_rulebook(monkeypatch, hits=[_FakeDoc("Some regulation text.", {})])

    answer = consult_rulebook.invoke({"query": "anything", "year": 2026})

    assert "**Source:** Regulatory Regulations 2026 (Unknown PDF)" in answer


@pytest.mark.unit
def test_a_long_passage_is_truncated(monkeypatch):
    """The whole article would crowd out the other passages in the model's context."""
    _install_rulebook(monkeypatch, hits=[_FakeDoc("x" * 2000, {"filename": "regs.pdf"})])

    answer = consult_rulebook.invoke({"query": "anything", "year": 2026})

    assert "x" * 700 in answer
    assert "x" * 701 not in answer


@pytest.mark.unit
def test_a_question_with_no_matching_regulation_says_so(monkeypatch):
    _install_rulebook(monkeypatch, hits=[])

    assert consult_rulebook.invoke({"query": "tyre warmers", "year": 2026}) == (
        "No regulations found for 'tyre warmers' in the 2026 rulebook."
    )


@pytest.mark.unit
def test_an_unconfigured_rulebook_names_the_missing_setting(monkeypatch):
    """Without DATABASE_URL there are no embeddings; "not found" would be misleading."""
    _install_rulebook(monkeypatch, enabled=False)

    assert consult_rulebook.invoke({"query": "anything", "year": 2026}) == (
        "Rulebook search is unavailable — DATABASE_URL is not configured."
    )


@pytest.mark.unit
def test_a_rulebook_failure_is_reported_rather_than_raised(monkeypatch):
    _install_rulebook(monkeypatch, hits=ConnectionError("pgvector unreachable"))

    assert consult_rulebook.invoke({"query": "anything", "year": 2026}) == (
        "Rulebook lookup failed: pgvector unreachable"
    )


# ---------------------------------------------------------------------------
# query_f1_database
# ---------------------------------------------------------------------------


def _install_query(monkeypatch, result):
    def _run(sql):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(reference_module, "run_readonly_query", _run)


@pytest.mark.unit
def test_rows_are_rendered_as_a_markdown_table(monkeypatch):
    _install_query(
        monkeypatch,
        {
            "columns": ["driver", "wins"],
            "rows": [{"driver": "Hamilton", "wins": 105}, {"driver": "Schumacher", "wins": 91}],
            "row_count": 2,
            "sql": "SELECT driver, wins FROM x LIMIT 100",
        },
    )

    answer = query_f1_database.invoke({"sql": "SELECT driver, wins FROM x"})

    assert answer.splitlines() == [
        "Returned 2 row(s).",
        "",
        "| driver | wins |",
        "| --- | --- |",
        "| Hamilton | 105 |",
        "| Schumacher | 91 |",
    ]


@pytest.mark.unit
def test_a_null_cell_renders_as_an_empty_column_rather_than_shifting_the_row(monkeypatch):
    """A row missing a key would otherwise misalign every column after it."""
    _install_query(
        monkeypatch,
        {
            "columns": ["driver", "wins"],
            "rows": [{"driver": "Hamilton"}],
            "row_count": 1,
            "sql": "SELECT driver, wins FROM x",
        },
    )

    assert "| Hamilton |  |" in query_f1_database.invoke({"sql": "SELECT driver, wins FROM x"})


@pytest.mark.unit
def test_an_empty_result_shows_the_sql_that_was_actually_run(monkeypatch):
    """The executed SQL carries the injected LIMIT, so it is what the model must debug."""
    _install_query(
        monkeypatch,
        {"columns": ["x"], "rows": [], "row_count": 0, "sql": "SELECT x FROM y\nLIMIT 200"},
    )

    answer = query_f1_database.invoke({"sql": "SELECT x FROM y"})

    assert answer == "Query ran successfully but returned no rows.\n\nSQL:\nSELECT x FROM y\nLIMIT 200"


@pytest.mark.unit
def test_a_disallowed_query_is_rejected_with_the_reason(monkeypatch):
    """A rejection is the model's cue to rewrite, not to report a database outage."""
    _install_query(monkeypatch, QueryValidationError("only SELECT statements are permitted"))

    assert query_f1_database.invoke({"sql": "DROP TABLE races"}) == (
        "Query rejected: only SELECT statements are permitted"
    )


@pytest.mark.unit
def test_a_broken_query_is_reported_with_a_hint_to_check_the_schema(monkeypatch):
    _install_query(monkeypatch, RuntimeError("no such column: drivr"))

    assert query_f1_database.invoke({"sql": "SELECT drivr FROM races"}) == (
        "Query failed: no such column: drivr. Check table/column names against the schema and try again."
    )


@pytest.mark.unit
def test_the_schema_is_appended_to_the_tool_description():
    """The model writes SQL from the description alone; without it, it guesses names."""
    assert "SCHEMA:" in query_f1_database.description
    assert "TABLES (key columns):" in query_f1_database.description
    assert "race(id, year, round" in query_f1_database.description
