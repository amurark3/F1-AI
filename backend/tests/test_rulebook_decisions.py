"""Tests for app.services.rulebook_decisions: stewards' decisions matched to a question.

Matching runs over the real 2026 Mexico City GP documents (R19) held in a file
store. A decision shown against a regulation passage must be a decided, standing
document whose article is the passage's; a decision found by words must share
at least half the question's words.
"""

from __future__ import annotations

from dataclasses import replace
import re

from fia_documents_support import MEXICO_2026, held, hold, mexico
import pytest

from app.data.fia_documents import store
from app.data.fia_documents.store import FiaStoreError
from app.services import rulebook_decisions as rd
from app.utils.ttl_cache import TtlCache


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(rd, "_SEASONS", TtlCache())


@pytest.fixture
def r19(monkeypatch, tmp_path):
    return hold(monkeypatch, tmp_path)


def _numbers(result: dict) -> list[int]:
    return [item["number"] for item in result["items"]]


@pytest.mark.unit
def test_article_codes_reads_every_article_number_once_in_order():
    text = "B3.5.3 When deemed ... Article B3.4.2 or B3.4.3, Appendix B2, B3.5.3 again, section B3, 12.2.1"

    assert rd.article_codes(text) == ("B3.5.3", "B3.4.2", "B3.4.3")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("decision_article", "code", "expected"),
    [
        ("B3.5.3", "B3.5.3", True),
        ("B1.6.3a", "B1.6.3", True),
        ("B1.6.2b.i", "B1.6.2", True),
        ("B3.5.3", "B3.5", True),
        ("B1.62", "B1.6", False),
        ("B3.5", "B3.5.3", False),
        ("ISC 12.2.1.l", "B1.6.3", False),
        ("ISC Appendix L Chapter IV Article 2 d)", "B1.6.3", False),
    ],
)
def test_cites_matches_an_article_or_its_sub_articles_only(decision_article, code, expected):
    assert rd.cites(decision_article, code) is expected


@pytest.mark.unit
def test_a_passage_article_matches_exactly_the_decision_that_cites_it(r19):
    result = rd.matching(2026, [("B3.5.3",)], first_cite=4)

    assert (result["match"], result["status"], result["total"], result["events"]) == ("article", "matched", 1, 1)
    assert _numbers(result) == [65]
    item = result["items"][0]
    assert item["cite"] == 4
    assert item["matched"] == ["B3.5.3"]
    assert item["car"] == 30
    assert item["driver"] == "Liam Lawson"
    assert item["published"] == "01.11.26 19:22"
    assert item["url"].endswith("changes_made_during_parc_ferme.pdf")
    assert result["articles"] == ["B3.5.3"]


@pytest.mark.unit
def test_sub_article_citations_match_their_parent_passage_code(r19):
    result = rd.matching(2026, [("B1.6.3",)], first_cite=1)

    assert result["total"] == 5
    assert set(_numbers(result)) <= {18, 25, 42, 68, 71}
    assert len(result["items"]) == rd.DECISIONS_SHOWN


@pytest.mark.unit
def test_no_decision_matches_a_passage_that_cites_nothing_stewards_applied(r19):
    result = rd.matching(2026, [("B9.9.9",), ()], first_cite=4)

    assert (result["status"], result["total"], result["items"], result["events"]) == ("none", 0, [], 1)


@pytest.mark.unit
def test_summonses_and_isc_articles_are_never_matched(r19):
    summons_numbers = {
        int(title.split()[1]) for title in MEXICO_2026 if title.split(" - ")[1].lower().startswith("summons")
    }
    result = rd.matching(2026, [("B1.6.3", "B3.5.3", "B1.6.2", "B1.8.4")], first_cite=1)

    assert not summons_numbers & set(_numbers(result))
    assert all(article.startswith("B") for item in result["items"] for article in item["matched"])


@pytest.mark.unit
def test_documents_that_are_not_decided_standing_and_numbered_are_skipped(monkeypatch, tmp_path):
    keep = held(mexico(65)[0])
    withdrawn = replace(held(mexico(18)[0]), withdrawn="withdrawn")
    unread = replace(held(mexico(25)[0]), text=None)
    garbled = replace(held(mexico(42)[0]), text="nothing a parser could read")
    title, text = mexico(68)
    numberless = replace(
        held(title), title=title.removeprefix("Doc 68 - "), text=re.sub(r"Document\s+\d+", "Document", text)
    )
    hold(monkeypatch, tmp_path, [keep, withdrawn, unread, garbled, numberless])

    result = rd.matching(2026, [("B3.5.3", "B1.6.3")], first_cite=1)

    assert _numbers(result) == [65]


@pytest.mark.unit
def test_a_document_without_its_own_number_takes_the_one_in_its_title(monkeypatch, tmp_path):
    title, text = mexico(65)
    unnumbered = replace(held(title), text=re.sub(r"Document\s+\d+", "Document", text))
    hold(monkeypatch, tmp_path, [unnumbered])

    assert _numbers(rd.matching(2026, [("B3.5.3",)], first_cite=1)) == [65]


@pytest.mark.unit
def test_decisions_are_ordered_by_closest_passage_then_newest(monkeypatch, tmp_path):
    old = replace(held(mexico(18)[0]), published="01.11.26 08:00")
    new = replace(held(mexico(25)[0]), published="01.11.26 20:00")
    unparsed = replace(held(mexico(42)[0]), published="whenever")
    hold(monkeypatch, tmp_path, [old, new, unparsed, held(mexico(65)[0])])

    first_passage = rd.matching(2026, [("B1.6.3",), ("B3.5.3",)], first_cite=1)
    second_passage_first = rd.matching(2026, [("B3.5.3",), ("B1.6.3",)], first_cite=1)

    assert _numbers(first_passage) == [25, 18, 42]
    assert first_passage["total"] == 4
    assert _numbers(second_passage_first)[0] == 65


@pytest.mark.unit
def test_zero_events_is_reported_not_hidden(monkeypatch, tmp_path):
    hold(monkeypatch, tmp_path, [])

    assert rd.matching(2026, [("B3.5.3",)], first_cite=1)["events"] == 0
    assert rd.keyword_matching(2026, "pit lane")["events"] == 0


@pytest.mark.unit
def test_the_season_is_read_once_inside_its_lifetime(r19, monkeypatch):
    reads: list[int] = []
    real = store.events

    def counting(year):
        reads.append(year)
        return real(year)

    monkeypatch.setattr(store, "events", counting)

    rd.matching(2026, [("B3.5.3",)], first_cite=1)
    rd.keyword_matching(2026, "pit lane")

    assert reads == [2026]


@pytest.mark.unit
def test_a_failed_read_is_reported_and_not_kept(r19, monkeypatch):
    real = store.events
    monkeypatch.setattr(store, "events", lambda year: (_ for _ in ()).throw(FiaStoreError("down")))

    down = rd.matching(2026, [("B3.5.3",)], first_cite=1)
    with pytest.raises(FiaStoreError):
        rd.keyword_matching(2026, "pit lane")
    monkeypatch.setattr(store, "events", real)

    assert (down["status"], down["events"], down["total"], down["items"]) == ("unavailable", None, 0, [])
    assert rd.matching(2026, [("B3.5.3",)], first_cite=1)["status"] == "matched"


@pytest.mark.unit
def test_search_words_folds_accents_expands_pu_and_drops_noise():
    assert rd.search_words("Café PU limits, the Lap-times!") == ("cafe", "power", "unit", "limit", "lap", "time")
    assert rd.search_words("a B 12 pass points") == ("12", "pass", "point")
    assert rd.search_words("grid grid GRID") == ("grid",)
    assert rd.search_words("the of and") == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("question", "words", "first"),
    [
        ("When is a driver required to start from the pit lane?", ("required", "start", "pit", "lane"), {65}),
        ("What is a power-unit grid penalty?", ("power", "unit", "grid", "penalty"), {17}),
        ("How do penalty points work?", ("penalty", "point"), {84, 85}),
        ("What counts as track limits?", ("track", "limit"), {69, 76}),
    ],
)
def test_the_quick_questions_find_their_r19_decisions_by_words(r19, question, words, first):
    result = rd.keyword_matching(2026, question)

    assert (result["match"], result["status"], result["articles"]) == ("keyword", "matched", [])
    assert tuple(result["words"]) == words
    assert set(_numbers(result)) >= first if len(first) > 1 else _numbers(result)[0] in first
    assert [item["cite"] for item in result["items"]] == [1, 2, 3][: len(result["items"])]
    assert all(set(item["matched"]) <= set(words) for item in result["items"])


@pytest.mark.unit
def test_pit_lane_speeding_decisions_follow_the_pit_lane_start(r19):
    result = rd.keyword_matching(2026, "When is a driver required to start from the pit lane?")

    assert _numbers(result)[0] == 65
    assert [len(item["matched"]) for item in result["items"]] == [4, 2, 2]


@pytest.mark.unit
def test_a_decision_needs_at_least_half_the_question_words(r19):
    one_word = rd.keyword_matching(2026, "pit")
    three_of_five = rd.keyword_matching(2026, "pit lane zebra giraffe walrus")

    assert one_word["total"] > 0
    assert three_of_five["total"] == 0


@pytest.mark.unit
def test_a_question_without_search_words_matches_nothing(r19):
    result = rd.keyword_matching(2026, "what is the rule?")

    assert (result["status"], result["words"], result["total"], result["items"]) == ("none", [], 0, [])


@pytest.mark.unit
def test_keyword_ranking_is_by_shared_words_then_newest(monkeypatch, tmp_path):
    older = replace(held(mexico(68)[0]), published="01.11.26 08:00")
    newer = replace(held(mexico(71)[0]), published="01.11.26 20:00")
    hold(monkeypatch, tmp_path, [older, newer, held(mexico(65)[0])])

    result = rd.keyword_matching(2026, "When is a driver required to start from the pit lane?")

    assert _numbers(result) == [65, 71, 68]
