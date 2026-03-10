"""
API Routes
==========
Defines all HTTP endpoints for the F1 AI backend:

  POST /api/chat                       — Streaming AI chat with tool orchestration
  GET  /api/schedule/{year}            — Full season calendar with UTC session times
  GET  /api/race/{year}/{round_num}    — Enriched race detail (circuit, results, qualifying)
  GET  /api/standings/drivers/{year}   — World Drivers' Championship standings
  GET  /api/standings/constructors/{year} — World Constructors' Championship standings
  GET  /api/health                     — Liveness probe

The chat endpoint implements an agentic loop:
  1. Build message history with system prompt.
  2. Call the LLM; it may request one or more tools.
  3. Execute every requested tool and append results to history.
  4. Repeat until the model produces a plain-text final answer (or max_turns is reached).
  5. Stream the final text back to the client.
"""

import os
import math
import asyncio
import threading
import structlog
import pandas as pd
import fastf1
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from fastapi.responses import StreamingResponse
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from fastf1.ergast import Ergast

from app.api.tools import TOOL_LIST, TOOL_MAP
from app.api.prompts import RACE_ENGINEER_PERSONA
from app.api.circuits import get_circuit_info
from app.data.predictions import compute_race_predictions
from app.config import (
    TOOL_TIMEOUT_SECONDS,
    FASTF1_TIMEOUT_SECONDS,
    OPENF1_HTTP_TIMEOUT_SECONDS,
    WS_RECEIVE_TIMEOUT,
    WS_HEARTBEAT_INTERVAL,
    WS_STALE_TIMEOUT,
    WS_POLL_INTERVAL,
    MAX_AGENT_TURNS,
    LLM_MODEL_NAME,
    LLM_TEMPERATURE,
)

logger = structlog.get_logger()

router = APIRouter()


def _safe_int(value, default: int = 0) -> int:
    """Convert Ergast/FastF1 values to int, treating NaN/None as default.

    Ergast returns NaN for position fields when a driver DNF'd, didn't start,
    or is a reserve entry with no championship standing. Calling int() on NaN
    raises ValueError. Use this everywhere you read a numeric field from an
    Ergast DataFrame row.
    """
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return int(value)

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
# Safety settings tuned for F1 domain content:
#
# DANGEROUS_CONTENT: BLOCK_ONLY_HIGH — F1 legitimately discusses crashes, fires,
#   driver injuries, and safety incidents (e.g. "the crash at Copse", "driver
#   hospitalization after impact"). Blocking at medium would break core functionality.
#
# HARASSMENT: BLOCK_ONLY_HIGH — F1 coverage includes team rivalries, driver
#   criticism, steward decisions, and heated radio messages. These are normal
#   sporting discourse, not harassment.
#
# HATE_SPEECH: BLOCK_MEDIUM_AND_ABOVE — Not relevant to F1 content. Can apply
#   stricter filtering without impacting legitimate queries.
#
# SEXUALLY_EXPLICIT: BLOCK_MEDIUM_AND_ABOVE — Not relevant to F1 content. Can
#   apply stricter filtering without impacting legitimate queries.
#
# Defense-in-depth: The system prompt in prompts.py has strong identity guardrails
# that refuse all non-F1 topics, so these safety settings are a secondary layer.
llm = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME,
    temperature=LLM_TEMPERATURE,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
)

# Bind all available tools so the model can call them by name.
llm_with_tools = llm.bind_tools(TOOL_LIST)

# ---------------------------------------------------------------------------
# FastF1 cache — speeds up repeated session data requests significantly.
# ---------------------------------------------------------------------------
if not os.path.exists("f1_cache"):
    os.makedirs("f1_cache")
fastf1.Cache.enable_cache("f1_cache")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """Payload expected by POST /api/chat."""
    messages: List[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint that drives an agentic tool-use loop.

    The client should read the response as a plain-text stream (text/plain).
    Each chunk is a fragment of the final assistant message.
    """
    today = datetime.now().strftime("%B %d, %Y")

    # Build a system prompt that injects today's date and tool-usage rules.
    final_system_prompt = f"""
    {RACE_ENGINEER_PERSONA}

    CURRENT CONTEXT:
    - TODAY'S DATE: {today}

    TOOL USAGE:
    - **CRITICAL:** If the user asks for "last race", "next race", or "schedule",
      ALWAYS call `get_season_schedule({today.split(',')[-1].strip()})` FIRST to
      identify the correct Grand Prix name before calling any results tool.
    - Use 'get_race_results' for final race classifications.
    - Use 'compare_drivers' for specific lap-time comparisons.
    - Use 'perform_web_search' for recent news or information beyond your knowledge.
    - If a tool returns a Markdown table, present it exactly as-is.
    """

    # Seed the message history with the system prompt, then replay the
    # conversation so the model has full context.
    langchain_messages = [SystemMessage(content=final_system_prompt)]

    for msg in request.messages:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))

    async def generate():
        """
        Inner async generator that drives the agentic loop and yields text chunks.

        The loop runs at most `max_turns` times to prevent runaway tool calls.
        Each turn is one of:
          - CASE A: Model requests tools  → execute them, append results, continue.
          - CASE B: Model returns text    → stream it to the client, break.
        """
        try:
            max_turns = MAX_AGENT_TURNS
            turn_count = 0

            logger.info("agent.invoking_model")
            current_response = await llm_with_tools.ainvoke(langchain_messages)

            while turn_count < max_turns:
                turn_count += 1

                if current_response.tool_calls:
                    # CASE A — model wants to call tools
                    logger.info("agent.turn", turn=turn_count, tool_count=len(current_response.tool_calls))

                    # Append the AI's "intent" message before tool results;
                    # LangChain requires this ordering in the message list.
                    langchain_messages.append(current_response)

                    for tool_call in current_response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]

                        if tool_name in TOOL_MAP:
                            # Stream a tool-start indicator so the frontend
                            # can show the user what's happening.
                            friendly = tool_name.replace("_", " ").title()
                            yield f"[TOOL_START]{friendly}[/TOOL_START]"

                            logger.info("tool.executing", tool=tool_name, args=tool_args)
                            try:
                                tool_result = await asyncio.wait_for(
                                    asyncio.to_thread(TOOL_MAP[tool_name].invoke, tool_args),
                                    timeout=TOOL_TIMEOUT_SECONDS,
                                )
                                logger.debug("tool.result", tool=tool_name, preview=str(tool_result)[:80])
                            except asyncio.TimeoutError:
                                tool_result = f"Tool '{tool_name}' timed out after {TOOL_TIMEOUT_SECONDS} seconds. The data source may be slow — try again."
                                logger.warning("tool.timeout", tool=tool_name, timeout_seconds=TOOL_TIMEOUT_SECONDS)
                            except Exception as tool_err:
                                # Surface the error as a tool message so the model
                                # can decide how to handle it gracefully.
                                tool_result = f"Error executing tool '{tool_name}': {tool_err}"
                                logger.error("tool.error", tool=tool_name, error=str(tool_err))

                            langchain_messages.append(
                                ToolMessage(
                                    tool_call_id=tool_id,
                                    content=str(tool_result),
                                    name=tool_name,
                                )
                            )

                            yield f"[TOOL_END]{friendly}[/TOOL_END]"

                    # Ask the model what to do next given the tool results.
                    current_response = await llm_with_tools.ainvoke(langchain_messages)

                else:
                    # CASE B — model has a final text answer; stream it.
                    logger.info("agent.generating_response")
                    yield current_response.content
                    return  # Exit the generator cleanly

            # If we exhausted max_turns without a text answer, tell the user.
            yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."

        except Exception as e:
            logger.error("agent.critical_error", error=str(e))
            yield f"**System Error:** My telemetry failed. Reason: {e}"

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/schedule/{year}")
async def get_schedule(year: int):
    """
    Returns the full season schedule for `year` with UTC timestamps.

    Each event includes all sessions (Practice 1-3, Qualifying, Sprint,
    Sprint Qualifying, Race) when available. Sprint weekends are detected
    automatically by FastF1.

    The frontend is responsible for converting UTC times to the user's timezone.
    """
    try:
        # include_testing=False omits pre-season test events.
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)

        data = []
        for _, row in schedule.iterrows():
            # Ensure the event date is always UTC-suffixed for JS Date parsing.
            event_date_str = row["EventDate"].isoformat()
            if not event_date_str.endswith("Z") and "+" not in event_date_str:
                event_date_str += "Z"

            location_str = f"{row['Location']}, {row['Country']}"

            event = {
                "round": int(row["RoundNumber"]),
                "name": row["EventName"],
                "location": location_str,
                "date": event_date_str,
                "sessions": {},
                "circuit": get_circuit_info(location_str),
            }

            # FastF1 uses Session1…Session5 columns; iterate to capture all
            # sessions including sprints without hard-coding session names.
            first_session_date = None
            last_session_date = None
            for i in range(1, 6):
                s_name_col = f"Session{i}"
                s_date_col = f"Session{i}DateUtc"

                if s_name_col in row and pd.notna(row[s_name_col]):
                    session_name = row[s_name_col]
                    session_date = row[s_date_col]
                    if pd.notna(session_date):
                        event["sessions"][session_name] = session_date.isoformat()
                        ts = session_date.to_pydatetime()
                        if first_session_date is None or ts < first_session_date:
                            first_session_date = ts
                        if last_session_date is None or ts > last_session_date:
                            last_session_date = ts

            # Detect sprint weekend
            event["is_sprint"] = "Sprint" in event["sessions"]

            # Determine event status relative to current UTC time.
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            if last_session_date and now_utc > last_session_date + pd.Timedelta(hours=3):
                event["status"] = "completed"
            elif first_session_date and now_utc >= first_session_date:
                event["status"] = "in_progress"
            else:
                event["status"] = "upcoming"

            data.append(event)

        return data

    except Exception as e:
        return {"error": str(e)}


@router.get("/standings/drivers/{year}")
async def get_driver_standings(year: int):
    """
    Returns World Drivers' Championship standings for `year`.

    Each entry contains: position, driver full name, team, points, wins.

    Note: A driver who switched teams mid-season will have multiple
    constructor names; we take the most recent (last) one.
    """
    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        if data.content:
            df = data.content[0]
            results = []
            for _, row in df.iterrows():
                # Skip entries with no position (reserve/non-racing drivers)
                if "position" not in row or (isinstance(row["position"], float) and math.isnan(row["position"])):
                    continue

                # FastF1/Ergast returns either 'constructorName' (string) for
                # single-team drivers, or 'constructorNames' (list) for drivers
                # who raced for multiple teams in one season.
                team_name = "Unknown"
                if "constructorName" in row:
                    team_name = row["constructorName"]
                elif "constructorNames" in row:
                    names = row["constructorNames"]
                    team_name = names[-1] if isinstance(names, list) and names else str(names)

                results.append({
                    "position": _safe_int(row["position"]),
                    "driver": f"{row['givenName']} {row['familyName']}",
                    "team": team_name,
                    "points": float(row["points"]),
                    "wins": int(row["wins"]),
                })
            return results

        # No standings yet (season hasn't started) — build a placeholder
        # entry list by querying each constructor's drivers for the season.
        constructors_df = ergast.get_constructor_info(season=year)
        if constructors_df.empty:
            return []

        results = []
        pos = 1
        for _, crow in constructors_df.iterrows():
            cid = crow["constructorId"]
            team_name = crow["constructorName"]
            drivers_df = ergast.get_driver_info(season=year, constructor=cid)
            for _, drow in drivers_df.iterrows():
                results.append({
                    "position": pos,
                    "driver": f"{drow['givenName']} {drow['familyName']}",
                    "team": team_name,
                    "points": 0.0,
                    "wins": 0,
                })
                pos += 1
        return results

    except Exception as e:
        logger.error("api.driver_standings.error", error=str(e))
        return []


@router.get("/standings/constructors/{year}")
async def get_constructor_standings(year: int):
    """
    Returns World Constructors' Championship standings for `year`.

    Each entry contains: position, team name, points, wins.
    """
    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        if data.content:
            df = data.content[0]
            results = []
            for _, row in df.iterrows():
                if "position" not in row or (isinstance(row["position"], float) and math.isnan(row["position"])):
                    continue
                results.append({
                    "position": _safe_int(row["position"]),
                    "team": row["constructorName"],
                    "points": float(row["points"]),
                    "wins": int(row["wins"]),
                })
            return results

        # No standings yet (season hasn't started) — return the entry list
        # from the Ergast constructor info endpoint with 0 points.
        constructors_df = ergast.get_constructor_info(season=year)
        if constructors_df.empty:
            return []

        results = []
        for idx, (_, row) in enumerate(constructors_df.iterrows(), start=1):
            results.append({
                "position": idx,
                "team": row["constructorName"],
                "points": 0.0,
                "wins": 0,
            })
        return results

    except Exception as e:
        logger.error("api.constructor_standings.error", error=str(e))
        return []



# ---------------------------------------------------------------------------
# In-memory cache for race detail — populated by background prefetch and
# on-demand requests.  Keyed by (year, round_num).
# ---------------------------------------------------------------------------
race_detail_cache: dict[tuple[int, int], dict] = {}

# Predictions cache — keyed by (year, round_num), same pattern as race_detail_cache.
predictions_cache: dict[tuple[int, int], dict] = {}

# Per-room commentary state — keyed by "{year}-{round_num}"
_commentary_state: dict[str, dict] = {}
COMMENTARY_COOLDOWN_SECONDS = 30

# Only allow ONE FastF1 session load at a time — they are heavy I/O and
# FastF1 itself is not thread-safe for concurrent session loads.
_fastf1_lock = threading.Lock()


def _fmt_td(time_val) -> str:
    """Convert a pandas Timedelta to a clean lap-time string."""
    if pd.isna(time_val):
        return "-"
    s = str(time_val).split("days")[-1].strip()
    if s.startswith("00:"):
        s = s[3:]
    if len(s) > 10:
        s = s[:9]
    return s


def _build_race_detail_sync(year: int, round_num: int) -> dict:
    """
    Synchronous helper that loads enriched race data from FastF1.

    Returns a dict with circuit info, race results, qualifying, and podium.
    Called via asyncio.to_thread() to avoid blocking the event loop.
    """
    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    event_row = schedule[schedule["RoundNumber"] == round_num]
    if event_row.empty:
        return {"error": f"Round {round_num} not found for {year}"}

    row = event_row.iloc[0]
    location_str = f"{row['Location']}, {row['Country']}"

    # Event date
    event_date_str = row["EventDate"].isoformat()
    if not event_date_str.endswith("Z") and "+" not in event_date_str:
        event_date_str += "Z"

    # Sessions
    sessions = {}
    for i in range(1, 6):
        s_name_col = f"Session{i}"
        s_date_col = f"Session{i}DateUtc"
        if s_name_col in row and pd.notna(row[s_name_col]):
            session_date = row[s_date_col]
            if pd.notna(session_date):
                sessions[row[s_name_col]] = session_date.isoformat()

    # Circuit info
    circuit = get_circuit_info(location_str)

    # Detect sprint weekend
    session_names = [row[f"Session{i}"] for i in range(1, 6) if f"Session{i}" in row and pd.notna(row[f"Session{i}"])]
    is_sprint_weekend = "Sprint" in session_names

    result = {
        "round": round_num,
        "name": row["EventName"],
        "location": location_str,
        "date": event_date_str,
        "sessions": sessions,
        "circuit": circuit,
        "race_results": None,
        "qualifying": None,
        "podium": None,
        "is_sprint": is_sprint_weekend,
        "sprint_results": None,
        "sprint_qualifying": None,
    }

    # Determine if the race is completed
    race_session_date = None
    for i in range(1, 6):
        s_name_col = f"Session{i}"
        s_date_col = f"Session{i}DateUtc"
        if s_name_col in row and row[s_name_col] == "Race" and pd.notna(row[s_date_col]):
            race_session_date = row[s_date_col].to_pydatetime()
            break

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    is_completed = race_session_date and now_utc > race_session_date + pd.Timedelta(hours=3)

    if not is_completed:
        return result

    # --- Load race results ---
    try:
        with _fastf1_lock:
            race_session = fastf1.get_session(year, round_num, "R")
            race_session.load(telemetry=False, laps=False, weather=False)
        race_results = race_session.results.sort_values(by="Position")

        results_list = []
        for _, r in race_results.iterrows():
            pos = int(r["Position"]) if pd.notna(r["Position"]) else None
            grid = int(r["GridPosition"]) if pd.notna(r["GridPosition"]) and r["GridPosition"] > 0 else None

            # Format time/gap
            status = r["Status"]
            time_val = r["Time"]
            if status == "Finished":
                if pd.notna(time_val):
                    t_str = str(time_val).split("days")[-1].strip()
                    if "." in t_str:
                        t_str = t_str[:t_str.find(".") + 4]
                    if t_str.startswith("00:"):
                        t_str = t_str[3:]
                    time_str = t_str
                else:
                    time_str = ""
            elif "Lap" in status:
                time_str = status
            else:
                time_str = f"DNF - {status}"

            results_list.append({
                "position": pos,
                "driver": r["Abbreviation"],
                "full_name": f"{r['FirstName']} {r['LastName']}",
                "team": r["TeamName"],
                "grid": grid,
                "time": time_str,
                "points": float(r["Points"]) if pd.notna(r["Points"]) else 0,
                "status": status,
            })

        result["race_results"] = results_list

        # Build podium (top 3)
        podium = [r for r in results_list if r["position"] and r["position"] <= 3]
        podium.sort(key=lambda x: x["position"])
        result["podium"] = podium

    except Exception as e:
        logger.error("api.race_results.load_error", year=year, round=round_num, error=str(e))

    # --- Load qualifying results ---
    try:
        with _fastf1_lock:
            quali_session = fastf1.get_session(year, round_num, "Q")
            quali_session.load(telemetry=False, laps=False, weather=False)
        quali_results = quali_session.results

        qualifying = {}
        for q_label in ["Q1", "Q2", "Q3"]:
            if q_label in quali_results.columns:
                q_df = quali_results[quali_results[q_label].notna()].sort_values(by=q_label)
                q_list = []
                for i, (_, r) in enumerate(q_df.iterrows(), 1):
                    q_list.append({
                        "position": i,
                        "driver": r["Abbreviation"],
                        "full_name": f"{r['FirstName']} {r['LastName']}",
                        "team": r["TeamName"],
                        "time": _fmt_td(r[q_label]),
                    })
                if q_list:
                    qualifying[q_label] = q_list

        result["qualifying"] = qualifying if qualifying else None

    except Exception as e:
        logger.error("api.qualifying.load_error", year=year, round=round_num, error=str(e))

    # --- Load sprint results (sprint weekends only) ---
    if is_sprint_weekend:
        # Sprint race results
        try:
            with _fastf1_lock:
                sprint_session = fastf1.get_session(year, round_num, "S")
                sprint_session.load(telemetry=False, laps=False, weather=False)
            sprint_results = sprint_session.results.sort_values(by="Position")

            sprint_list = []
            for _, r in sprint_results.iterrows():
                pos = int(r["Position"]) if pd.notna(r["Position"]) else None
                grid = int(r["GridPosition"]) if pd.notna(r["GridPosition"]) and r["GridPosition"] > 0 else None

                status = r["Status"]
                time_val = r["Time"]
                if status == "Finished":
                    time_str = _fmt_td(time_val) if pd.notna(time_val) else ""
                elif "Lap" in status:
                    time_str = status
                else:
                    time_str = f"DNF - {status}"

                sprint_list.append({
                    "position": pos,
                    "driver": r["Abbreviation"],
                    "full_name": f"{r['FirstName']} {r['LastName']}",
                    "team": r["TeamName"],
                    "grid": grid,
                    "time": time_str,
                    "points": float(r["Points"]) if pd.notna(r["Points"]) else 0,
                    "status": status,
                })

            result["sprint_results"] = sprint_list if sprint_list else None

        except Exception as e:
            logger.error("api.sprint_results.load_error", year=year, round=round_num, error=str(e))

        # Sprint qualifying results
        try:
            with _fastf1_lock:
                sq_session = fastf1.get_session(year, round_num, "SQ")
                sq_session.load(telemetry=False, laps=False, weather=False)
            sq_results = sq_session.results

            sprint_quali = {}
            for sq_label in ["Q1", "Q2", "Q3"]:
                if sq_label in sq_results.columns:
                    sq_df = sq_results[sq_results[sq_label].notna()].sort_values(by=sq_label)
                    sq_list = []
                    for i, (_, r) in enumerate(sq_df.iterrows(), 1):
                        sq_list.append({
                            "position": i,
                            "driver": r["Abbreviation"],
                            "full_name": f"{r['FirstName']} {r['LastName']}",
                            "team": r["TeamName"],
                            "time": _fmt_td(r[sq_label]),
                        })
                    if sq_list:
                        sprint_quali[sq_label] = sq_list

            result["sprint_qualifying"] = sprint_quali if sprint_quali else None

        except Exception as e:
            logger.error("api.sprint_qualifying.load_error", year=year, round=round_num, error=str(e))

    return result


# Per-request timeout for building race detail (seconds).
# Generous because the lock means requests queue up sequentially.
FASTF1_TIMEOUT = FASTF1_TIMEOUT_SECONDS


@router.get("/race/{year}/{round_num}")
async def get_race_detail(year: int, round_num: int):
    """
    Returns enriched race data: circuit info, race results, qualifying.

    Results are cached in memory — first request may be slow (~5-15s) as
    FastF1 loads session data, subsequent requests are instant.
    A 60-second timeout prevents hanging requests.  A threading lock ensures
    only one FastF1 session loads at a time.
    """
    cache_key = (year, round_num)

    if cache_key in race_detail_cache:
        return race_detail_cache[cache_key]

    try:
        detail = await asyncio.wait_for(
            asyncio.to_thread(_build_race_detail_sync, year, round_num),
            timeout=FASTF1_TIMEOUT,
        )
        # Cache if we got at least circuit info (even without results)
        if detail.get("circuit") is not None:
            race_detail_cache[cache_key] = detail
        return detail
    except asyncio.TimeoutError:
        logger.warning("api.race_detail.timeout", year=year, round=round_num, timeout_seconds=FASTF1_TIMEOUT)
        return {"error": "Request timed out loading race data. Try again later.", "timeout": True}
    except Exception as e:
        logger.error("api.race_detail.error", error=str(e))
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Live timing WebSocket
# ---------------------------------------------------------------------------
# Polls OpenF1 API and fans out position/timing updates to connected clients.

import time
import httpx


# ---------------------------------------------------------------------------
# WebSocket Connection Manager — heartbeat + stale connection cleanup
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Manages WebSocket connections with heartbeat pings and stale cleanup.

    Tracks active connections per room and last activity time per connection.
    Heartbeat pings are application-level JSON (not WebSocket protocol pings)
    since the client may not handle protocol pings.
    """

    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}
        self.last_activity: dict[int, float] = {}  # id(ws) -> timestamp

    async def connect(self, room: str, ws: WebSocket) -> None:
        """Accept a WebSocket and register it in the room."""
        await ws.accept()
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(ws)
        self.last_activity[id(ws)] = time.time()
        logger.info("ws.connected", room=room, connection_id=id(ws))

    def disconnect(self, room: str, ws: WebSocket) -> None:
        """Remove a WebSocket from tracking."""
        if room in self.rooms:
            self.rooms[room] = [c for c in self.rooms[room] if c != ws]
            if not self.rooms[room]:
                del self.rooms[room]
        self.last_activity.pop(id(ws), None)
        logger.info("ws.disconnected", room=room, connection_id=id(ws))

    def touch(self, ws: WebSocket) -> None:
        """Update last activity timestamp for a connection."""
        self.last_activity[id(ws)] = time.time()

    def is_stale(self, ws: WebSocket) -> bool:
        """Check if a connection has been inactive beyond the stale timeout."""
        last = self.last_activity.get(id(ws), 0)
        return (time.time() - last) > WS_STALE_TIMEOUT

    async def heartbeat(self, ws: WebSocket) -> None:
        """Send periodic JSON pings to keep the connection alive.

        Runs until the WebSocket is closed or a send failure occurs.
        """
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                await ws.send_json({"type": "ping"})
                logger.debug("ws.heartbeat_sent", connection_id=id(ws))
        except Exception:
            # Connection closed or send failed -- caller handles cleanup
            pass


manager = ConnectionManager()


# Cache driver info per session to avoid re-fetching every poll cycle
_driver_cache: dict[str, dict[int, dict]] = {}


async def _poll_openf1_positions(session_key: str) -> list[dict] | None:
    """Fetch latest positions, gaps, and driver names from OpenF1 API."""
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            # Fetch driver info once per session, then cache
            if session_key not in _driver_cache:
                drv_resp = await client.get("https://api.openf1.org/v1/drivers", params={"session_key": session_key})
                if drv_resp.status_code == 200 and isinstance(drv_resp.json(), list):
                    _driver_cache[session_key] = {
                        d["driver_number"]: d for d in drv_resp.json() if "driver_number" in d
                    }

            pos_resp = await client.get("https://api.openf1.org/v1/position", params={"session_key": session_key})
            int_resp = await client.get("https://api.openf1.org/v1/intervals", params={"session_key": session_key})

        if pos_resp.status_code != 200:
            return None
        pos_data = pos_resp.json()
        if not isinstance(pos_data, list) or not pos_data:
            return None

        # Latest interval per driver
        intervals: dict[int, dict] = {}
        if int_resp.status_code == 200 and isinstance(int_resp.json(), list):
            for entry in int_resp.json():
                dn = entry.get("driver_number")
                if dn is not None:
                    intervals[dn] = entry

        drivers = _driver_cache.get(session_key, {})

        # Latest position per driver
        latest: dict[int, dict] = {}
        for entry in pos_data:
            dn = entry.get("driver_number")
            if dn is not None:
                latest[dn] = entry

        positions = []
        for dn, entry in sorted(latest.items(), key=lambda x: x[1].get("position", 99)):
            pos = entry.get("position", 0)
            interval = intervals.get(dn, {})
            gap_raw = interval.get("gap_to_leader")
            try:
                gap_float = float(gap_raw) if gap_raw is not None else None
            except (ValueError, TypeError):
                gap_float = None
            if pos == 1 or gap_float == 0.0:
                gap = "LEADER"
            elif gap_float is not None:
                gap = f"+{gap_float:.3f}"
            else:
                gap = "—"

            drv_info = drivers.get(dn, {})
            acronym = drv_info.get("name_acronym") or str(dn)

            positions.append({
                "position": pos,
                "driver": acronym,
                "gap": gap,
                "last_lap": None,
                "sector1": None,
                "sector2": None,
                "sector3": None,
                "tyre": None,
                "pit_stops": None,
            })
        return positions
    except Exception as e:
        logger.error("openf1.poll_error", error=str(e))
        return None


async def _fetch_current_lap(session_key: str) -> int:
    """
    Fetch the highest completed lap number for the session from OpenF1 /v1/laps.
    Returns 0 on failure or empty response.
    """
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.openf1.org/v1/laps",
                params={"session_key": session_key},
            )
            if resp.status_code != 200:
                return 0
            data = resp.json()
            if not data:
                return 0
            # Take the maximum lap_number across all drivers' lap entries
            lap_nums = [entry.get("lap_number", 0) for entry in data if entry.get("lap_number")]
            return max(lap_nums) if lap_nums else 0
    except Exception as e:
        logger.warning("openf1.laps_fetch_error", error=str(e))
        return 0


async def _find_openf1_session(year: int, round_num: int) -> tuple[str, int] | None:
    """Find the session key and total laps for a specific race round from OpenF1."""
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            # Step 1: find the meeting_key for this round
            meetings_resp = await client.get(
                "https://api.openf1.org/v1/meetings",
                params={"year": year},
            )
            if meetings_resp.status_code != 200:
                return None
            meetings = meetings_resp.json()
            # Sort by date; exclude testing events which shift round indices
            meetings_sorted = sorted(
                [m for m in meetings if "test" not in m.get("meeting_name", "").lower()],
                key=lambda m: m.get("date_start", ""),
            )
            if round_num < 1 or round_num > len(meetings_sorted):
                return None
            meeting_key = meetings_sorted[round_num - 1].get("meeting_key")
            if not meeting_key:
                return None

            # Step 2: find the Race session for that meeting
            sessions_resp = await client.get(
                "https://api.openf1.org/v1/sessions",
                params={"meeting_key": meeting_key, "session_type": "Race"},
            )
            if sessions_resp.status_code != 200:
                return None
            sessions = sessions_resp.json()
            for s in sessions:
                if s.get("session_key"):
                    total_laps = s.get("total_laps") or s.get("laps") or s.get("number_of_laps") or 0
                    return str(s["session_key"]), int(total_laps)
            return None
    except Exception:
        return None


@router.get("/compare/{year}/{driver1}/{driver2}")
async def compare_drivers_endpoint(year: int, driver1: str, driver2: str):
    """
    Head-to-head comparison of two drivers across the season.

    Returns qualifying battle, race battle, average positions, points,
    and per-round breakdown for charts.
    """
    try:
        result = await asyncio.to_thread(_build_comparison_sync, year, driver1, driver2)
        return result
    except asyncio.TimeoutError:
        return {"error": "Comparison timed out. Try again."}
    except Exception as e:
        return {"error": str(e)}


def _build_comparison_sync(year: int, driver1_query: str, driver2_query: str) -> dict:
    """Build season-long head-to-head stats for two drivers."""
    ergast = Ergast()

    # Resolve driver codes from standings
    standings_data = ergast.get_driver_standings(season=year)
    if not standings_data.content:
        return {"error": f"No standings data for {year}"}

    df = standings_data.content[0]

    def find_driver(query: str) -> dict | None:
        q = query.lower().strip()
        for _, row in df.iterrows():
            code = str(row.get("driverCode", "")).lower()
            family = str(row.get("familyName", "")).lower()
            given = str(row.get("givenName", "")).lower()
            if q == code or q in family or q in given:
                teams = row.get("constructorNames", row.get("constructorName", "Unknown"))
                team = teams[-1] if isinstance(teams, list) and teams else str(teams)
                return {
                    "code": str(row.get("driverCode", "")),
                    "name": f"{row.get('givenName', '')} {row.get('familyName', '')}",
                    "team": team,
                    "points": float(row.get("points", 0)),
                    "wins": int(row.get("wins", 0)),
                    "position": _safe_int(row.get("position", 0)),
                }
        return None

    d1 = find_driver(driver1_query)
    d2 = find_driver(driver2_query)

    if not d1 or not d2:
        return {"error": f"Could not find driver '{driver1_query}' or '{driver2_query}' in {year} standings."}

    # Get race results for each round to build head-to-head
    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    now_utc = datetime.now()

    quali_h2h = {"d1": 0, "d2": 0}
    race_h2h = {"d1": 0, "d2": 0}
    rounds = []

    d1_positions = []
    d2_positions = []

    for _, event in schedule.iterrows():
        race_date = event["EventDate"]
        if race_date > now_utc:
            break  # Skip future races

        round_num = int(event["RoundNumber"])
        gp_name = event["EventName"]

        round_data = {"round": round_num, "name": gp_name}

        # Try loading race results from Ergast (lighter than FastF1)
        try:
            race_data = ergast.get_race_results(season=year, round=round_num)
            if race_data.content:
                rdf = race_data.content[0]
                d1_row = rdf[rdf["driverCode"] == d1["code"]]
                d2_row = rdf[rdf["driverCode"] == d2["code"]]

                if not d1_row.empty and not d2_row.empty:
                    r1 = d1_row.iloc[0]["position"]
                    r2 = d2_row.iloc[0]["position"]
                    if (isinstance(r1, float) and math.isnan(r1)) or (isinstance(r2, float) and math.isnan(r2)):
                        rounds.append(round_data)
                        continue
                    d1_pos = int(r1)
                    d2_pos = int(r2)
                    round_data["d1_race"] = d1_pos
                    round_data["d2_race"] = d2_pos
                    d1_positions.append(d1_pos)
                    d2_positions.append(d2_pos)

                    if d1_pos < d2_pos:
                        race_h2h["d1"] += 1
                    elif d2_pos < d1_pos:
                        race_h2h["d2"] += 1
        except Exception:
            pass

        # Try qualifying
        try:
            quali_data = ergast.get_qualifying_results(season=year, round=round_num)
            if quali_data.content:
                qdf = quali_data.content[0]
                d1_q = qdf[qdf["driverCode"] == d1["code"]]
                d2_q = qdf[qdf["driverCode"] == d2["code"]]

                if not d1_q.empty and not d2_q.empty:
                    d1_qpos = _safe_int(d1_q.iloc[0]["position"])
                    d2_qpos = _safe_int(d2_q.iloc[0]["position"])
                    round_data["d1_quali"] = d1_qpos
                    round_data["d2_quali"] = d2_qpos

                    if d1_qpos < d2_qpos:
                        quali_h2h["d1"] += 1
                    elif d2_qpos < d1_qpos:
                        quali_h2h["d2"] += 1
        except Exception:
            pass

        rounds.append(round_data)

    return {
        "driver1": d1,
        "driver2": d2,
        "qualifying_h2h": quali_h2h,
        "race_h2h": race_h2h,
        "avg_race_position": {
            "d1": round(sum(d1_positions) / len(d1_positions), 1) if d1_positions else None,
            "d2": round(sum(d2_positions) / len(d2_positions), 1) if d2_positions else None,
        },
        "rounds": rounds,
    }


async def _fetch_session_status(session_key: int) -> str:
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
    except Exception as e:
        logger.warning("commentary.race_control_fetch_error", error=str(e))
        return ""


async def _fetch_stint_counts(session_key: int) -> dict[str, int]:
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
    except Exception as e:
        logger.warning("commentary.stints_fetch_error", error=str(e))
        return {}


def _detect_event(
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


async def _generate_commentary(event: dict, race_name: str) -> str:
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

    try:
        response = await asyncio.to_thread(llm.invoke, prompt)
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


@router.websocket("/live/{year}/{round_num}")
async def live_timing(websocket: WebSocket, year: int, round_num: int):
    """WebSocket endpoint for live race timing data.

    Uses ConnectionManager for heartbeat pings and stale connection cleanup.
    """
    room = f"{year}-{round_num}"
    await manager.connect(room, websocket)

    # Start heartbeat as a background task
    heartbeat_task = asyncio.create_task(manager.heartbeat(websocket))

    try:
        session_result = await _find_openf1_session(year, round_num)
        if session_result:
            session_key, total_laps = session_result
        else:
            session_key, total_laps = None, 0
        race_name = f"Round {round_num} {year}"  # fallback; sufficient for prompts
        last_known_lap = 0

        while True:
            # Check if connection is stale
            if manager.is_stale(websocket):
                logger.warning("ws.stale_connection", room=room, connection_id=id(websocket))
                break

            if session_key:
                positions = await _poll_openf1_positions(session_key)
                if positions:
                    await websocket.send_json({
                        "type": "positions",
                        "data": positions,
                    })
                    manager.touch(websocket)

                    # Fetch current lap and broadcast session_status
                    current_lap = await _fetch_current_lap(session_key)
                    if current_lap > 0:
                        last_known_lap = current_lap
                    await websocket.send_json({
                        "type": "session_status",
                        "data": {
                            "status": "started",
                            "lap": last_known_lap if last_known_lap > 0 else None,
                            "total_laps": total_laps if total_laps > 0 else None,
                        },
                    })
                    manager.touch(websocket)

                    # --- Commentary detection ---
                    # Fetch auxiliary data for event types not available in positions endpoint
                    curr_status, curr_stints = await asyncio.gather(
                        _fetch_session_status(session_key),
                        _fetch_stint_counts(session_key),
                    )

                    state = _commentary_state.setdefault(room, {
                        "last_time": 0.0,
                        "prev_positions": [],
                        "prev_session_status": "",
                        "prev_stints": {},
                    })

                    if not state["prev_positions"]:
                        # First snapshot — store and skip detection to avoid false positives
                        state["prev_positions"] = positions
                        state["prev_session_status"] = curr_status
                        state["prev_stints"] = curr_stints
                    else:
                        now_ts = time.time()
                        if now_ts - state["last_time"] >= COMMENTARY_COOLDOWN_SECONDS:
                            event = _detect_event(
                                state["prev_positions"],
                                positions,
                                state["prev_session_status"],
                                curr_status,
                                state["prev_stints"],
                                curr_stints,
                            )
                            if event:
                                commentary_text = await _generate_commentary(event, race_name)
                                if commentary_text:
                                    commentary_entry = {
                                        "type": "commentary",
                                        "data": {
                                            "id": str(time.time()),
                                            "text": commentary_text,
                                            "event_type": event["type"],
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                        },
                                    }
                                    await websocket.send_json(commentary_entry)
                                    state["last_time"] = time.time()
                                    logger.info(
                                        "commentary.broadcast",
                                        room=room,
                                        event_type=event["type"],
                                    )

                        state["prev_positions"] = positions
                        state["prev_session_status"] = curr_status
                        state["prev_stints"] = curr_stints

            # Wait before next poll
            await asyncio.sleep(WS_POLL_INTERVAL)

            # Check if client is still alive
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT)
                manager.touch(websocket)
            except asyncio.TimeoutError:
                pass  # Client didn't send anything -- that's fine

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        heartbeat_task.cancel()
        manager.disconnect(room, websocket)


def _should_recompute_predictions(year: int, round_num: int, cached: dict) -> bool:
    """Return True if cached prediction should be recomputed.

    Recompute when qualifying data becomes available but cached prediction
    was generated from practice/historical data only.
    """
    cached_sources = cached.get("data_sources", [])
    if "qualifying" in cached_sources:
        return False  # Already has qualifying data, no need to recompute

    # Check if qualifying data is now available by trying to load it
    # This is a lightweight check -- just see if the session exists
    try:
        session = fastf1.get_session(year, round_num, "Q")
        # If we can get the session object without error, qualifying happened
        return True
    except Exception:
        return False


@router.get("/predictions/{year}/{round_num}")
async def get_predictions_endpoint(year: int, round_num: int):
    """Structured race predictions for iOS and web consumption.

    Returns all 20 drivers with predicted positions, confidence ranges,
    reasoning factors, and model accuracy statistics.

    Per CONTEXT.md: REST version returns structured numbers + factors.
    Chat version (via tool) adds narrative reasoning and personality.
    """
    cache_key = (year, round_num)

    if cache_key in predictions_cache:
        cached = predictions_cache[cache_key]
        # Return cached unless qualifying data is now available
        if not _should_recompute_predictions(year, round_num, cached):
            return cached

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(compute_race_predictions, year, round_num),
            timeout=FASTF1_TIMEOUT_SECONDS,
        )
        predictions_cache[cache_key] = result
        return result
    except asyncio.TimeoutError:
        logger.error("predictions.timeout", year=year, round_num=round_num)
        return {"error": "Prediction computation timed out", "year": year, "round": round_num}
    except Exception as e:
        logger.error("predictions.error", year=year, round_num=round_num, error=str(e))
        return {"error": f"Failed to compute predictions: {str(e)}", "year": year, "round": round_num}


@router.get("/health")
async def health_check():
    """Liveness probe — returns 200 OK when the server is running."""
    return {"status": "ok", "timestamp": datetime.now()}
