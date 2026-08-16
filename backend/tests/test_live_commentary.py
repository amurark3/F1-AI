"""Tests for app.api.live.commentary — the LLM copy layer of the live socket.

Commentary is generated inside the WebSocket poll loop, which shapes every risk
worth pinning here:

* **An LLM failure must not reach the socket.** Groq being down, rate-limiting
  or simply unconfigured has to degrade to a template line; an exception
  escaping ``_generate_commentary`` would land in the endpoint's handler and
  tear the connection down mid-race.
* **The model is a process-wide singleton built on first use.** Rebuilding it
  per event would pay a construction cost on every cooldown window, and the
  binding it memoises was once missing entirely — every call then raised
  ``NameError`` into the fallback and commentary was silently template-only.
* **Each event type has to say something specific.** The assertions below check
  what the prompt tells the model about the race situation (who moved where,
  which stop this is, what was deployed), not merely that a string came back.

Groq is never reached: ``build_chat_llm`` is replaced at the module boundary,
and ``GROQ_API_KEY`` is cleared by ``conftest`` so the unconfigured path is the
default one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.live import commentary

RACE_NAME = "Monaco Grand Prix"

SAFETY_CAR_EVENT = {"type": "safety_car", "status": "Safety Car"}
POSITION_EVENT = {
    "type": "position_change",
    "driver": "NOR",
    "from_pos": 3,
    "to_pos": 1,
    "positions": [
        {"position": 1, "driver": "NOR"},
        {"position": 2, "driver": "VER"},
        {"position": 3, "driver": "LEC"},
    ],
}
PIT_EVENT = {"type": "pit_stop", "driver": "HAM", "pit_count": 2, "position": 7}


class _FakeLLM:
    """Records the prompt it is handed and replays a scripted answer."""

    def __init__(self, reply="Lights out and away we go!", error=None):
        self.reply = reply
        self.error = error
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.reply)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """The built model is a module global; leaking it across tests hides bugs."""
    monkeypatch.setattr(commentary, "_commentary_llm", None)


def _install_llm(monkeypatch, llm):
    """Make the lazily-built singleton resolve to ``llm``."""
    monkeypatch.setattr(commentary, "build_chat_llm", lambda: llm)
    return llm


# ---------------------------------------------------------------------------
# _get_commentary_llm
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_model_is_built_once_and_reused(monkeypatch):
    builds = []
    monkeypatch.setattr(commentary, "build_chat_llm", lambda: builds.append(1) or _FakeLLM())

    first = commentary._get_commentary_llm()
    second = commentary._get_commentary_llm()

    assert first is second
    assert len(builds) == 1, "a poll cycle must not rebuild the chat model"


@pytest.mark.unit
def test_a_failed_build_is_not_memoised_as_a_working_model(monkeypatch):
    """A startup-time misconfiguration must be retried, not cached as broken."""
    monkeypatch.setattr(commentary, "build_chat_llm", lambda: (_ for _ in ()).throw(RuntimeError("GROQ_API_KEY")))

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        commentary._get_commentary_llm()

    assert commentary._commentary_llm is None


# ---------------------------------------------------------------------------
# Prompt content — what the commentator is told about the race situation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected_fragment"),
    [
        (SAFETY_CAR_EVENT, "The Safety Car has just been deployed."),
        (POSITION_EVENT, "Driver #NOR just moved from P3 to P1."),
        (PIT_EVENT, "Driver #HAM just pitted (stop #2), currently P7 after the stop."),
    ],
    ids=["safety-car", "position-change", "pit-stop"],
)
async def test_the_prompt_states_the_race_situation(monkeypatch, event, expected_fragment):
    llm = _install_llm(monkeypatch, _FakeLLM())

    await commentary._generate_commentary(event, RACE_NAME)

    prompt = llm.prompts[0]
    assert expected_fragment in prompt
    assert RACE_NAME in prompt


@pytest.mark.unit
async def test_a_position_change_prompt_lists_the_running_order(monkeypatch):
    llm = _install_llm(monkeypatch, _FakeLLM())

    await commentary._generate_commentary(POSITION_EVENT, RACE_NAME)

    assert "Current top 5: P1 #NOR, P2 #VER, P3 #LEC." in llm.prompts[0]


@pytest.mark.unit
async def test_a_position_change_without_a_running_order_still_prompts(monkeypatch):
    """``positions`` is optional on the event; its absence must not raise."""
    llm = _install_llm(monkeypatch, _FakeLLM())
    event = {key: value for key, value in POSITION_EVENT.items() if key != "positions"}

    await commentary._generate_commentary(event, RACE_NAME)

    assert "Current top 5: ." in llm.prompts[0]


@pytest.mark.unit
async def test_the_model_reply_is_returned_stripped(monkeypatch):
    _install_llm(monkeypatch, _FakeLLM(reply="  Safety car! Everything changes.\n"))

    text = await commentary._generate_commentary(SAFETY_CAR_EVENT, RACE_NAME)

    assert text == "Safety car! Everything changes."


@pytest.mark.unit
async def test_an_unknown_event_type_is_dropped_without_calling_the_model(monkeypatch):
    llm = _install_llm(monkeypatch, _FakeLLM())

    text = await commentary._generate_commentary({"type": "tyre_change"}, RACE_NAME)

    assert text == ""
    assert llm.prompts == [], "an event with no prompt must not reach the model"


# ---------------------------------------------------------------------------
# Degradation — the socket keeps running when the model does not
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            SAFETY_CAR_EVENT,
            f"Safety car out at {RACE_NAME}! The field bunches up and strategy windows open!",
        ),
        (POSITION_EVENT, "Position change! Driver #NOR moves to P1!"),
        (PIT_EVENT, "Driver #HAM dives into the pits for stop #2!"),
    ],
    ids=["safety-car", "position-change", "pit-stop"],
)
async def test_an_llm_failure_falls_back_to_a_template_line(monkeypatch, event, expected):
    _install_llm(monkeypatch, _FakeLLM(error=RuntimeError("groq is rate limiting")))

    assert await commentary._generate_commentary(event, RACE_NAME) == expected


@pytest.mark.unit
async def test_an_unconfigured_model_falls_back_instead_of_raising():
    """``GROQ_API_KEY`` is cleared by conftest, so the real builder raises here."""
    text = await commentary._generate_commentary(PIT_EVENT, RACE_NAME)

    assert text == "Driver #HAM dives into the pits for stop #2!"
    assert commentary._commentary_llm is None


@pytest.mark.unit
async def test_a_malformed_model_reply_falls_back(monkeypatch):
    """``response.content`` missing is an AttributeError inside the same guard."""
    monkeypatch.setattr(commentary, "build_chat_llm", lambda: SimpleNamespace(invoke=lambda _p: object()))

    text = await commentary._generate_commentary(SAFETY_CAR_EVENT, RACE_NAME)

    assert text.startswith("Safety car out at")


@pytest.mark.unit
async def test_the_llm_failure_is_logged_with_its_cause(monkeypatch, capsys):
    _install_llm(monkeypatch, _FakeLLM(error=RuntimeError("connection reset by peer")))

    await commentary._generate_commentary(SAFETY_CAR_EVENT, RACE_NAME)

    logged = capsys.readouterr().out
    assert "commentary.llm_error" in logged
    assert "connection reset by peer" in logged


class _TypeMatchingOnce(str):
    """An event type that compares equal to ``safety_car`` exactly once.

    Nothing in production produces this. It exists to reach the final
    ``return ""`` of the exception handler, which is unreachable for any real
    event: the prompt builder has already returned early for every type the
    handler does not recognise, so the handler's own default can never fire.
    """

    def __init__(self, *_args):
        self._comparisons = 0

    def __eq__(self, other):
        self._comparisons += 1
        return self._comparisons == 1

    def __hash__(self):
        return str.__hash__(self)


@pytest.mark.unit
async def test_an_unrecognised_type_in_the_fallback_yields_no_commentary(monkeypatch):
    _install_llm(monkeypatch, _FakeLLM(error=RuntimeError("groq is down")))
    event = {"type": _TypeMatchingOnce("safety_car"), "status": "Safety Car"}

    assert await commentary._generate_commentary(event, RACE_NAME) == ""
