"""Tests for app.services.rulebook_text: the computed Rulebook text.

Every sentence is built from the evidence alone, in the markup the model also
writes ([n] source markers, **bold**), so the page has one renderer.
"""

from __future__ import annotations

import pytest

from app.services import rulebook_text as text


def _article(cite=1, codes=("B3.5.3", "B3.5.4"), page=29) -> dict:
    return {"cite": cite, "codes": list(codes), "source": "Section B · Sporting", "page": page}


def _item(cite=4, number=65) -> dict:
    return {
        "cite": cite,
        "number": number,
        "event": "Mexico City Grand Prix",
        "car": 30,
        "driver": "Liam Lawson",
        "decision": "Required to start the Race from the pit lane.",
    }


def _decisions(status="matched", items=(), total=None, events=19, articles=(), words=()) -> dict:
    return {
        "status": status,
        "items": list(items),
        "total": len(items) if total is None else total,
        "events": events,
        "articles": list(articles),
        "words": list(words),
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("codes", "label"),
    [
        ([], None),
        (["B3.5.3"], "Article B3.5.3"),
        (["B3.5.3", "B3.5.4"], "Articles B3.5.3 and B3.5.4"),
        (["A1.1", "A1.2", "A1.3"], "Articles A1.1, A1.2 and A1.3"),
        (["A1.1", "A1.2", "A1.3", "A1.4", "A1.5"], "Articles A1.1, A1.2, A1.3 and 2 more"),
    ],
)
def test_article_label(codes, label):
    assert text.article_label(codes) == label


@pytest.mark.unit
def test_the_closest_rule_leads_with_its_articles_and_where_they_are():
    summary = text.computed_summary(
        2026,
        [_article()],
        _decisions("matched", [_item()], articles=["B3.5.3"], events=1),
    )

    assert summary["heading"] == "The closest rule: Articles B3.5.3 and B3.5.4"
    assert summary["paragraph"] == (
        "The closest passage in the FIA 2026 F1 Regulations is **Articles B3.5.3 and B3.5.4 "
        "(Section B · Sporting, page 29)** [1]. The stewards cited Article B3.5.3 in 1 decision from the "
        "1 2026 event collected. At the Mexico City Grand Prix, document 65, car 30 (Liam Lawson): "
        "**“Required to start the Race from the pit lane.”** [4]"
    )


@pytest.mark.unit
def test_related_passages_and_a_cut_off_decision_list_are_named():
    articles = [_article(), _article(2), _article(3)]
    summary = text.computed_summary(
        2026, articles, _decisions("matched", [_item()], total=5, articles=["B3.5.3", "B3.5.4"])
    )

    assert " Related passages: [2] [3]." in summary["paragraph"]
    assert "in 5 decisions from the 19 2026 events collected. 1 of them are cited below." in summary["paragraph"]


@pytest.mark.unit
def test_a_passage_without_an_article_number_is_named_by_its_place():
    bare = _article(codes=(), page=None)
    summary = text.computed_summary(2026, [bare], _decisions("none"))
    no_driver = {**_item(), "driver": None}
    matched = text.computed_summary(2026, [bare], _decisions("matched", [no_driver], articles=["B1.1"]))

    assert summary["heading"] == "The closest passage: Section B · Sporting"
    assert "is **Section B · Sporting** [1]." in summary["paragraph"]
    assert summary["paragraph"].endswith(
        "These passages name no article number, so no stewards' decision can be matched to them."
    )
    assert "car 30: **" in matched["paragraph"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("decisions", "ending"),
    [
        (
            _decisions("unavailable", events=None),
            "The stewards' decisions could not be read just now, so none is cited.",
        ),
        (_decisions("none", events=0), "No 2026 stewards' decisions have been collected yet."),
        (
            _decisions("none", events=1),
            "None of the stewards' decisions collected from 1 2026 event cites Articles B3.5.3 and B3.5.4.",
        ),
        (
            _decisions("none", events=19),
            "None of the stewards' decisions collected from 19 2026 events cites Articles B3.5.3 and B3.5.4.",
        ),
    ],
)
def test_the_second_sentence_says_why_no_decision_is_cited(decisions, ending):
    assert text.computed_summary(2026, [_article()], decisions)["paragraph"].endswith(ending)


@pytest.mark.unit
def test_keyword_summary_with_matches_says_they_are_not_article_matches():
    decisions = _decisions("matched", [_item(1)], total=6, words=["required", "start", "pit", "lane"])

    summary = text.keyword_summary(2026, decisions)

    assert summary["heading"] == "6 stewards' decisions share words with the question"
    assert summary["paragraph"] == (
        "Found by the words required, start, pit, lane in the stewards' decisions collected from 19 2026 events, "
        "not matched to an article of the regulations. The closest: at the Mexico City Grand Prix, document 65, "
        "car 30 (Liam Lawson): **“Required to start the Race from the pit lane.”** [1] 1 of 6 are cited below."
    )
    assert (summary["written_by"], summary["why"]) == ("computed", None)


@pytest.mark.unit
def test_keyword_summary_for_one_match_uses_the_singular():
    summary = text.keyword_summary(2026, _decisions("matched", [_item(1)], words=["pit"], events=1))

    assert summary["heading"] == "1 stewards' decision shares words with the question"
    assert "1 2026 event," in summary["paragraph"]
    assert "cited below" not in summary["paragraph"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("decisions", "paragraph"),
    [
        (_decisions("none", words=[]), "The question has no word to search the stewards' decisions by."),
        (_decisions("none", words=["pit"], events=0), "No 2026 stewards' decisions have been collected yet."),
        (
            _decisions("none", words=["pit", "lane"]),
            "None of the stewards' decisions collected from 19 2026 events mentions pit, lane.",
        ),
    ],
)
def test_keyword_summary_without_matches(decisions, paragraph):
    summary = text.keyword_summary(2026, decisions)

    assert summary["heading"] == "No stewards' decision shares words with the question"
    assert summary["paragraph"] == paragraph
