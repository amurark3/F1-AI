"""Tests for app.api.llm — which chat engine answers, and when to give up on one.

The contract is narrow but load-bearing:

* A missing key fails loudly, naming every key that would fix it, rather than
  degrading into a chat loop that never calls a tool.
* Engines are tried in the configured order, skipping any with no key and any
  resting after a failure — that is what keeps the chat answering when AMD
  Token Lab's points or access window run out.
* Only the engine's own failures (an HTTP status, a dropped connection) hand a
  question to the next engine; a bug in our code must surface instead.
* Text comes out clean whatever shape the engine returned it in.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import NoReturn

import httpx
from langchain_core.messages import AIMessage
import pytest

from app.api import llm as llm_module
from app.config import LLMProvider

TOKENLAB = LLMProvider(name="tokenlab", model="m-open", key_env="TL_KEY", base_url="https://tl.example/v1")
GEMINI = LLMProvider(name="gemini", model="m-gemini", key_env="G_KEY")


@pytest.fixture(autouse=True)
def _two_engines(monkeypatch):
    """A fixed engine list with no keys set and nothing resting."""
    monkeypatch.setattr(llm_module, "LLM_PROVIDERS", (TOKENLAB, GEMINI))
    monkeypatch.setattr(llm_module, "_resting_until", {})
    monkeypatch.delenv("TL_KEY", raising=False)
    monkeypatch.delenv("G_KEY", raising=False)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(llm_module.time, "monotonic", fake)
    return fake


def _install_fake_clients(monkeypatch, recorder: list):
    """Register fake client modules for the builder's lazy imports."""

    def _client(kind: str):
        def _build(**kwargs):
            recorder.append((kind, kwargs))
            return SimpleNamespace(kind=kind, **kwargs)

        return _build

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=_client("openai")))
    monkeypatch.setitem(
        sys.modules, "langchain_google_genai", SimpleNamespace(ChatGoogleGenerativeAI=_client("gemini"))
    )


def _status_error(status: int) -> Exception:
    """The shape openai raises: an exception carrying ``status_code``."""
    exc = RuntimeError(f"Error code: {status}")
    exc.status_code = status  # type: ignore[attr-defined]
    return exc


def _wrapped_gemini_error(code: int) -> Exception:
    """The shape langchain-google-genai raises: its own error, Google's ``code`` on the cause."""
    cause = RuntimeError(f"{code} RESOURCE_EXHAUSTED")
    cause.code = code  # type: ignore[attr-defined]
    try:
        raise ValueError("Error calling model 'gemini' (RESOURCE_EXHAUSTED)") from cause
    except ValueError as wrapped:
        return wrapped


# ---------------------------------------------------------------------------
# Which engines are available
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_key_at_all_raises_naming_every_key_that_would_fix_it():
    with pytest.raises(RuntimeError) as excinfo:
        llm_module.available_providers()

    message = str(excinfo.value)
    assert "TL_KEY" in message
    assert "G_KEY" in message


@pytest.mark.unit
def test_an_empty_key_is_treated_as_missing(monkeypatch):
    # An env var set to "" is a common .env mistake and must not reach an engine.
    monkeypatch.setenv("TL_KEY", "")

    with pytest.raises(RuntimeError):
        llm_module.available_providers()


@pytest.mark.unit
def test_engines_come_back_in_configured_order(monkeypatch):
    monkeypatch.setenv("TL_KEY", "tl-1")
    monkeypatch.setenv("G_KEY", "g-1")

    assert llm_module.available_providers() == (TOKENLAB, GEMINI)


@pytest.mark.unit
def test_an_engine_without_a_key_is_skipped(monkeypatch):
    monkeypatch.setenv("G_KEY", "g-1")

    assert llm_module.available_providers() == (GEMINI,)


@pytest.mark.unit
def test_a_resting_engine_is_skipped_until_its_rest_ends(monkeypatch, clock):
    monkeypatch.setenv("TL_KEY", "tl-1")
    monkeypatch.setenv("G_KEY", "g-1")

    llm_module.mark_unavailable(TOKENLAB, _status_error(429))
    assert llm_module.available_providers() == (GEMINI,)

    clock.now += llm_module.LLM_TRANSIENT_COOLDOWN_SECONDS + 1
    assert llm_module.available_providers() == (TOKENLAB, GEMINI)


@pytest.mark.unit
def test_when_every_engine_is_resting_they_are_all_tried_anyway(monkeypatch, clock):
    """Refusing outright would guarantee an error; one may have recovered."""
    monkeypatch.setenv("TL_KEY", "tl-1")
    monkeypatch.setenv("G_KEY", "g-1")

    llm_module.mark_unavailable(TOKENLAB, _status_error(402))
    llm_module.mark_unavailable(GEMINI, _status_error(429))

    assert llm_module.available_providers() == (TOKENLAB, GEMINI)


@pytest.mark.unit
@pytest.mark.parametrize("status", [401, 402, 403, 404])
def test_an_account_problem_rests_the_engine_for_the_long_cooldown(monkeypatch, clock, status):
    """Expired access, spent points, a wrong model id: none clears in a minute."""
    monkeypatch.setenv("TL_KEY", "tl-1")
    monkeypatch.setenv("G_KEY", "g-1")

    llm_module.mark_unavailable(TOKENLAB, _status_error(status))
    clock.now += llm_module.LLM_TRANSIENT_COOLDOWN_SECONDS + 1

    assert llm_module.available_providers() == (GEMINI,)


@pytest.mark.unit
def test_a_request_specific_rejection_does_not_rest_the_engine(monkeypatch, clock):
    """A 400 is about this request; the next question may be fine."""
    monkeypatch.setenv("TL_KEY", "tl-1")

    llm_module.mark_unavailable(TOKENLAB, _status_error(400))

    assert llm_module.available_providers() == (TOKENLAB,)


@pytest.mark.unit
def test_resting_an_engine_replaces_the_rest_map_rather_than_mutating_it(monkeypatch, clock):
    before = llm_module._resting_until

    llm_module.mark_unavailable(TOKENLAB, _status_error(503))

    assert before == {}
    assert llm_module._resting_until is not before


# ---------------------------------------------------------------------------
# Building a client
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_openai_compatible_engine_gets_its_base_url_key_and_settings(monkeypatch):
    monkeypatch.setenv("TL_KEY", "tl-secret")
    built: list = []
    _install_fake_clients(monkeypatch, built)

    llm_module.build_chat_llm(TOKENLAB)

    kind, kwargs = built[0]
    assert kind == "openai"
    assert kwargs["model"] == "m-open"
    assert kwargs["base_url"] == "https://tl.example/v1"
    assert kwargs["api_key"] == "tl-secret"
    assert kwargs["temperature"] == llm_module.LLM_TEMPERATURE
    assert kwargs["timeout"] == llm_module.LLM_REQUEST_TIMEOUT_SECONDS
    assert kwargs["max_retries"] == llm_module.LLM_MAX_RETRIES


@pytest.mark.unit
def test_gemini_is_built_with_its_own_client_and_no_temperature(monkeypatch):
    """Gemini 3.5+ fixes its own sampling and warns on every request that sets it."""
    monkeypatch.setenv("G_KEY", "g-secret")
    built: list = []
    _install_fake_clients(monkeypatch, built)

    llm_module.build_chat_llm(GEMINI)

    kind, kwargs = built[0]
    assert kind == "gemini"
    assert kwargs["model"] == "m-gemini"
    assert kwargs["api_key"] == "g-secret"
    assert "temperature" not in kwargs
    assert kwargs["thinking_level"] == llm_module.GEMINI_THINKING_LEVEL
    assert kwargs["timeout"] == llm_module.LLM_REQUEST_TIMEOUT_SECONDS
    assert kwargs["max_retries"] == llm_module.LLM_MAX_RETRIES


@pytest.mark.unit
def test_without_an_engine_named_the_first_available_one_is_built(monkeypatch):
    monkeypatch.setenv("G_KEY", "g-1")
    built: list = []
    _install_fake_clients(monkeypatch, built)

    llm_module.build_chat_llm()

    assert [kind for kind, _ in built] == ["gemini"]


@pytest.mark.unit
def test_building_an_engine_whose_key_is_missing_raises(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=lambda **_: pytest.fail("must not construct a client")),
    )

    with pytest.raises(RuntimeError, match="TL_KEY"):
        llm_module.build_chat_llm(TOKENLAB)


@pytest.mark.unit
def test_the_selection_is_logged_without_leaking_the_key(monkeypatch, capsys):
    monkeypatch.setenv("TL_KEY", "tl-secret-value")
    _install_fake_clients(monkeypatch, [])

    llm_module.build_chat_llm(TOKENLAB)
    logged = capsys.readouterr().out

    assert "llm.provider_selected" in logged
    assert "tl-secret-value" not in logged


@pytest.mark.unit
def test_temperature_defaults_to_deterministic():
    # Tool selection is a routing decision, not a creative one.
    assert llm_module.LLM_TEMPERATURE == 0


# ---------------------------------------------------------------------------
# Classifying failures
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 401, 402, 404, 429, 500, 503])
def test_an_http_status_from_the_engine_is_its_failure(status):
    assert llm_module.is_provider_failure(_status_error(status))


@pytest.mark.unit
def test_a_status_carried_on_the_cause_is_found():
    """langchain-google-genai wraps Google's error; the 402 lives on ``__cause__``."""
    assert llm_module.is_provider_failure(_wrapped_gemini_error(402))


def _dropped_connection() -> Exception:
    """The shape openai raises: its own error, raised from httpx's."""
    try:
        raise RuntimeError("Connection error.") from httpx.ConnectError("reset by peer")
    except RuntimeError as exc:
        return exc


@pytest.mark.unit
def test_a_dropped_connection_is_the_engines_failure():
    assert llm_module.is_provider_failure(_dropped_connection())


def _fail_to_save() -> NoReturn:
    raise ValueError("database write failed")


def _raised_while_handling(handled: Exception) -> Exception:
    """A new error raised inside an ``except`` block, so ``handled`` is only its context."""
    try:
        try:
            raise handled
        except type(handled):
            _fail_to_save()
    except ValueError as exc:
        return exc


@pytest.mark.unit
def test_an_error_merely_raised_while_handling_an_engine_error_is_not_one():
    """Only explicit ``raise ... from`` links count; implicit context is unrelated."""
    assert not llm_module.is_provider_failure(_raised_while_handling(_status_error(503)))


@pytest.mark.unit
def test_our_own_bug_is_not_an_engine_failure():
    """Failing over would only run the same bug twice and hide it."""
    assert not llm_module.is_provider_failure(KeyError("messages"))


@pytest.mark.unit
def test_a_code_outside_the_http_range_is_not_a_status():
    exc = RuntimeError("exit")
    exc.code = 1  # type: ignore[attr-defined]

    assert not llm_module.is_provider_failure(exc)


@pytest.mark.unit
def test_an_exception_chain_that_loops_back_on_itself_terminates():
    first, second = RuntimeError("a"), RuntimeError("b")
    first.__cause__, second.__cause__ = second, first

    assert not llm_module.is_provider_failure(first)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [_status_error(429), _wrapped_gemini_error(429), RuntimeError("Rate limit reached for model")],
    ids=["status", "wrapped", "message"],
)
def test_a_rate_limit_is_recognised_in_every_shape(exc):
    assert llm_module.is_rate_limited(exc)


@pytest.mark.unit
def test_spent_credit_is_not_a_rate_limit():
    """Gemini reports both as RESOURCE_EXHAUSTED; only the 429 clears by waiting."""
    assert not llm_module.is_rate_limited(_wrapped_gemini_error(402))


# ---------------------------------------------------------------------------
# message_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plain_string_content_is_returned_trimmed():
    assert llm_module.message_text(AIMessage(content="  Verstappen won.\n")) == "Verstappen won."


@pytest.mark.unit
def test_block_list_content_is_rendered_as_its_text():
    """Gemini can answer in content blocks; str() of them is a Python list on screen."""
    message = AIMessage(content=[{"type": "text", "text": "Verstappen won.", "extras": {"signature": "abc"}}])

    assert llm_module.message_text(message) == "Verstappen won."


@pytest.mark.unit
def test_inline_reasoning_is_stripped():
    """Open reasoning models served without a reasoning parser put their thinking in the text."""
    message = AIMessage(content="<think>Check the rows first.</think>\nVerstappen won.")

    assert llm_module.message_text(message) == "Verstappen won."


@pytest.mark.unit
def test_reasoning_without_its_opening_tag_is_stripped_up_to_the_closing_tag():
    """Seen live on Token Lab's DeepSeek-V4-Flash: a no-tools turn opened with a
    bare closing tag, the reasoning parser having taken the opening one."""
    assert llm_module.message_text(AIMessage(content="</think>I don't have the race results.")) == (
        "I don't have the race results."
    )
    assert llm_module.message_text(AIMessage(content="Check the rows.</think>\nVerstappen won.")) == "Verstappen won."


@pytest.mark.unit
def test_no_message_is_no_text():
    assert llm_module.message_text(None) == ""
