"""Tests for live-race commentary generation.

No live session is needed: the LLM is stubbed and OpenF1 payloads are canned.
The point of the LLM tests is to prove the model is genuinely reached — the
generator previously referenced an undefined ``llm``, so every call raised
NameError into the template fallback and no AI commentary ever shipped.
"""

import asyncio

import pytest

from app.services import live_commentary as lc

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, content: str):
        self.content = content


class _FakeChat:
    """Stands in for the Groq chat model, recording the prompts it receives."""

    def __init__(self, reply: str = "  Antonelli sweeps past into the lead!  "):
        self.reply = reply
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _Response:
        self.prompts.append(prompt)
        return _Response(self.reply)


@pytest.fixture
def chat(monkeypatch) -> _FakeChat:
    fake = _FakeChat()
    monkeypatch.setattr(lc, "build_chat_llm", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _clear_state():
    lc._state.clear()
    yield
    lc._state.clear()


POSITION_CHANGE = {
    "type": "position_change",
    "driver": "ANT",
    "from_pos": 2,
    "to_pos": 1,
    "positions": [{"position": 1, "driver": "ANT"}, {"position": 2, "driver": "LEC"}],
}
SAFETY_CAR = {"type": "safety_car", "status": "safety car"}
PIT_STOP = {"type": "pit_stop", "driver": "VER", "pit_count": 2, "position": 4}


# --------------------------------------------------------------------------
# generate_commentary — the LLM path
# --------------------------------------------------------------------------


def test_generate_commentary_reaches_the_model(chat):
    """Regression: an undefined name here silently downgraded every call."""
    text = asyncio.run(lc.generate_commentary(POSITION_CHANGE, "Dutch Grand Prix"))

    assert chat.prompts, "the LLM was never invoked — commentary fell back to a template"
    assert text == "Antonelli sweeps past into the lead!"


def test_generate_commentary_prompt_carries_the_event_detail(chat):
    asyncio.run(lc.generate_commentary(POSITION_CHANGE, "Dutch Grand Prix"))

    prompt = chat.prompts[0]
    assert "Dutch Grand Prix" in prompt
    assert "P2" in prompt and "P1" in prompt


@pytest.mark.parametrize("event", [SAFETY_CAR, POSITION_CHANGE, PIT_STOP])
def test_generate_commentary_handles_every_event_type(chat, event):
    text = asyncio.run(lc.generate_commentary(event, "Dutch Grand Prix"))

    assert text
    assert len(chat.prompts) == 1


def test_generate_commentary_ignores_an_unknown_event_type(chat):
    text = asyncio.run(lc.generate_commentary({"type": "confetti"}, "Dutch Grand Prix"))

    assert text == ""
    assert chat.prompts == []


# --------------------------------------------------------------------------
# generate_commentary — the fallback path
# --------------------------------------------------------------------------


@pytest.fixture
def broken_chat(monkeypatch):
    def _explode():
        raise RuntimeError("groq unavailable")

    monkeypatch.setattr(lc, "build_chat_llm", _explode)


def test_generate_commentary_falls_back_when_the_model_fails(broken_chat):
    text = asyncio.run(lc.generate_commentary(POSITION_CHANGE, "Dutch Grand Prix"))

    assert "ANT" in text and "P1" in text


def test_generate_commentary_falls_back_for_a_safety_car(broken_chat):
    text = asyncio.run(lc.generate_commentary(SAFETY_CAR, "Dutch Grand Prix"))

    assert "Safety car" in text


def test_generate_commentary_falls_back_for_a_pit_stop(broken_chat):
    text = asyncio.run(lc.generate_commentary(PIT_STOP, "Dutch Grand Prix"))

    assert "VER" in text


def test_generate_commentary_survives_a_bad_model_response(monkeypatch):
    class _Nonsense:
        def invoke(self, _prompt):
            return object()  # no .content

    monkeypatch.setattr(lc, "build_chat_llm", lambda: _Nonsense())

    assert "ANT" in asyncio.run(lc.generate_commentary(POSITION_CHANGE, "Dutch Grand Prix"))


# --------------------------------------------------------------------------
# detect_event
# --------------------------------------------------------------------------

BEFORE = [{"position": 1, "driver": "LEC"}, {"position": 2, "driver": "ANT"}]
AFTER = [{"position": 1, "driver": "ANT"}, {"position": 2, "driver": "LEC"}]


def test_detect_event_prioritises_a_safety_car_over_a_pass():
    event = lc.detect_event(BEFORE, AFTER, "", "safety car", {}, {})

    assert event["type"] == "safety_car"


def test_detect_event_reports_a_position_change():
    event = lc.detect_event(BEFORE, AFTER, "", "", {}, {})

    assert event["type"] == "position_change"
    assert event["to_pos"] == 1


def test_detect_event_reports_a_pit_stop():
    event = lc.detect_event(BEFORE, BEFORE, "", "", {"ANT": 1}, {"ANT": 2})

    assert event["type"] == "pit_stop"
    assert event["pit_count"] == 1


def test_detect_event_is_quiet_when_nothing_changed():
    assert lc.detect_event(BEFORE, BEFORE, "", "", {}, {}) is None


def test_detect_event_does_not_re_announce_a_standing_safety_car():
    assert lc.detect_event(BEFORE, BEFORE, "safety car", "safety car", {}, {}) is None


# --------------------------------------------------------------------------
# next_commentary — the per-room state machine
# --------------------------------------------------------------------------


@pytest.fixture
def quiet_openf1(monkeypatch):
    """Canned OpenF1 auxiliary feeds: no flags, no pit stops."""
    async def _status(_key):
        return ""

    async def _stints(_key):
        return {}

    monkeypatch.setattr(lc, "fetch_session_status", _status)
    monkeypatch.setattr(lc, "fetch_stint_counts", _stints)


def test_next_commentary_stays_silent_on_the_first_snapshot(chat, quiet_openf1):
    """Nothing to compare against yet — narrating here invents events."""
    entry = asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))

    assert entry is None
    assert chat.prompts == []


def test_next_commentary_narrates_a_change_on_the_second_snapshot(chat, quiet_openf1):
    asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))
    entry = asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", AFTER))

    assert entry["event_type"] == "position_change"
    assert entry["text"] == "Antonelli sweeps past into the lead!"
    assert entry["timestamp"].startswith("20")


def test_next_commentary_respects_the_cooldown(chat, quiet_openf1):
    asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))
    asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", AFTER))
    second = asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))

    assert second is None, "a second narration inside the cooldown window"


def test_next_commentary_keeps_rooms_independent(chat, quiet_openf1):
    asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))
    entry = asyncio.run(lc.next_commentary("2026-13", "11360", "Italian Grand Prix", AFTER))

    assert entry is None, "one room's history leaked into another"


def test_reset_room_clears_history_between_sessions(chat, quiet_openf1):
    asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", BEFORE))
    lc.reset_room("2026-12")
    entry = asyncio.run(lc.next_commentary("2026-12", "11353", "Dutch Grand Prix", AFTER))

    assert entry is None, "qualifying's final order was compared against the race's first lap"
