"""Chat engines — AMD Token Lab first, Gemini's free tier as the fallback.

The engines and their order are code constants (``LLM_PROVIDERS`` in
app/config.py); only the keys come from the environment. Each question runs on
the first engine that has a key and is not resting after a failure. The chat
router hands a question to the next engine when one fails with its own error
(an HTTP status or a dropped connection), and :func:`mark_unavailable` rests the
failed engine so the next questions skip it:

* 401/402/403/404 — expired access, spent points or credit, a wrong model id —
  rest for ``LLM_ACCOUNT_COOLDOWN_SECONDS``; none of these clears in a minute.
* 408/429/5xx and connection errors rest for ``LLM_TRANSIENT_COOLDOWN_SECONDS``.
* Anything else the engine rejected (a 400) moves this question on but rests
  nothing: it was about the request, not the engine.

Clients are imported lazily so app startup stays light on Render's 512 MB.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import httpx
import structlog

from app.config import (
    GEMINI_THINKING_LEVEL,
    LLM_ACCOUNT_COOLDOWN_SECONDS,
    LLM_MAX_RETRIES,
    LLM_PROVIDERS,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_TEMPERATURE,
    LLM_TRANSIENT_COOLDOWN_SECONDS,
    LLMProvider,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage

logger = structlog.get_logger()

_ACCOUNT_STATUSES = frozenset({401, 402, 403, 404})
_TRANSIENT_STATUSES = frozenset({408, 429})
_FIRST_SERVER_ERROR = 500
_HTTP_ERROR_RANGE = range(400, 600)
_NETWORK_ERRORS = (httpx.TransportError, ConnectionError, TimeoutError)
_RATE_LIMIT = 429

# Where an open reasoning model's inline thinking ends. The opening tag is not
# always there: a server's reasoning parser can take it and leave the closing
# one, so everything up to the last closing tag is thinking.
_REASONING_END = "</think>"

# Engine name -> monotonic time it may be tried again. Replaced, never mutated.
_resting_until: dict[str, float] = {}


def _configured() -> tuple[LLMProvider, ...]:
    return tuple(provider for provider in LLM_PROVIDERS if os.getenv(provider.key_env))


def _missing_key_message() -> str:
    keys = ", ".join(provider.key_env for provider in LLM_PROVIDERS)
    return (
        f"No chat engine is configured: set at least one of {keys} in backend/.env. "
        "TOKENLAB_API_KEY comes from https://notebooks.amd.com/tokenlab; GOOGLE_API_KEY "
        "from https://aistudio.google.com on a project with no billing (free tier)."
    )


def available_providers() -> tuple[LLMProvider, ...]:
    """Engines to try for the next question, in order.

    Raises ``RuntimeError`` when no key is set. When every configured engine is
    resting they are all returned anyway: one may have recovered, and refusing
    outright would guarantee an error.
    """
    configured = _configured()
    if not configured:
        raise RuntimeError(_missing_key_message())
    now = time.monotonic()
    ready = tuple(provider for provider in configured if _resting_until.get(provider.name, 0.0) <= now)
    return ready or configured


def build_chat_llm(provider: LLMProvider | None = None) -> BaseChatModel:
    """Construct the chat model for ``provider``, or for the first available engine."""
    spec = provider or available_providers()[0]
    api_key = os.getenv(spec.key_env)
    if not api_key:
        raise RuntimeError(_missing_key_message())

    if spec.base_url is None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=spec.model,
            api_key=api_key,
            thinking_level=GEMINI_THINKING_LEVEL,
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )
    else:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=spec.model,
            base_url=spec.base_url,
            api_key=api_key,
            temperature=LLM_TEMPERATURE,
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )
    logger.info("llm.provider_selected", provider=spec.name, model=spec.model)
    return llm


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """``exc`` and every exception it was explicitly raised ``from``, each once.

    Implicit context is not followed: an error raised while another was being
    handled (a database write failing after a caught timeout, say) is not the
    engine's failure, and must not hand the question to the next engine.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__


def _http_status(exc: BaseException) -> int | None:
    """The HTTP status an engine failed with: openai's ``status_code``, Google's ``code``."""
    for error in _chain(exc):
        for attribute in ("status_code", "code"):
            value = getattr(error, attribute, None)
            if isinstance(value, int) and value in _HTTP_ERROR_RANGE:
                return value
    return None


def _is_network_error(exc: BaseException) -> bool:
    return any(isinstance(error, _NETWORK_ERRORS) for error in _chain(exc))


def is_provider_failure(exc: BaseException) -> bool:
    """True when the engine failed, so another engine could still answer."""
    return _http_status(exc) is not None or _is_network_error(exc)


def is_rate_limited(exc: BaseException) -> bool:
    """True for a quota that clears by waiting — not for spent credit."""
    return _http_status(exc) == _RATE_LIMIT or "rate limit" in str(exc).lower()


def _rest_seconds(exc: BaseException) -> float | None:
    status = _http_status(exc)
    if status in _ACCOUNT_STATUSES:
        return LLM_ACCOUNT_COOLDOWN_SECONDS
    if status in _TRANSIENT_STATUSES or (status or 0) >= _FIRST_SERVER_ERROR or _is_network_error(exc):
        return LLM_TRANSIENT_COOLDOWN_SECONDS
    return None


def mark_unavailable(provider: LLMProvider, exc: BaseException) -> None:
    """Rest ``provider`` after it failed with ``exc``, for as long as that failure warrants."""
    global _resting_until
    seconds = _rest_seconds(exc)
    if seconds is None:
        return
    _resting_until = {**_resting_until, provider.name: time.monotonic() + seconds}
    logger.warning("llm.provider_resting", provider=provider.name, seconds=seconds, status=_http_status(exc))


def message_text(message: BaseMessage | None) -> str:
    """What the model said, as clean text.

    ``str(message.content)`` is wrong for engines that answer in content blocks
    (Gemini does): it renders a Python list. ``.text`` joins the text blocks.
    Inline reasoning is dropped, with or without its opening tag.
    """
    if message is None:
        return ""
    return message.text.rpartition(_REASONING_END)[2].strip()
