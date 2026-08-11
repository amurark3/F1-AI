"""Tests for app.api.llm — construction of the Groq chat model.

The contract is narrow but load-bearing: a missing key must fail loudly at
construction time rather than degrading into a chat loop that silently never
calls a tool.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.api import llm as llm_module


def _install_fake_groq(monkeypatch, recorder: dict):
    """Register a fake ``langchain_groq`` for the function's lazy import."""

    class _FakeChatGroq:
        def __init__(self, **kwargs):
            recorder.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_groq", SimpleNamespace(ChatGroq=_FakeChatGroq))
    return _FakeChatGroq


@pytest.mark.unit
def test_missing_api_key_raises_with_actionable_guidance(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        llm_module.build_chat_llm()

    message = str(excinfo.value)
    assert "GROQ_API_KEY" in message
    assert "console.groq.com" in message


@pytest.mark.unit
def test_empty_api_key_is_treated_as_missing(monkeypatch):
    # An env var set to "" is a common .env mistake and must not reach Groq.
    monkeypatch.setenv("GROQ_API_KEY", "")

    with pytest.raises(RuntimeError):
        llm_module.build_chat_llm()


@pytest.mark.unit
def test_groq_is_not_imported_when_the_key_is_absent(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "langchain_groq",
        SimpleNamespace(ChatGroq=lambda **_: pytest.fail("must not construct a client")),
    )

    with pytest.raises(RuntimeError):
        llm_module.build_chat_llm()


@pytest.mark.unit
def test_builds_the_model_from_config_and_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
    recorder: dict = {}
    _install_fake_groq(monkeypatch, recorder)

    result = llm_module.build_chat_llm()

    assert result is not None
    assert recorder["model"] == llm_module.GROQ_MODEL_NAME
    assert recorder["temperature"] == llm_module.LLM_TEMPERATURE
    assert recorder["api_key"] == "gsk-test-key"


@pytest.mark.unit
def test_selection_is_logged_without_leaking_the_key(monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-secret-value")
    _install_fake_groq(monkeypatch, {})

    llm_module.build_chat_llm()
    logged = capsys.readouterr().out

    assert "llm.provider_selected" in logged
    assert "gsk-secret-value" not in logged


@pytest.mark.unit
def test_temperature_defaults_to_deterministic():
    # Tool selection is a routing decision, not a creative one.
    assert llm_module.LLM_TEMPERATURE == 0
