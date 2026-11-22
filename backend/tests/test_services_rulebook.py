"""Tests for app.services.rulebook: the Rulebook page's search.

The risk is a confident answer from a search that never ran. Every degraded
path (no index, no embedding model, a failing search, an empty index) must say
which, search the stewards' decisions by words instead, and never put exception
text or an invented citation in front of the reader.

The pgvector and cross-encoder boundaries are faked; the stewards' decisions are
the real R19 documents in a file store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from fia_documents_support import hold
import pytest

from app.data.fia_documents import store
from app.data.fia_documents.store import FiaStoreError
from app.services import rulebook, rulebook_decisions
from app.utils.ttl_cache import TtlCache

QUESTION = "When is a driver required to start from the pit lane?"
# Section B, page 29 (0-indexed 28) of the 2026 Sporting Regulations.
PARC_FERME = (
    "B3.5.3 When deemed to be in parc fermé, other than when the Cars are sealed in accordance with "
    "Article B3.4.2 or B3.4.3, only the work listed in Appendix B2 may be carried out."
)
SPORTING_FILE = "FIA 2026 F1 Regulations - Section B [Sporting] - Iss 04 - 2025-12-10.pdf"


@dataclass(frozen=True)
class _Hit:
    """Shape of a ``RulebookHit`` as the reranker hands it back."""

    page_content: str
    metadata: dict | None = field(default=None)


def _sporting(text: str = PARC_FERME, page: int | None = 28) -> _Hit:
    return _Hit(text, {"type": "Sporting", "filename": SPORTING_FILE, "page": page, "source_year": "2026"})


@pytest.fixture(autouse=True)
def fresh_season_cache(monkeypatch):
    monkeypatch.setattr(rulebook_decisions, "_SEASONS", TtlCache())


@pytest.fixture
def enabled(monkeypatch):
    """Turn on both gates so the retrieval path is the one under test."""
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", True)
    monkeypatch.setattr(rulebook, "ENABLE_LOCAL_MODELS", True)


@pytest.fixture
def summary(monkeypatch):
    """Replace the model-written text with a marker, recording what it was given."""
    seen: list[tuple] = []

    def write(query, year, articles, decisions):
        seen.append((query, year, articles, decisions))
        return {"heading": "h", "paragraph": "p", "written_by": "ai", "why": None}

    monkeypatch.setattr(rulebook.rulebook_answer, "write_summary", write)
    return seen


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
        (datetime(2026, 6, 1, tzinfo=UTC), True, 2026),
        # December, but before the roll-over date.
        (datetime(2026, 12, 5, tzinfo=UTC), True, 2026),
        # Late December with next year's PDFs on disk: roll forward.
        (datetime(2026, 12, 20, tzinfo=UTC), True, 2027),
        # Late December but nothing ingested yet: stay put rather than search
        # a corpus that does not exist.
        (datetime(2026, 12, 20, tzinfo=UTC), False, 2026),
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
def test_a_blank_question_is_unavailable_and_searches_nothing(monkeypatch):
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: pytest.fail("a blank question must not search"))

    result = rulebook.search_rulebook("   ", year=2026)

    assert (result["status"], result["decisions"], result["summary"], result["articles"]) == (
        "unavailable",
        None,
        None,
        [],
    )
    assert result["reason"] == "Enter a question to search the regulations."


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rulebook_on", "models_on", "reason"),
    [
        (False, True, "The regulation index isn't set up on this server, so the regulations were not searched."),
        (
            True,
            False,
            "Regulation search is off on this server: it needs a model this server doesn't have the memory to run. "
            "The regulations were not searched.",
        ),
    ],
)
def test_a_switched_off_index_falls_back_to_keyword_matches(
    monkeypatch, tmp_path, summary, rulebook_on, models_on, reason
):
    hold(monkeypatch, tmp_path)
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", rulebook_on)
    monkeypatch.setattr(rulebook, "ENABLE_LOCAL_MODELS", models_on)
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: pytest.fail("the index is off"))

    result = rulebook.search_rulebook(f"  {QUESTION}  ", year=2026)

    assert (result["status"], result["reason"], result["articles"], result["query"]) == (
        "keyword",
        reason,
        [],
        QUESTION,
    )
    assert result["decisions"]["match"] == "keyword"
    assert result["decisions"]["items"][0]["number"] == 65
    assert summary[0][2] == []


@pytest.mark.unit
def test_a_failing_search_reports_a_fixed_reason_without_the_exception_text(enabled, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("password=hunter2 connection refused")

    monkeypatch.setattr(rulebook, "rulebook_search", broken)

    result = rulebook.search_rulebook(QUESTION, year=2026)

    assert result["status"] == "keyword"
    assert result["reason"] == "The regulation search failed, so the regulations were not searched. Try again shortly."
    assert "hunter2" not in str(result)


@pytest.mark.unit
def test_a_failing_rerank_reports_the_same_fixed_reason(enabled, monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path)
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: [_sporting()])

    def broken(*args):
        raise RuntimeError("torch exploded")

    monkeypatch.setattr(rulebook, "rerank", broken)

    result = rulebook.search_rulebook(QUESTION, year=2026)

    assert result["reason"].startswith("The regulation search failed")


@pytest.mark.unit
@pytest.mark.parametrize("candidates", [[], None])
def test_an_empty_index_says_the_year_is_not_indexed(enabled, monkeypatch, tmp_path, candidates):
    hold(monkeypatch, tmp_path)
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: candidates or [])
    monkeypatch.setattr(rulebook, "rerank", lambda q, c, k: c[:k])

    result = rulebook.search_rulebook(QUESTION, year=2026)

    assert result["status"] == "keyword"
    assert result["reason"] == "The FIA 2026 F1 Regulations aren't in the search index yet."


@pytest.mark.unit
def test_keyword_mode_with_an_unreadable_store_is_unavailable_with_both_reasons(monkeypatch, summary):
    monkeypatch.setattr(rulebook, "RULEBOOK_ENABLED", False)
    monkeypatch.setattr(store, "events", lambda year: (_ for _ in ()).throw(FiaStoreError("down")))

    result = rulebook.search_rulebook(QUESTION, year=2026)

    assert (result["status"], result["decisions"], result["summary"]) == ("unavailable", None, None)
    assert result["reason"] == (
        "The regulation index isn't set up on this server, so the regulations were not searched. "
        "The stewards' decisions could not be read either."
    )
    assert summary == []


@pytest.mark.unit
def test_an_answered_search_quotes_three_passages_and_matches_decisions_by_article(
    enabled, monkeypatch, tmp_path, summary
):
    hold(monkeypatch, tmp_path)
    asked: list[tuple] = []

    def search(query, year, **kwargs):
        asked.append((query, year, kwargs))
        return [_sporting(), _sporting("a\n\n  b  c", page=None), _sporting("nothing numbered"), _sporting("fourth")]

    monkeypatch.setattr(rulebook, "rulebook_search", search)
    monkeypatch.setattr(rulebook, "rerank", lambda q, c, k: c[:k])

    result = rulebook.search_rulebook(QUESTION, "Sporting", 2026)

    assert asked == [(QUESTION, 2026, {"category": "Sporting", "k": 24})]
    assert (result["status"], result["reason"], result["year"]) == ("answered", None, 2026)
    first, second, third = result["articles"]
    assert (first["cite"], first["codes"], first["page"]) == (1, ["B3.5.3", "B3.4.2", "B3.4.3"], 29)
    assert first["source"] == "Section B · Sporting"
    assert first["document"] == SPORTING_FILE
    assert (second["excerpt"], second["page"], second["codes"]) == ("a b c", None, [])
    assert third["cite"] == 3
    assert result["decisions"]["match"] == "article"
    assert [item["number"] for item in result["decisions"]["items"]] == [65]
    assert result["decisions"]["items"][0]["cite"] == 4
    assert result["summary"]["written_by"] == "ai"
    assert summary[0][:2] == (QUESTION, 2026)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("metadata", "source"),
    [
        ({"filename": "FIA 2025 F1 Regulations - Section C [Technical] - Iss 01.pdf"}, "Section C · Technical"),
        ({"filename": "old_rules.pdf", "type": "Financial"}, "Financial Regulations"),
        ({"filename": "old_rules.pdf"}, "Regulatory Regulations"),
        ({}, "Regulatory Regulations"),
    ],
)
def test_the_source_names_the_section_or_falls_back_to_the_document_type(metadata, source):
    assert rulebook._source(metadata) == source
    assert rulebook._article(1, _Hit("x", metadata or None))["source"] == source


@pytest.mark.unit
def test_an_article_without_a_filename_is_not_given_an_invented_one():
    assert rulebook._article(1, _Hit("x", None))["document"] == "Unknown regulation PDF"


@pytest.mark.unit
def test_the_store_failing_in_answered_mode_still_answers_with_the_passages(enabled, monkeypatch, summary):
    monkeypatch.setattr(store, "events", lambda year: (_ for _ in ()).throw(FiaStoreError("down")))
    monkeypatch.setattr(rulebook, "rulebook_search", lambda *a, **k: [_sporting()])
    monkeypatch.setattr(rulebook, "rerank", lambda q, c, k: c[:k])

    result = rulebook.search_rulebook(QUESTION, year=2026)

    assert result["status"] == "answered"
    assert result["decisions"]["status"] == "unavailable"
