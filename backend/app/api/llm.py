"""LLM provider — Groq.

The agent runs on Groq (free, no card, Llama 3.3 70B), whose model supports the
function calling the agentic loop depends on.  Get a free key at
https://console.groq.com and set ``GROQ_API_KEY``.

Kept behind ``build_chat_llm()`` so the agent loop never imports a concrete
client directly.
"""

from __future__ import annotations

import os

import structlog

from app.config import GROQ_MODEL_NAME, LLM_TEMPERATURE

logger = structlog.get_logger()


def build_chat_llm():
    """Construct the Groq chat model.

    Raises a clear error if ``GROQ_API_KEY`` is missing so misconfiguration
    fails loudly at startup rather than silently degrading.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
            "and add GROQ_API_KEY=... to backend/.env"
        )

    from langchain_groq import ChatGroq

    llm = ChatGroq(
        model=GROQ_MODEL_NAME,
        temperature=LLM_TEMPERATURE,
        api_key=os.getenv("GROQ_API_KEY"),
    )
    logger.info("llm.provider_selected", provider="groq", model=GROQ_MODEL_NAME)
    return llm
