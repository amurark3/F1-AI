"""OpenF1 API polling — positions, lap counter, session discovery and stints.

Every call here is an outbound HTTP request with a timeout; failures return
``None`` or an empty result so the live feed degrades instead of dropping.
"""

from __future__ import annotations

import httpx
import structlog

from app.config import OPENF1_HTTP_TIMEOUT_SECONDS

logger = structlog.get_logger()

# Cache driver info per session to avoid re-fetching every poll cycle
_driver_cache: dict[str, dict[int, dict]] = {}


async def _cached_drivers(client: httpx.AsyncClient, session_key: str) -> dict[int, dict]:
    """Driver metadata for the session, fetched once and cached thereafter."""
    if session_key not in _driver_cache:
        response = await client.get("https://api.openf1.org/v1/drivers", params={"session_key": session_key})
        if response.status_code == 200 and isinstance(response.json(), list):
            _driver_cache[session_key] = {d["driver_number"]: d for d in response.json() if "driver_number" in d}
    return _driver_cache.get(session_key, {})


def _latest_by_driver(payload: object) -> dict[int, dict]:
    """Index an OpenF1 append-only log by driver number, last entry winning."""
    latest: dict[int, dict] = {}
    if not isinstance(payload, list):
        return latest
    for entry in payload:
        number = entry.get("driver_number")
        if number is not None:
            latest[number] = entry
    return latest


def _format_gap(position: int, interval: dict) -> str:
    """Render gap-to-leader — LEADER for P1, an em dash when unknown."""
    raw = interval.get("gap_to_leader")
    try:
        gap = float(raw) if raw is not None else None
    except (ValueError, TypeError):
        gap = None
    if position == 1 or gap == 0.0:
        return "LEADER"
    return f"+{gap:.3f}" if gap is not None else "—"


async def _poll_openf1_positions(session_key: str) -> list[dict] | None:
    """Fetch latest positions, gaps, and driver names from OpenF1 API."""
    try:
        async with httpx.AsyncClient(timeout=OPENF1_HTTP_TIMEOUT_SECONDS) as client:
            drivers = await _cached_drivers(client, session_key)
            pos_resp = await client.get("https://api.openf1.org/v1/position", params={"session_key": session_key})
            int_resp = await client.get("https://api.openf1.org/v1/intervals", params={"session_key": session_key})

        if pos_resp.status_code != 200:
            return None
        latest = _latest_by_driver(pos_resp.json())
        if not latest:
            return None

        intervals = _latest_by_driver(int_resp.json()) if int_resp.status_code == 200 else {}

        return [
            {
                "position": entry.get("position", 0),
                "driver": drivers.get(number, {}).get("name_acronym") or str(number),
                "gap": _format_gap(entry.get("position", 0), intervals.get(number, {})),
                "last_lap": None,
                "sector1": None,
                "sector2": None,
                "sector3": None,
                "tyre": None,
                "pit_stops": None,
            }
            for number, entry in sorted(latest.items(), key=lambda item: item[1].get("position", 99))
        ]
    except Exception as e:
        logger.exception("openf1.poll_error", error=str(e))
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
    except Exception as e:
        logger.warning("openf1.session_lookup_error", error=str(e))
        return None


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
