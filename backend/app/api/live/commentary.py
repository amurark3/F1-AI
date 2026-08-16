"""LLM-generated commentary for live race events, with template fallbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

import asyncio
import threading

import structlog

from app.api.llm import build_chat_llm

logger = structlog.get_logger()

# Per-room commentary state — keyed by "{year}-{round_num}"
_commentary_state: dict[str, dict] = {}
COMMENTARY_COOLDOWN_SECONDS = 30

_commentary_llm_lock = threading.Lock()
# Built on first use. Without this binding the `global` in `_get_commentary_llm`
# had nothing to read, so every call raised NameError into the caller's fallback
# and commentary was silently template-only.
_commentary_llm: BaseChatModel | None = None


def _get_commentary_llm() -> BaseChatModel:
    """Return the shared commentary model, constructing it on first use."""
    global _commentary_llm
    if _commentary_llm is None:
        with _commentary_llm_lock:
            if _commentary_llm is None:
                _commentary_llm = build_chat_llm()
    return _commentary_llm


async def _generate_commentary(event: dict, race_name: str) -> str:
    """
    Generate 2-3 sentences of excited-commentator copy for a live race event.
    Wrapped in asyncio.to_thread so it does not block the WebSocket event loop.
    Falls back to a template string on any LLM error.
    """
    event_type = event["type"]

    if event_type == "safety_car":
        prompt = (
            f"You are an excited F1 race commentator at {race_name}. "
            f"The {event['status']} has just been deployed. "
            "Write 2-3 energetic, fan-friendly sentences explaining what this means for the race. "
            "No technical jargon."
        )
    elif event_type == "position_change":
        top5 = event.get("positions", [])
        top5_str = ", ".join(f"P{p['position']} #{p['driver']}" for p in top5)
        prompt = (
            f"You are an excited F1 race commentator at {race_name}. "
            f"Driver #{event['driver']} just moved from P{event['from_pos']} to P{event['to_pos']}. "
            f"Current top 5: {top5_str}. "
            "Write 2-3 energetic, fan-friendly sentences. No technical jargon."
        )
    elif event_type == "pit_stop":
        prompt = (
            f"You are an excited F1 race commentator at {race_name}. "
            f"Driver #{event['driver']} just pitted (stop #{event['pit_count']}), "
            f"currently P{event['position']} after the stop. "
            "Write 2-3 energetic, fan-friendly sentences. No technical jargon."
        )
    else:
        return ""

    try:
        response = await asyncio.to_thread(_get_commentary_llm().invoke, prompt)
        return response.content.strip()
    except Exception as e:
        logger.exception("commentary.llm_error", error=str(e))
        # Template fallback
        if event_type == "safety_car":
            return f"Safety car out at {race_name}! The field bunches up and strategy windows open!"
        if event_type == "position_change":
            return f"Position change! Driver #{event['driver']} moves to P{event['to_pos']}!"
        if event_type == "pit_stop":
            return f"Driver #{event['driver']} dives into the pits for stop #{event['pit_count']}!"
        return ""
