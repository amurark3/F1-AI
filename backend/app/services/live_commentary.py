"""Live-race commentary: event detection and narration.

Compares successive timing snapshots, picks the most newsworthy change, and
asks the LLM to narrate it. Falls back to a template when the LLM is
unavailable so a broadcast never goes silent.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx
import structlog

from app.api.llm import build_chat_llm

logger = structlog.get_logger()

# Room -> last-broadcast bookkeeping, so an event is narrated only once.
_state: dict[str, dict] = {}
COMMENTARY_COOLDOWN_SECONDS = 30


async def fetch_session_status(session_key: int) -> str:
    """
    Poll OpenF1 /v1/race_control for the most recent safety car or flag event.
    Returns a normalized status string: "safety car", "vsc", "red flag", or "".
    """
    try:
        url = f"https://api.openf1.org/v1/race_control?session_key={session_key}&category=SafetyCar,Flag"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            messages = resp.json()
        if not messages:
            return ""
        # Messages are in chronological order; take the last one
        latest = messages[-1]
        msg = (latest.get("message") or "").lower()
        flag = (latest.get("flag") or "").lower()
        if "safety car" in msg or flag == "safety car":
            return "safety car"
        if "virtual safety car" in msg or flag == "virtual safety car":
            return "vsc"
        if "red flag" in msg or flag == "red":
            return "red flag"
        return ""
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("commentary.race_control_fetch_error", error=str(e))
        return ""


async def fetch_stint_counts(session_key: int) -> dict[str, int]:
    """
    Poll OpenF1 /v1/stints for current session.
    Returns a dict mapping driver_number (str) to number of stints (proxy for pit stops).
    A driver on stint 2 has made 1 pit stop, stint 3 = 2 pit stops, etc.
    """
    try:
        url = f"https://api.openf1.org/v1/stints?session_key={session_key}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            stints = resp.json()
        counts: dict[str, int] = {}
        for stint in stints:
            drv = str(stint.get("driver_number", ""))
            if drv:
                counts[drv] = max(counts.get(drv, 0), stint.get("stint_number", 1))
        return counts
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("commentary.stints_fetch_error", error=str(e))
        return {}


def detect_event(
    prev_positions: list[dict],
    curr_positions: list[dict],
    prev_session_status: str,
    curr_session_status: str,
    prev_stints: dict[str, int],
    curr_stints: dict[str, int],
) -> dict | None:
    """
    Compare successive snapshots and return the highest-priority event dict, or None.
    Priority: (1) safety car / red flag, (2) position change, (3) pit stop.
    """
    # 1. Safety car / red flag
    if curr_session_status and curr_session_status != prev_session_status and curr_session_status.lower() in (
        "safety car", "vsc", "virtual safety car", "red flag"
    ):
        return {"type": "safety_car", "status": curr_session_status}

    # Build lookup maps
    curr_map = {p["driver"]: p for p in curr_positions}
    prev_map = {p["driver"]: p for p in prev_positions}

    # 2. Position change (any driver moved at least 1 place)
    for driver, curr in curr_map.items():
        prev = prev_map.get(driver)
        if prev and curr["position"] != prev["position"]:
            return {
                "type": "position_change",
                "driver": driver,
                "from_pos": prev["position"],
                "to_pos": curr["position"],
                "positions": curr_positions[:5],
            }

    # 3. Pit stop (stint count increased for any driver)
    for driver, curr_stint in curr_stints.items():
        prev_stint = prev_stints.get(driver, 1)
        if curr_stint > prev_stint:
            curr_pos = curr_map.get(driver, {}).get("position", "?")
            return {
                "type": "pit_stop",
                "driver": driver,
                "pit_count": curr_stint - 1,  # stints = pit_stops + 1
                "position": curr_pos,
            }

    return None


async def generate_commentary(event: dict, race_name: str) -> str:
    """
    Call Gemini to generate 2-3 sentence excited-commentator commentary.
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

    # Deliberately broad: this runs inside the live WebSocket loop, and no
    # provider-specific failure is worth dropping a viewer's connection over.
    # The template fallback below keeps the broadcast going.
    try:
        chat = build_chat_llm()
        response = await asyncio.to_thread(chat.invoke, prompt)
        return response.content.strip()
    except Exception as e:
        logger.error("commentary.llm_error", error=str(e))
        # Template fallback
        if event_type == "safety_car":
            return f"Safety car out at {race_name}! The field bunches up and strategy windows open!"
        elif event_type == "position_change":
            return f"Position change! Driver #{event['driver']} moves to P{event['to_pos']}!"
        elif event_type == "pit_stop":
            return f"Driver #{event['driver']} dives into the pits for stop #{event['pit_count']}!"
        return ""


def _empty_state() -> dict:
    return {
        "last_time": 0.0,
        "prev_positions": [],
        "prev_session_status": "",
        "prev_stints": {},
    }


def reset_room(room: str) -> None:
    """Drop a room's history, so a new session starts without stale comparisons."""
    _state.pop(room, None)


async def next_commentary(room: str, session_key: str, event_name: str, positions: list[dict]) -> dict | None:
    """Narrate the most newsworthy change since the last poll, or return None.

    Owns the per-room snapshot history: callers pass timing rows in and get a
    ready-to-send payload out.
    """
    status, stints = await asyncio.gather(
        fetch_session_status(session_key),
        fetch_stint_counts(session_key),
    )
    previous = _state.get(room)

    if previous is None or not previous["prev_positions"]:
        # First snapshot — record it and skip detection to avoid false positives
        _state[room] = {**_empty_state(), "prev_positions": positions,
                        "prev_session_status": status, "prev_stints": stints}
        return None

    payload = None
    last_time = previous["last_time"]
    if time.time() - last_time >= COMMENTARY_COOLDOWN_SECONDS:
        event = detect_event(
            previous["prev_positions"], positions,
            previous["prev_session_status"], status,
            previous["prev_stints"], stints,
        )
        if event:
            text = await generate_commentary(event, event_name)
            if text:
                payload = {
                    "id": str(time.time()),
                    "text": text,
                    "event_type": event["type"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                last_time = time.time()

    _state[room] = {
        "last_time": last_time,
        "prev_positions": positions,
        "prev_session_status": status,
        "prev_stints": stints,
    }
    return payload
