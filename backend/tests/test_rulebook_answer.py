"""Tests for app.services.rulebook_answer: the AI-written heading and paragraph, and its check.

No test reaches a live model: the engines are a fake. What matters is that a
reply naming anything the evidence does not hold is never shown, that a failed
model falls back to computed text labelled as such, and that a checked reply is
asked for once.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage
import pytest

from app.config import LLMProvider
from app.data.analysis_cache import AnalysisCache
from app.services import rulebook_answer as answer

ARTICLES = [
    {
        "cite": 1,
        "codes": ["B3.5.3", "B3.4.2"],
        "source": "Section B · Sporting",
        "document": "FIA 2026 F1 Regulations - Section B [Sporting].pdf",
        "page": 29,
        "excerpt": "B3.5.3 When deemed to be in parc fermé, only the work listed in Appendix B2 may be carried out.",
    }
]
ITEM = {
    "cite": 2,
    "number": 65,
    "event": "Mexico City Grand Prix",
    "car": 30,
    "driver": "Liam Lawson",
    "offence": "Changes made during Parc Ferme",
    "decision": "Required to start the Race from the pit lane.",
    "articles": ["B3.5.3", "ISC 12.2.1.l"],
    "url": "https://www.fia.com/doc65.pdf",
}
DECISIONS = {
    "match": "article",
    "status": "matched",
    "events": 19,
    "total": 1,
    "articles": ["B3.5.3"],
    "words": [],
    "items": [ITEM],
}
KEYWORD = {**DECISIONS, "match": "keyword", "articles": [], "words": ["pit", "lane"], "items": [{**ITEM, "cite": 1}]}
GOOD = {
    "heading": "A car that broke parc fermé starts from the pit lane",
    "paragraph": "Work beyond Appendix B2 is barred under B3.5.3 [1]. Car 30 started from the **pit lane** [2].",
}


class _FakeLLM:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return AIMessage(content=self.outcome)


class _HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _provider(name: str) -> LLMProvider:
    return LLMProvider(name=name, model=f"{name}-model", key_env=f"{name.upper()}_KEY")


@pytest.fixture
def engines(monkeypatch):
    """Install fake engines (name -> outcome); returns the fakes and the rested engines."""
    rested: list[str] = []
    fakes: dict[str, _FakeLLM] = {}

    def install(**outcomes):
        for name, outcome in outcomes.items():
            fakes[name] = _FakeLLM(outcome)
        providers = tuple(_provider(name) for name in outcomes)
        monkeypatch.setattr(answer, "available_providers", lambda: providers)
        monkeypatch.setattr(answer, "build_chat_llm", lambda provider: fakes[provider.name])
        monkeypatch.setattr(answer, "mark_unavailable", lambda provider, exc: rested.append(provider.name))
        return fakes

    monkeypatch.setattr(answer, "analysis_cache", AnalysisCache(None, 8))
    install.rested = rested
    return install


def _reply(**fields) -> str:
    return json.dumps({**GOOD, **fields})


def _check(heading=GOOD["heading"], paragraph=GOOD["paragraph"], decisions=DECISIONS):
    return answer.check_reply(heading, paragraph, ARTICLES, decisions)


@pytest.mark.unit
def test_a_reply_built_from_the_evidence_passes_the_check():
    assert _check() == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("paragraph", "fragment"),
    [
        ("Starts from the pit lane [9].", "source [9]"),
        ("Starts from the pit lane.", "no source marker"),
        ("Article B3.5.9 forbids it [1].", "B3.5.9"),
        ("Article 99.1 applies [2].", "Article 99.1"),
        ("Document 66 says so [2].", "document 66"),
        ("Car 31 was sent to the pit lane [2].", "car 31"),
        ("**a** **b** **c** **d** [1]", "bold"),
        ("**unclosed [1]", "bold"),
    ],
)
def test_a_reply_naming_something_the_evidence_lacks_is_flagged(paragraph, fragment):
    problems = _check(paragraph=paragraph)

    assert any(fragment in problem for problem in problems)


@pytest.mark.unit
def test_a_parent_article_of_an_evidence_article_passes():
    assert _check(paragraph="Article B3.5 governs parc fermé [1].") == []


@pytest.mark.unit
def test_an_isc_article_held_in_a_decision_passes():
    decisions = {**DECISIONS, "items": [{**ITEM, "articles": ["ISC Appendix L Chapter IV Article 2.5 d)"]}]}

    assert _check(paragraph="Article 2.5 was breached [2].", decisions=decisions) == []


@pytest.mark.unit
def test_parse_reply_accepts_plain_and_fenced_json():
    fenced = "```json\n" + _reply() + "\n```"

    assert answer.parse_reply(_reply()) == (GOOD["heading"], GOOD["paragraph"])
    assert answer.parse_reply(fenced) == (GOOD["heading"], GOOD["paragraph"])


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[1, 2]",
        json.dumps({"heading": "only a heading"}),
        json.dumps({"heading": 3, "paragraph": "x"}),
        json.dumps({"heading": "", "paragraph": "x [1]"}),
        json.dumps({"heading": "h" * 121, "paragraph": "x [1]"}),
        json.dumps({"heading": "see [1]", "paragraph": "x [1]"}),
        json.dumps({"heading": "a **bold** claim", "paragraph": "x [1]"}),
        json.dumps({"heading": "ok", "paragraph": ""}),
        json.dumps({"heading": "ok", "paragraph": "p" * 1201}),
    ],
)
def test_a_reply_that_is_not_the_asked_for_json_is_rejected(reply):
    with pytest.raises(ValueError, match=r"reply|heading|paragraph"):
        answer.parse_reply(reply)


@pytest.mark.unit
def test_a_checked_reply_is_shown_as_ai_written_and_asked_for_once(engines):
    fakes = engines(first=_reply())

    first = answer.write_summary("When must a car start from the pit lane?", 2026, ARTICLES, DECISIONS)
    again = answer.write_summary("  when must a car start from the PIT lane ", 2026, ARTICLES, DECISIONS)

    assert first == {**GOOD, "written_by": "ai", "why": None}
    assert again == first
    assert len(fakes["first"].calls) == 1


@pytest.mark.unit
def test_a_different_question_or_different_evidence_asks_again(engines):
    fakes = engines(first=_reply())
    answer.write_summary("one question", 2026, ARTICLES, DECISIONS)

    answer.write_summary("another question", 2026, ARTICLES, DECISIONS)
    answer.write_summary("one question", 2026, ARTICLES, {**DECISIONS, "items": [{**ITEM, "url": "https://x/new.pdf"}]})
    answer.write_summary("one question", 2026, [{**ARTICLES[0], "excerpt": "changed"}], DECISIONS)

    assert len(fakes["first"].calls) == 4


@pytest.mark.unit
def test_the_human_message_holds_exactly_the_evidence_blocks(engines):
    fakes = engines(first=_reply())

    answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    system, human = fakes["first"].calls[0]
    assert "only the numbered sources" in system.content
    assert "regulation text is unavailable" not in system.content
    assert human.content == (
        "Question: Q?\n\nSources:\n"
        "[1] FIA 2026 F1 Regulations, Section B · Sporting, page 29, articles B3.5.3, B3.4.2:\n"
        f"{ARTICLES[0]['excerpt']}\n\n"
        "[2] Stewards' decision, Mexico City Grand Prix 2026, document 65, car 30 (Liam Lawson), "
        "articles B3.5.3, ISC 12.2.1.l, offence: Changes made during Parc Ferme, "
        'decision: "Required to start the Race from the pit lane."'
    )


@pytest.mark.unit
def test_a_driverless_decision_block_omits_the_name(engines):
    fakes = engines(first=_reply())

    answer.write_summary("Q?", 2026, [], {**KEYWORD, "items": [{**KEYWORD["items"][0], "driver": None}]})

    assert "car 30, articles" in fakes["first"].calls[0][1].content


@pytest.mark.unit
def test_keyword_mode_tells_the_model_the_regulations_are_unavailable(engines):
    fakes = engines(first=_reply(paragraph="Car 30 started from the **pit lane** [1]."))

    result = answer.write_summary("pit lane?", 2026, [], KEYWORD)

    assert result["written_by"] == "ai"
    assert "regulation text is unavailable" in fakes["first"].calls[0][0].content


@pytest.mark.unit
def test_keyword_mode_with_no_match_makes_no_model_call(engines):
    fakes = engines(first=_reply())

    result = answer.write_summary("zebra", 2026, [], {**KEYWORD, "items": [], "total": 0, "status": "none"})

    assert fakes["first"].calls == []
    assert (result["written_by"], result["why"]) == ("computed", None)


@pytest.mark.unit
def test_when_the_first_engine_fails_with_a_provider_error_the_next_answers(engines):
    fakes = engines(first=_HttpError(429), second=_reply())

    result = answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    assert result["written_by"] == "ai"
    assert engines.rested == ["first"]
    assert len(fakes["second"].calls) == 1


@pytest.mark.unit
def test_every_engine_failing_gives_computed_text_that_is_not_kept(engines):
    fakes = engines(first=_HttpError(503))

    result = answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)
    answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    assert (result["written_by"], result["why"]) == ("computed", "ai_unavailable")
    assert result["heading"].startswith("The closest rule: ")
    assert len(fakes["first"].calls) == 2


@pytest.mark.unit
def test_an_error_that_is_not_the_engines_stops_at_computed_text(engines):
    fakes = engines(first=ValueError("bad request"), second=_reply())

    result = answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    assert result["why"] == "ai_unavailable"
    assert fakes["second"].calls == []
    assert engines.rested == []


@pytest.mark.unit
def test_no_engine_key_gives_computed_text(engines, monkeypatch):
    engines(first=_reply())
    monkeypatch.setattr(answer, "available_providers", lambda: (_ for _ in ()).throw(RuntimeError("no key")))

    result = answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    assert (result["written_by"], result["why"]) == ("computed", "ai_unavailable")


@pytest.mark.unit
@pytest.mark.parametrize("reply", ["not json", _reply(paragraph="Car 31 was sent off [2].")])
def test_a_reply_that_fails_the_check_is_never_shown_or_kept(engines, reply):
    fakes = engines(first=reply)

    result = answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)
    answer.write_summary("Q?", 2026, ARTICLES, DECISIONS)

    assert (result["written_by"], result["why"]) == ("computed", "check_failed")
    assert "31" not in result["paragraph"]
    assert len(fakes["first"].calls) == 2


@pytest.mark.unit
def test_keyword_mode_falls_back_to_the_keyword_text_labelled(engines):
    engines(first="not json")

    result = answer.write_summary("pit lane?", 2026, [], KEYWORD)

    assert result["why"] == "check_failed"
    assert result["heading"] == "1 stewards' decision shares words with the question"
