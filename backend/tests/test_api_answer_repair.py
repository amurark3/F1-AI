"""Tests for app.api.answer_repair — the check that runs on every final answer.

The answer is compared with the driver↔team pairs in this conversation's tool
tables. What is pinned:

* **A clean answer costs nothing**: no tables or no contradiction means no
  request and an unchanged answer — the free tier cannot afford a pass per answer.
* **A contradiction gets one repair**, naming the sentence and the team the
  rows show, and the repair is re-checked before it replaces the draft.
* **Every failure degrades to the draft plus a "Data check" line** stating what
  the rows show — a refused repair, a repair still wrong, a rate limit. The line
  is true even when the flag was not, so a false positive cannot add a falsehood.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from app.api import answer_repair
from app.api.answer_repair import checked_answer

_TABLE = """| round | sprint_winner | sprint_team | race_winner | race_team |
| --- | --- | --- | --- | --- |
| 4 | Lando Norris | McLaren | Kimi Antonelli | Mercedes |
| 12 | George Russell | Mercedes | Lando Norris | McLaren |"""

_HISTORY = [HumanMessage(content="who won?"), ToolMessage(tool_call_id="c1", content=_TABLE, name="query_f1_database")]
_WRONG = "Mercedes drivers (Russell three times, Norris once) won the sprints."
_FIXED = "Mercedes drivers (Russell three times, Antonelli once) won the sprints."
_NOTE = "\n\n**Data check:** Norris drove for McLaren in these results, not Mercedes."


@pytest.fixture(autouse=True)
def _teams(monkeypatch):
    """Every team f1db knows — including one only the model's memory would reach for."""
    monkeypatch.setattr(answer_repair, "constructor_names", lambda: frozenset({"Mercedes", "McLaren", "Alfa Romeo"}))


class _Editor:
    """Stands in for the no-tools model call; ``reply`` may be text, None or an exception."""

    def __init__(self, reply):
        self.reply = reply
        self.seen: list[list] = []

    async def __call__(self, messages):
        self.seen.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return None if self.reply is None else AIMessage(content=self.reply)


@pytest.mark.unit
async def test_an_answer_with_no_tool_tables_is_returned_untouched():
    editor = _Editor("unused")

    assert await checked_answer([HumanMessage(content="hi")], _WRONG, editor) == _WRONG
    assert editor.seen == []


@pytest.mark.unit
async def test_an_answer_the_rows_support_costs_no_request():
    editor = _Editor("unused")

    assert await checked_answer(_HISTORY, _FIXED, editor) == _FIXED
    assert editor.seen == []


@pytest.mark.unit
async def test_a_contradiction_is_repaired_with_the_correction_spelled_out():
    editor = _Editor(_FIXED)

    assert await checked_answer(_HISTORY, _WRONG, editor) == _FIXED
    [request] = editor.seen
    prompt = request[-1].content
    assert f'- In "{_WRONG}": Norris drove for McLaren, not Mercedes.' in prompt
    assert prompt.endswith(f"ANSWER:\n{_WRONG}")


@pytest.mark.unit
async def test_a_team_only_f1db_knows_is_still_recognised():
    """'Alfa Romeo' appears in no tool table; it is a team because f1db says so."""
    editor = _Editor("Lando Norris (McLaren) won.")

    assert await checked_answer(_HISTORY, "Lando Norris (Alfa Romeo) won.", editor) == "Lando Norris (McLaren) won."


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply",
    [
        _WRONG,  # the repair repeated the mistake
        None,  # the model reached for a tool and was refused
        "   ",  # it returned nothing usable
        RuntimeError("Rate limit reached for model"),
    ],
)
async def test_a_failed_repair_falls_back_to_the_draft_and_a_data_check(reply):
    assert await checked_answer(_HISTORY, _WRONG, _Editor(reply)) == _WRONG + _NOTE


@pytest.mark.unit
async def test_without_f1db_the_tables_own_teams_still_count(monkeypatch):
    """The lookup is a courtesy: Mercedes is a team because the rows name it."""

    def _locked():
        raise RuntimeError("f1db is locked")

    monkeypatch.setattr(answer_repair, "constructor_names", _locked)

    assert await checked_answer(_HISTORY, _WRONG, _Editor(_FIXED)) == _FIXED
