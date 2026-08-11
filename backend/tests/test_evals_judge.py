"""Tests for app.evals.judge — LLM-as-judge scoring with a keyword fallback.

The judge produces the number CI gates on, so two failure modes matter. First,
a fragile parser: the model returns prose around its JSON, or a bare number, or
a score outside 0..1 — any of which must land on a usable float rather than
blowing up the eval run. Second, the fallback: when Groq is unreachable
(``GROQ_API_KEY`` is unset in this suite, so that is the default path) the run
must still yield a score, and it must be the *keyword* score rather than a
silent 1.0 — otherwise an outage reads as a passing build.

The LLM boundary is faked; no Groq call is ever made.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.evals import judge


class _FakeLLM:
    """Returns a canned judge response, or raises, on ``invoke``."""

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.prompts: list[list] = []

    def invoke(self, messages):
        self.prompts.append(messages)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.content)


def _install_judge_llm(monkeypatch, llm: _FakeLLM) -> _FakeLLM:
    """Patch the lazily imported ``build_chat_llm`` on its home module."""
    from app.api import llm as llm_module

    monkeypatch.setattr(llm_module, "build_chat_llm", lambda: llm)
    return llm


# ---------------------------------------------------------------------------
# keyword_score()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("answer", "must_include", "expected"),
    [
        ("Max Verstappen won the 2021 title.", ["Verstappen"], 1.0),
        ("max verstappen won it.", ["Verstappen"], 1.0),  # case-insensitive
        ("A fine of €100 per km/h applies.", ["fine", "€", "km/h"], 1.0),
        ("A fine applies.", ["fine", "€", "km/h"], pytest.approx(1 / 3)),
        ("Lewis Hamilton won it.", ["Verstappen"], 0.0),
    ],
)
def test_keyword_score_is_the_fraction_of_signals_present(answer, must_include, expected):
    assert judge.keyword_score(answer, must_include) == expected


@pytest.mark.unit
def test_keyword_score_is_perfect_when_nothing_is_required():
    """No required signals means nothing to disprove — the case dataset.py forbids."""
    assert judge.keyword_score("anything at all", []) == 1.0


# ---------------------------------------------------------------------------
# _parse_score()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected_score", "expected_reason"),
    [
        ('{"score": 0.8, "reason": "names Verstappen"}', 0.8, "names Verstappen"),
        ('Sure! Here you go:\n{"score": 1.0, "reason": "correct"}\nHope that helps.', 1.0, "correct"),
        ('{"score": "0.5", "reason": "partial"}', 0.5, "partial"),  # numeric string coerces
        ('{"score": 0.4}', 0.4, ""),  # a missing reason is not an error
        ('{"score": 7}', 1.0, ""),  # clamped up
        ('{"score": -3}', 0.0, ""),  # clamped down
    ],
)
def test_parse_score_reads_the_json_verdict(text, expected_score, expected_reason):
    assert judge._parse_score(text) == (expected_score, expected_reason)


@pytest.mark.unit
def test_parse_score_spans_multiple_lines_of_json():
    score, reason = judge._parse_score('{\n  "score": 0.25,\n  "reason": "wrong driver"\n}')

    assert (score, reason) == (0.25, "wrong driver")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I would score this 0.6 overall.", 0.6),
        ("{not valid json at all} but 0.9 is my score", 0.9),  # bad JSON, bare float behind it
        ('{"score": null} — call it 0.3', 0.3),  # float(None) is a TypeError
        ('{"score": "high"} really, 0.7', 0.7),  # float("high") is a ValueError
        ("score: 4", 1.0),  # a bare out-of-range number is still clamped
    ],
)
def test_parse_score_falls_back_to_a_bare_number_in_freeform_output(text, expected):
    score, reason = judge._parse_score(text)

    assert score == expected
    assert reason == "parsed from freeform judge output"


@pytest.mark.unit
def test_parse_score_raises_when_no_number_is_present():
    with pytest.raises(ValueError, match="Could not parse judge score"):
        judge._parse_score("The answer is entirely wrong.")


@pytest.mark.unit
def test_parse_score_error_truncates_a_runaway_response():
    with pytest.raises(ValueError, match="Could not parse judge score") as excinfo:
        judge._parse_score("no digits here " * 200)

    assert len(str(excinfo.value)) < 200


# ---------------------------------------------------------------------------
# judge_answer()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_judge_answer_uses_the_llm_verdict_when_available(monkeypatch):
    llm = _install_judge_llm(monkeypatch, _FakeLLM('{"score": 0.9, "reason": "names Verstappen"}'))

    verdict = judge.judge_answer("Who won 2021?", "Max Verstappen.", "Must name Verstappen.", ["Verstappen"])

    assert verdict == {"score": 0.9, "reason": "names Verstappen", "method": "llm_judge"}
    system, human = llm.prompts[0]
    assert "strict grader" in system.content
    # The judge needs all three to grade; dropping the rubric would make it
    # score on vibes.
    assert "Who won 2021?" in human.content
    assert "Max Verstappen." in human.content
    assert "Must name Verstappen." in human.content


@pytest.mark.unit
def test_judge_answer_falls_back_to_keywords_when_the_llm_fails(monkeypatch):
    _install_judge_llm(monkeypatch, _FakeLLM(error=RuntimeError("GROQ_API_KEY is not set")))

    verdict = judge.judge_answer("Who won 2021?", "Max Verstappen.", "Must name Verstappen.", ["Verstappen"])

    assert verdict == {"score": 1.0, "reason": "keyword fallback", "method": "keyword"}


@pytest.mark.unit
def test_judge_answer_falls_back_when_the_verdict_cannot_be_parsed(monkeypatch):
    _install_judge_llm(monkeypatch, _FakeLLM("completely unparseable"))

    verdict = judge.judge_answer("Who won 2021?", "Lewis Hamilton.", "Must name Verstappen.", ["Verstappen"])

    # A parse failure must not inherit the LLM's optimism — the keyword score
    # is what a wrong answer actually earns.
    assert verdict == {"score": 0.0, "reason": "keyword fallback", "method": "keyword"}


@pytest.mark.unit
def test_judge_answer_without_a_key_degrades_rather_than_raising(monkeypatch):
    """The suite's default: GROQ_API_KEY is unset, so build_chat_llm raises."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    verdict = judge.judge_answer("Who won 2021?", "Max Verstappen.", "Must name Verstappen.", ["Verstappen"])

    assert verdict["method"] == "keyword"


@pytest.mark.unit
def test_judge_answer_logs_a_warning_when_it_degrades(monkeypatch):
    warnings: list[tuple[str, dict]] = []
    _install_judge_llm(monkeypatch, _FakeLLM(error=RuntimeError("rate limited")))
    monkeypatch.setattr(
        judge, "logger", type("L", (), {"warning": staticmethod(lambda e, **k: warnings.append((e, k)))})
    )

    judge.judge_answer("q", "a", "r", ["a"])

    # A silent downgrade to keyword scoring would make the gate meaningless.
    assert warnings[0][0] == "evals.judge_llm_unavailable_using_keywords"
    assert "rate limited" in warnings[0][1]["error"]
