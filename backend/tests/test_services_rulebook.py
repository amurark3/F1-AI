"""Tests for app.services.rulebook — cited FIA regulation search.

The risk here is a *confident uncited answer*. Every degraded path — no vector
store, no embedding model, an unreachable database, an empty query — must come
back tagged ``source="fallback"`` with an explicit reason, never as a plausible
"the regulations do not cover that" verdict from a search that never ran. The
fallback's placeholder citation exists so the UI cannot render an answer with
no provenance attached.

The pgvector and cross-encoder boundaries are faked; neither torch nor a
database connection is involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from app.services import rulebook


@dataclass(frozen=True)
class _Hit:
    """Shape of a ``RulebookHit`` as the reranker hands it back."""

    page_content: str
    metadata: dict | None = field(default=None)


@pytest.fixture
def enabled(monkeypatch):
    """Turn on both gates so the retrieval path is the one under test."""
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(rulebook, "ENABLE_LOCAL_MODELS", True)


def _freeze_clock(monkeypatch, moment: datetime) -> None:
    class _FrozenDatetime:
        @staticmethod
        def now(tz=None):
            return moment.astimezone(tz) if tz else moment

    monkeypatch.setattr(rulebook, "datetime", _FrozenDatetime)


@pytest.mark.unit
def test_an_explicit_year_is_never_second_guessed():
    assert rulebook.resolve_rulebook_year(2021) == 2021


@pytest.mark.unit
@pytest.mark.parametrize(
    ("moment", "next_season_ingested", "expected"),
    [
        # Mid-season: always the running season.
        (datetime(2026, 6, 1, tzinfo=timezone.utc), True, 2026),
        # December, but before the roll-over date.
        (datetime(2026, 12, 5, tzinfo=timezone.utc), True, 2026),
        # Late December with next year's PDFs on disk — roll forward.
        (datetime(2026, 12, 20, tzinfo=timezone.utc), True, 2027),
        # Late December but nothing ingested yet — stay put rather than search
        # a corpus that does not exist.
        (datetime(2026, 12, 20, tzinfo=timezone.utc), False, 2026),
    ],
)
def test_year_rolls_forward_only_once_next_seasons_corpus_exists(
    monkeypatch, tmp_path, moment, next_season_ingested, expected
):
    _freeze_clock(monkeypatch, moment)
    monkeypatch.chdir(tmp_path)
    if next_season_ingested:
        (tmp_path / "data" / "raw" / "2027").mkdir(parents=True)

    assert rulebook.resolve_rulebook_year() == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stored_page", "expected"),
    [(0, "1"), (12, "13"), (4.0, "5"), (None, None), ("iv", None)],
)
def test_page_label_is_presented_one_indexed(stored_page, expected):
    # pgvector stores 0-indexed pages; a citation that says "page 0" is unusable.
    assert rulebook._page_label(stored_page) == expected


@pytest.mark.unit
def test_fallback_carries_a_placeholder_citation_and_refuses_to_answer():
    result = rulebook.fallback_rulebook_search("pit limit", category="Sporting", year=2025, error="boom")

    assert result["source"] == "fallback"
    assert result["error"] == "boom"
    assert "No uncited regulation answer was generated" in result["answer"]
    assert result["citations"] == [
        {
            "document": "Sporting",
            "year": "2025",
            "category": "Sporting",
            "page": None,
            "snippet": "Citation preview unavailable because the vector search could not answer this request.",
        }
    ]


@pytest.mark.unit
@pytest.mark.parametrize("category", [None, "All"])
def test_fallback_without_a_category_names_the_whole_corpus(category):
    result = rulebook.fallback_rulebook_search("q", category=category, year=2026)

    assert result["citations"][0]["document"] == "FIA regulations corpus"
    assert result["citations"][0]["category"] == "All"


@pytest.mark.unit
@pytest.mark.parametrize("query", ["", "   "])
def test_a_blank_query_asks_for_input_instead_of_searching(query, monkeypatch, enabled):
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: pytest.fail("must not search on a blank query"))

    result = rulebook.search_rulebook(query, year=2026)

    assert result["error"] == "Enter a regulation question before searching."


@pytest.mark.unit
def test_an_unconfigured_vector_store_says_so(monkeypatch):
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", False)

    result = rulebook.search_rulebook("pit lane speed", year=2026)

    assert result["source"] == "fallback"
    assert "DATABASE_URL unset" in result["error"]


@pytest.mark.unit
def test_disabled_local_models_report_the_real_reason_not_an_empty_corpus(monkeypatch):
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(rulebook, "ENABLE_LOCAL_MODELS", False)

    result = rulebook.search_rulebook("pit lane speed", year=2026)

    # Saying "no excerpts matched" here would assert the regulations are silent
    # on the question when the search never ran at all.
    assert "no excerpts matched" not in result["answer"]
    assert "does not have the memory to load" in result["error"]


@pytest.mark.unit
def test_a_store_outage_degrades_to_the_cited_fallback(monkeypatch, enabled):
    def explode(*_args, **_kwargs):
        raise ConnectionError("connection reset by peer")

    monkeypatch.setattr(rulebook, "rulebook_search", explode)

    result = rulebook.search_rulebook("safety car restart", category="Sporting", year=2026)

    assert result["source"] == "fallback"
    assert result["error"] == "connection reset by peer"


@pytest.mark.unit
def test_no_matching_excerpts_returns_an_empty_citation_list(monkeypatch, enabled):
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: [])
    monkeypatch.setattr(rulebook, "rerank", lambda *a, **k: [])

    result = rulebook.search_rulebook("hovercraft rules", category="Technical", year=2026)

    assert result["citations"] == []
    assert result["source"] == "pgvector-rag"
    assert "'hovercraft rules'" in result["answer"]
    assert "2026 Technical corpus" in result["answer"]


@pytest.mark.unit
def test_hits_become_citations_with_document_page_and_snippet(monkeypatch, enabled):
    requested: list[tuple] = []

    def fake_search(query, year, *, category, k):
        requested.append((query, year, category, k))
        return ["candidate"] * 4

    monkeypatch.setattr(rulebook, "rulebook_search", fake_search)
    monkeypatch.setattr(
        rulebook,
        "rerank",
        lambda *a, **k: [
            _Hit(
                "Pit lane speed\nis limited to 80 km/h.",
                {"filename": "sporting.pdf", "source_year": "2025", "type": "Sporting", "page": 41},
            ),
            _Hit("A second excerpt."),
        ],
    )

    result = rulebook.search_rulebook("pit lane speed", category="Sporting", year=2026)

    # Over-fetch by 4x before reranking, and the trimmed query is what is sent.
    assert requested == [("pit lane speed", 2026, "Sporting", rulebook.RULEBOOK_TOP_K * 4)]
    assert result["citations"][0] == {
        "document": "sporting.pdf",
        "year": "2025",
        "category": "Sporting",
        "page": "42",
        "snippet": "Pit lane speed is limited to 80 km/h.",
    }
    # A hit with no metadata still yields a citation rather than being dropped.
    assert result["citations"][1] == {
        "document": "Unknown regulation PDF",
        "year": "2026",
        "category": "Sporting",
        "page": None,
        "snippet": "A second excerpt.",
    }
    assert "Found 2 cited regulation excerpts" in result["answer"]


@pytest.mark.unit
def test_a_single_hit_is_described_in_the_singular(monkeypatch, enabled):
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: ["candidate"])
    monkeypatch.setattr(rulebook, "rerank", lambda *a, **k: [_Hit("Only one.", {})])

    result = rulebook.search_rulebook("q", year=2026)

    assert "Found 1 cited regulation excerpt " in result["answer"]


@pytest.mark.unit
def test_snippets_are_truncated_so_a_citation_cannot_become_the_answer(monkeypatch, enabled):
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: ["candidate"])
    monkeypatch.setattr(rulebook, "rerank", lambda *a, **k: [_Hit("x" * 2000, {})])

    result = rulebook.search_rulebook("q", year=2026)

    assert len(result["citations"][0]["snippet"]) == 700
