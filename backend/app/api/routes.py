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
import asyncio
import threading
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
from app.config import (
    TOOL_TIMEOUT_SECONDS,
    FASTF1_TIMEOUT_SECONDS,
    OPENF1_HTTP_TIMEOUT_SECONDS,
    WS_RECEIVE_TIMEOUT,
    WS_POLL_INTERVAL,
    MAX_AGENT_TURNS,
    LLM_MODEL_NAME,
    LLM_TEMPERATURE,
)

router = APIRouter()

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

            print("🤖 ASKING MODEL...")
            current_response = await llm_with_tools.ainvoke(langchain_messages)

            while turn_count < max_turns:
                turn_count += 1

                if current_response.tool_calls:
                    # CASE A — model wants to call tools
                    print(f"🔄 TURN {turn_count}: Model requested {len(current_response.tool_calls)} tool(s).")

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

                            print(f"🛠️  EXECUTING: {tool_name} with args {tool_args}")
                            try:
                                tool_result = await asyncio.wait_for(
                                    asyncio.to_thread(TOOL_MAP[tool_name].invoke, tool_args),
                                    timeout=TOOL_TIMEOUT_SECONDS,
                                )
                                print(f"✅ RESULT (preview): {str(tool_result)[:80]}...")
                            except asyncio.TimeoutError:
                                tool_result = f"Tool '{tool_name}' timed out after {TOOL_TIMEOUT_SECONDS} seconds. The data source may be slow — try again."
                                print(f"⏱️ TOOL TIMEOUT: {tool_name}")
                            except Exception as tool_err:
                                # Surface the error as a tool message so the model
                                # can decide how to handle it gracefully.
                                tool_result = f"Error executing tool '{tool_name}': {tool_err}"
                                print(f"❌ TOOL ERROR: {tool_result}")

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
                    print("🤖 GENERATING FINAL TEXT...")
                    yield current_response.content
                    return  # Exit the generator cleanly

            # If we exhausted max_turns without a text answer, tell the user.
            yield "**System Notice:** Reached the maximum number of reasoning steps. Please try a more specific question."

        except Exception as e:
            print(f"❌ CRITICAL ERROR IN GENERATE: {e}")
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
                    "position": int(row["position"]),
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
        print(f"Driver Standings Error: {e}")
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
                results.append({
                    "position": int(row["position"]),
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
        print(f"Constructor Standings Error: {e}")
        return []



# ---------------------------------------------------------------------------
# In-memory cache for race detail — populated by background prefetch and
# on-demand requests.  Keyed by (year, round_num).
# ---------------------------------------------------------------------------
race_detail_cache: dict[tuple[int, int], dict] = {}

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
        print(f"Race results load error for {year} R{round_num}: {e}")

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
        print(f"Qualifying load error for {year} R{round_num}: {e}")

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
            print(f"Sprint results load error for {year} R{round_num}: {e}")

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
            print(f"Sprint qualifying load error for {year} R{round_num}: {e}")

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
        print(f"⏱️ Race detail TIMEOUT for {year} R{round_num} after {FASTF1_TIMEOUT}s")
        return {"error": "Request timed out loading race data. Try again later.", "timeout": True}
    except Exception as e:
        print(f"Race detail error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Live timing WebSocket
# ---------------------------------------------------------------------------
# Polls OpenF1 API and fans out position/timing updates to connected clients.

import httpx

_live_connections: dict[str, list[WebSocket]] = {}


async def _poll_openf1_positions(session_key: str) -> list[dict] | None:
    """Fetch latest positions from OpenF1 API."""
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.openf1.org/v1/position",
                params={"session_key": session_key, "position__lte": 20},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data:
                return None

            # Group by driver, take latest entry per driver
            latest: dict[int, dict] = {}
            for entry in data:
                dn = entry.get("driver_number")
                if dn is not None:
                    latest[dn] = entry

            positions = []
            for dn, entry in sorted(latest.items(), key=lambda x: x[1].get("position", 99)):
                positions.append({
                    "position": entry.get("position", 0),
                    "driver": str(dn),
                    "gap": entry.get("gap_to_leader", "LEADER") or "LEADER",
                    "last_lap": None,
                    "sector1": None,
                    "sector2": None,
                    "sector3": None,
                    "tyre": None,
                    "pit_stops": None,
                })
            return positions
    except Exception as e:
        print(f"OpenF1 poll error: {e}")
        return None


async def _find_openf1_session(year: int, round_num: int) -> str | None:
    """Find the current live session key from OpenF1."""
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.openf1.org/v1/sessions",
                params={"year": year, "session_type": "Race"},
            )
            if resp.status_code != 200:
                return None
            sessions = resp.json()
            # Match by meeting_key or round number approximation
            for s in sessions:
                if s.get("session_key"):
                    return str(s["session_key"])
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
                    "position": int(row.get("position", 0)),
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
                    d1_pos = int(d1_row.iloc[0]["position"])
                    d2_pos = int(d2_row.iloc[0]["position"])
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
                    d1_qpos = int(d1_q.iloc[0]["position"])
                    d2_qpos = int(d2_q.iloc[0]["position"])
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


@router.websocket("/live/{year}/{round_num}")
async def live_timing(websocket: WebSocket, year: int, round_num: int):
    """WebSocket endpoint for live race timing data."""
    await websocket.accept()

    room = f"{year}-{round_num}"
    if room not in _live_connections:
        _live_connections[room] = []
    _live_connections[room].append(websocket)

    try:
        session_key = await _find_openf1_session(year, round_num)

        while True:
            if session_key:
                positions = await _poll_openf1_positions(session_key)
                if positions:
                    await websocket.send_json({
                        "type": "positions",
                        "data": positions,
                    })

            # Wait before next poll
            await asyncio.sleep(WS_POLL_INTERVAL)

            # Check if client is still alive
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT)
            except asyncio.TimeoutError:
                pass  # Client didn't send anything — that's fine

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if room in _live_connections:
            _live_connections[room] = [
                ws for ws in _live_connections[room] if ws != websocket
            ]


@router.get("/health")
async def health_check():
    """Liveness probe — returns 200 OK when the server is running."""
    return {"status": "ok", "timestamp": datetime.now()}
