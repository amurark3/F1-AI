"""
API Routes
==========
Defines all HTTP endpoints for the F1 AI backend:

  POST /api/chat                       — Streaming AI chat with tool orchestration
  GET  /api/schedule/{year}            — Full season calendar with UTC session times
  GET  /api/race/{year}/{round_num}    — Enriched race detail (circuit, results, qualifying)
  GET  /api/standings/drivers/{year}   — World Drivers' Championship standings
  GET  /api/standings/constructors/{year} — World Constructors' Championship standings
  GET  /api/health                     — Liveness probe (is the process up?)
  GET  /api/ready                      — Readiness probe (has warm-up finished?)

The chat endpoint implements an agentic loop:
  1. Build message history with system prompt.
  2. Call the LLM; it may request one or more tools.
  3. Execute every requested tool and append results to history.
  4. Repeat until the model produces a plain-text final answer (or max_turns is reached).
  5. Stream the final text back to the client.
"""

import asyncio
import threading
import structlog

from app.utils.fastf1_lock import FASTF1_LOCK
import pandas as pd
import fastf1
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

from app.api.errors import client_error
from app.api.circuits import get_circuit_info
from app.api.routers.champions import router as champions_router
from app.api.routers.chat import router as chat_router
from app.api.routers.memory import router as memory_router
from app.api.routers.predictions import router as predictions_router
from app.api.routers.race_control import router as race_control_router
from app.api.routers.readiness import router as readiness_router
from app.api.routers.season import router as season_router
from app.services.live_commentary import next_commentary, reset_room
from app.services.live_timing import SESSION_END_GRACE, derive_session_state
from app.services.live_timing_client import (
    ActiveSession,
    fetch_current_lap,
    poll_positions,
    resolve_active_session,
)
from app.utils.f1_values import safe_float as _safe_float
from app.utils.f1_values import safe_int as _safe_int
from app.utils.f1_values import safe_str as _safe_str
from app.utils.f1_values import utc_isoformat
from app.utils.fastf1_cache import enable_fastf1_cache
from app.config import (
    FASTF1_TIMEOUT_SECONDS,
    OPENF1_HTTP_TIMEOUT_SECONDS,
    SESSION_LOOKUP_INTERVAL,
    WS_IDLE_POLL_INTERVAL,
    WS_RECEIVE_TIMEOUT,
    WS_HEARTBEAT_INTERVAL,
    WS_STALE_TIMEOUT,
    WS_POLL_INTERVAL,
)

logger = structlog.get_logger()

router = APIRouter()
router.include_router(chat_router)
router.include_router(memory_router)
router.include_router(predictions_router)
router.include_router(race_control_router)
router.include_router(season_router)
router.include_router(champions_router)
router.include_router(readiness_router)

# ---------------------------------------------------------------------------
# FastF1 cache — speeds up repeated session data requests significantly.
# Corrupted cache files are quarantined and recreated on startup.
# ---------------------------------------------------------------------------
enable_fastf1_cache()


# ---------------------------------------------------------------------------
# In-memory cache for race detail — populated by background prefetch and
# on-demand requests.  Keyed by (year, round_num).
# ---------------------------------------------------------------------------
race_detail_cache: dict[tuple[int, int], dict] = {}


# Per-room commentary state — keyed by "{year}-{round_num}"

# Only allow ONE FastF1 session load at a time — they are heavy I/O and
# FastF1 itself is not thread-safe for concurrent session loads.
# Aliased to the process-wide lock: a per-module lock does not serialise
# against the other modules sharing FastF1's SQLite cache.
_fastf1_lock = FASTF1_LOCK


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
                sessions[row[s_name_col]] = utc_isoformat(session_date)

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
                "driver": r.get("Abbreviation", ""),
                "full_name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
                "team": r.get("TeamName", "Unknown"),
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
                        "full_name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
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
                    "full_name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
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
                            "full_name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
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
        return client_error("api.race_detail.error", e, year=year, round=round_num)


# ---------------------------------------------------------------------------
# Live timing WebSocket
# ---------------------------------------------------------------------------
# Polls OpenF1 API and fans out position/timing updates to connected clients.

import time


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
        return client_error("api.compare_drivers.error", e, year=year, driver1=driver1, driver2=driver2)


def _build_comparison_sync(year: int, driver1_query: str, driver2_query: str) -> dict:
    """Build season-long head-to-head stats for two drivers (sourced from f1db)."""
    from app.data.f1db_results import qualifying_positions, race_results, race_schedule
    from app.data.f1db_standings import driver_standings_detailed

    standings = driver_standings_detailed(year)
    if not standings:
        return {"error": f"No standings data for {year}"}

    def find_driver(query: str) -> dict | None:
        q = query.lower().strip()
        for row in standings:
            code = str(row.get("code", "")).lower()
            name = str(row.get("name", "")).lower()
            if q == code or q in name:
                return {
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "team": row.get("team", "Unknown"),
                    "points": float(row.get("points", 0)),
                    "wins": int(row.get("wins", 0)),
                    "position": int(row.get("position", 0)),
                }
        return None

    d1 = find_driver(driver1_query)
    d2 = find_driver(driver2_query)

    if not d1 or not d2:
        return {"error": f"Could not find driver '{driver1_query}' or '{driver2_query}' in {year} standings."}

    quali_h2h = {"d1": 0, "d2": 0}
    race_h2h = {"d1": 0, "d2": 0}
    rounds = []
    d1_positions: list[int] = []
    d2_positions: list[int] = []

    # Walk the season's rounds from f1db. race_results is empty for rounds not
    # yet run / not in the dataset, so future rounds are naturally skipped.
    for event in race_schedule(year):
        round_num = int(event["round"])
        round_data = {"round": round_num, "name": event.get("name", f"Round {round_num}")}

        race_pos = race_results(year, round_num)
        if not race_pos:
            continue

        d1_race = race_pos.get(d1["code"])
        d2_race = race_pos.get(d2["code"])
        if d1_race is not None and d2_race is not None:
            round_data["d1_race"] = d1_race
            round_data["d2_race"] = d2_race
            d1_positions.append(d1_race)
            d2_positions.append(d2_race)
            if d1_race < d2_race:
                race_h2h["d1"] += 1
            elif d2_race < d1_race:
                race_h2h["d2"] += 1

        quali_pos = qualifying_positions(year, round_num)
        d1_q = quali_pos.get(d1["code"])
        d2_q = quali_pos.get(d2["code"])
        if d1_q is not None and d2_q is not None:
            round_data["d1_quali"] = d1_q
            round_data["d2_quali"] = d2_q
            if d1_q < d2_q:
                quali_h2h["d1"] += 1
            elif d2_q < d1_q:
                quali_h2h["d2"] += 1

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
    """Stream live timing for whichever session is running at a race weekend.

    The socket stays open across the weekend and re-resolves the active session
    as practice gives way to qualifying and the race. It reports ``standby``
    honestly between sessions rather than replaying finished classifications.
    """
    room = f"{year}-{round_num}"
    await manager.connect(room, websocket)
    heartbeat_task = asyncio.create_task(manager.heartbeat(websocket))

    try:
        await _run_live_loop(websocket, room, year, round_num)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        heartbeat_task.cancel()
        manager.disconnect(room, websocket)


async def _run_live_loop(websocket: WebSocket, room: str, year: int, round_num: int) -> None:
    """Poll the active session until the client goes away.

    Idles cheaply between sessions: a socket left open across a race weekend
    must not re-resolve the calendar every few seconds.
    """
    active: ActiveSession | None = None
    resolved_at = 0.0

    while not manager.is_stale(websocket):
        now = datetime.now(timezone.utc)

        if _needs_resolution(active, now, resolved_at):
            previous_key = active.session_key if active else None
            active = await resolve_active_session(year, round_num, now=now)
            resolved_at = time.time()
            if active is None or active.session_key != previous_key:
                reset_room(room)
                logger.info(
                    "live.session_resolved",
                    room=room,
                    session=active.session_name if active else None,
                )

        positions = await poll_positions(active.session_key, now=now) if active else None
        state = derive_session_state(active.raw if active else None, now, bool(positions))

        await _broadcast_state(websocket, active, positions, state)

        if positions and active:
            entry = await next_commentary(room, active.session_key, active.meeting_name, positions)
            if entry:
                await websocket.send_json({"type": "commentary", "data": entry})
                logger.info("commentary.broadcast", room=room, event_type=entry["event_type"])

        await asyncio.sleep(WS_POLL_INTERVAL if active else WS_IDLE_POLL_INTERVAL)
        await _drain_client(websocket)


def _needs_resolution(active: "ActiveSession | None", now: datetime, resolved_at: float) -> bool:
    """Whether the active session must be looked up again.

    While nothing is on track the lookup is rate-limited: it costs a FastF1
    schedule read plus two OpenF1 calls, and the answer changes at most once
    per session.
    """
    if active is None:
        return (time.time() - resolved_at) >= SESSION_LOOKUP_INTERVAL
    return now > active.date_end + SESSION_END_GRACE


async def _broadcast_state(
    websocket: WebSocket,
    active: "ActiveSession | None",
    positions: list[dict] | None,
    state: str,
) -> None:
    """Send session status, and positions only when there is a live feed."""
    lap = await fetch_current_lap(active.session_key) if (positions and active) else None

    await websocket.send_json({
        "type": "session_status",
        "data": {
            "status": state,
            "session_name": active.session_name if active else None,
            "meeting_name": active.meeting_name if active else None,
            "starts_at": active.date_start.isoformat() if active else None,
            "lap": lap,
        },
    })
    manager.touch(websocket)

    if positions:
        await websocket.send_json({"type": "positions", "data": positions})
        manager.touch(websocket)


async def _drain_client(websocket: WebSocket) -> None:
    """Consume any client message so liveness is tracked; silence is fine."""
    try:
        await asyncio.wait_for(websocket.receive_text(), timeout=WS_RECEIVE_TIMEOUT)
        manager.touch(websocket)
    except asyncio.TimeoutError:
        pass


@router.get("/health")
async def health_check():
    """Liveness probe — returns 200 OK when the server is running."""
    return {"status": "ok", "timestamp": datetime.now()}
