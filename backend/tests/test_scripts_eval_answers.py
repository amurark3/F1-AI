"""Tests for scripts.eval_answers — the answer-quality eval for the AI Engineer.

The eval runs real questions through the real agent and scores the answers
against f1db, because the unit suite (by design) never sees a real answer:
every failure this eval exists for — invented teams, miscounted wins, a
"double" that never happened — passed 3,000 green tests. What is pinned here:

* **Scoring is right**: status read from what the user would see, team claims
  checked against the season's rows and the tools' own tables, known-wrong
  claims caught, required facts (computed from f1db) checked, numbers matched
  as digits or words.
* **The run is paced** between samples (the Groq free tier rate-limits back-to-
  back questions) and never before the first.
* **The exit code** fails only on a wrong answer, not on a rate-limited one.

The agent is replaced at ``ask``; f1db is the seeded fixture.
"""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage
import pytest

from app.api.routers import chat as chat_router
from scripts import eval_answers as ev

_CLEAN = "Max Verstappen (Red Bull) won both 2026 races; Charles Leclerc (Ferrari) was second."


def _transcript(answer: str, tool_texts: tuple[str, ...] = (), tools: tuple[str, ...] = ()) -> ev.Transcript:
    return ev.Transcript(answer=answer, tool_texts=tool_texts, tools=tools)


def _score(answer: str, question: ev.Question | None = None, **kwargs) -> ev.Score:
    q = question or ev.Question("q", "Who won?")
    reference = ev.Reference(ev.season_roster(2026), ("Red Bull", "Ferrari", "McLaren", "Alfa Romeo"))
    return ev.score(q, 1, _transcript(answer, **kwargs), reference)


# ---------------------------------------------------------------------------
# Reference data from f1db
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_the_season_roster_maps_each_driver_to_the_teams_they_raced_for(fake_f1db):
    roster = ev.season_roster(2026)

    assert roster["Verstappen"] == frozenset({"Red Bull"})
    assert roster["VER"] == frozenset({"Red Bull"})
    assert roster["Norris"] == frozenset({"McLaren"})


@pytest.mark.integration
def test_the_most_race_wins_fact_is_computed_from_the_data(fake_f1db):
    assert ev.most_race_wins_team() == ["Red Bull", "2"]


@pytest.mark.integration
def test_a_sessions_top_three_is_read_from_the_data_by_family_name(fake_f1db):
    """The podium and pole questions are scored against f1db, not a hardcoded list."""
    assert ev.top_three("SPRINT_RACE_RESULT", "bahrain")() == ["Leclerc", "Verstappen"]


@pytest.mark.integration
def test_every_question_with_an_expected_fact_can_compute_it(fake_f1db):
    """A broken query in the question set would only surface mid-run, after paying for answers."""
    for question in ev.QUESTIONS:
        if question.expect:
            assert all(question.expect())


# ---------------------------------------------------------------------------
# Scoring one answer
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_correct_answer_is_clean(fake_f1db):
    result = _score(_CLEAN)

    assert result.status == "answered"
    assert result.clean


@pytest.mark.integration
def test_a_team_the_season_contradicts_is_flagged(fake_f1db):
    result = _score("Max Verstappen (Alfa Romeo) won both races.")

    assert [(m["driver"], m["claimed_team"]) for m in result.misattributions] == [("Verstappen", "Alfa Romeo")]
    assert not result.clean


@pytest.mark.integration
def test_the_tools_own_tables_extend_the_roster(fake_f1db):
    """A driver the season rows lack is still checked against what the tools showed."""
    table = "| Pos | Driver | Team |\n| :-- | :----- | :--- |\n| 1 | Oscar Piastri (PIA) | McLaren |"

    result = _score("Oscar Piastri (Ferrari) won.", tool_texts=(table,))

    assert [m["driver"] for m in result.misattributions] == ["Piastri"]


@pytest.mark.integration
def test_a_known_wrong_claim_is_caught(fake_f1db):
    question = ev.Question("q", "Who won?", forbidden=(r"Norris[^.\n]{0,80}\bdouble\b",))

    result = _score("Lando Norris completed a double in Miami.", question)

    assert result.forbidden_hits == (r"Norris[^.\n]{0,80}\bdouble\b",)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("answer", "missing"),
    [
        ("Red Bull leads with 2 wins.", ()),
        ("Red Bull leads with two wins.", ()),
        ("Red Bull leads with three wins.", ("2",)),
        ("McLaren leads with 2 wins.", ("Red Bull",)),
    ],
)
def test_a_required_fact_is_matched_as_digits_or_words(fake_f1db, answer, missing):
    question = ev.Question("q", "Which team?", expect=lambda: ["Red Bull", "2"])

    assert _score(answer, question).missing == missing


@pytest.mark.integration
@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ("**System Error:** Something went wrong loading this data. (reference: abc)", "error"),
        ("**Box, box:** The engine is rate-limited right now (free tier).", "rate_limited"),
        ("**System Notice:** Reached the maximum number of reasoning steps.", "notice"),
        ("", "empty"),
        (_CLEAN, "answered"),
    ],
)
def test_the_status_is_what_the_user_would_see(fake_f1db, answer, status):
    result = _score(answer)

    assert result.status == status
    assert result.clean is (status == "answered")


@pytest.mark.integration
def test_unstated_absolutes_are_counted_as_a_risk_signal(fake_f1db):
    result = _score("Verstappen is the only winner and has never lost; none came close.")

    assert result.absolutes == 3
    assert result.clean, "an absolute is a risk, not an error on its own"


# ---------------------------------------------------------------------------
# Asking the agent
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ask_collects_the_answer_the_tools_used_and_their_tables(monkeypatch):
    async def _stream(messages, tool_names, conversation):
        assert conversation.user_id is None, "an eval must not write to anyone's memory"
        messages.append(ToolMessage(tool_call_id="c1", content="| a | team |", name="query_f1_database"))
        yield "[TOOL_START]Query F1 Database[/TOOL_START]"
        yield "[TOOL_END]Query F1 Database[/TOOL_END]"
        yield "Verstappen won."

    monkeypatch.setattr(chat_router, "_guarded_stream", _stream)

    transcript = await ev.ask("Who won?")

    assert transcript == ev.Transcript(
        answer="Verstappen won.", tool_texts=("| a | team |",), tools=("Query F1 Database",)
    )


# ---------------------------------------------------------------------------
# The run, the report and the exit code
# ---------------------------------------------------------------------------


def _install_agent(monkeypatch, answer: str = _CLEAN) -> list[float]:
    asked: list[str] = []
    pauses: list[float] = []

    async def _ask(text):
        asked.append(text)
        return _transcript(answer, tools=("Query F1 Database",))

    async def _sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(ev, "ask", _ask)
    monkeypatch.setattr(ev.asyncio, "sleep", _sleep)
    # main() loads backend/.env; under test that would put real credentials
    # back into a process the conftest scrubbed.
    monkeypatch.setattr(ev, "load_dotenv", lambda: None)
    return pauses


_TWO = (ev.Question("a", "First?"), ev.Question("b", "Second?"))


@pytest.mark.integration
async def test_the_run_pauses_between_samples_but_not_before_the_first(fake_f1db, monkeypatch):
    pauses = _install_agent(monkeypatch)

    scores = await ev.run(_TWO, samples=2, pause=75)

    assert [(s.question_id, s.sample) for s in scores] == [("a", 1), ("a", 2), ("b", 1), ("b", 2)]
    assert pauses == [75, 75, 75]


@pytest.mark.integration
async def test_the_report_summarises_each_question_and_details_each_flag(fake_f1db, monkeypatch):
    _install_agent(monkeypatch, "Max Verstappen (Ferrari) won.")

    report = ev.report(await ev.run(_TWO[:1], samples=1, pause=0))

    assert "a: answered 1/1 · clean 0/1 · misattributions 1 · forbidden 0 · missing 0 · absolutes 0" in report
    assert "  sample 1 [Query F1 Database]: Verstappen → Ferrari (rows: Red Bull)" in report
    assert "TOTAL: answered 1/1 · clean 0/1" in report


@pytest.mark.integration
def test_main_writes_json_and_exits_zero_when_every_answer_is_clean(fake_f1db, monkeypatch, tmp_path, capsys):
    _install_agent(monkeypatch)
    out = tmp_path / "eval.json"

    code = ev.main(["--question", ev.QUESTIONS[1].id, "--samples", "1", "--pause", "0", "--json", str(out)])

    assert code == 0
    [saved] = json.loads(out.read_text())
    assert saved["question_id"] == ev.QUESTIONS[1].id
    assert "tool_texts" in saved, "a saved run is re-scored offline against the tables it saw"
    assert "TOTAL: answered 1/1 · clean 1/1" in capsys.readouterr().out


@pytest.mark.integration
def test_main_exits_one_when_an_answer_is_wrong(fake_f1db, monkeypatch):
    _install_agent(monkeypatch, "Max Verstappen (Ferrari) won.")

    assert ev.main(["--question", ev.QUESTIONS[1].id, "--samples", "1", "--pause", "0"]) == 1


@pytest.mark.integration
def test_a_rate_limited_answer_is_not_a_wrong_answer(fake_f1db, monkeypatch):
    """The free tier refusing a question says nothing about answer quality."""
    _install_agent(monkeypatch, "**Box, box:** The engine is rate-limited right now (free tier).")

    assert ev.main(["--question", ev.QUESTIONS[1].id, "--samples", "1", "--pause", "0"]) == 0


@pytest.mark.unit
def test_an_unknown_question_id_is_rejected():
    with pytest.raises(SystemExit):
        ev.main(["--question", "no-such-question"])


@pytest.mark.unit
def test_zero_samples_is_rejected():
    with pytest.raises(SystemExit):
        ev.main(["--samples", "0"])
