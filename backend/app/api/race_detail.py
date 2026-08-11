"""Enriched race detail: circuit info, race results and qualifying.

Split out of ``routes`` because it is the one endpoint that does heavy
synchronous FastF1 work, with its own in-memory cache and timeout.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import threading
from typing import TYPE_CHECKING

from fastapi import APIRouter
import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.api.errors import client_error
from app.config import FASTF1_TIMEOUT_SECONDS
from app.utils.f1_values import utc_isoformat

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

router = APIRouter()

# In-memory cache for race detail — populated by background prefetch and
# on-demand requests. Keyed by (year, round_num).
race_detail_cache: dict[tuple[int, int], dict] = {}

# Only allow ONE FastF1 session load at a time — they are heavy I/O and
# FastF1 itself is not thread-safe for concurrent session loads.
_fastf1_lock = threading.Lock()

# Per-request timeout for building race detail (seconds).
# Generous because the lock means requests queue up sequentially.
FASTF1_TIMEOUT = FASTF1_TIMEOUT_SECONDS


def _fmt_td(time_val: pd.Timedelta | None) -> str:
    """Convert a pandas Timedelta to a clean lap-time string."""
    if pd.isna(time_val):
        return "-"
    s = str(time_val).split("days")[-1].strip()
    s = s.removeprefix("00:")
    if len(s) > 10:
        s = s[:9]
    return s


# A race is treated as complete this long after its scheduled start.
_RACE_COMPLETE_BUFFER = pd.Timedelta(hours=3)

# FastF1 exposes at most five sessions per event row.
_SESSION_SLOTS = range(1, 6)

_QUALIFYING_PHASES = ("Q1", "Q2", "Q3")


def _full_name(entry: pd.Series) -> str:
    """Driver's display name, tolerating either half being absent."""
    return f"{entry.get('FirstName', '')} {entry.get('LastName', '')}".strip()


def _event_date(row: pd.Series) -> str:
    """Event date as ISO text, forced to carry an explicit UTC marker."""
    text = row["EventDate"].isoformat()
    if not text.endswith("Z") and "+" not in text:
        text += "Z"
    return text


def _session_schedule(row: pd.Series) -> dict[str, str]:
    """Session name -> UTC start, for the sessions the schedule dates."""
    sessions = {}
    for slot in _SESSION_SLOTS:
        name_col = f"Session{slot}"
        date_col = f"Session{slot}DateUtc"
        if name_col in row and pd.notna(row[name_col]) and pd.notna(row[date_col]):
            sessions[row[name_col]] = utc_isoformat(row[date_col])
    return sessions


def _session_names(row: pd.Series) -> list[str]:
    """Every named session on an event row."""
    return [
        row[f"Session{slot}"] for slot in _SESSION_SLOTS if f"Session{slot}" in row and pd.notna(row[f"Session{slot}"])
    ]


def _race_start(row: pd.Series) -> datetime | None:
    """UTC start of the Race session, if the schedule gives it a date."""
    for slot in _SESSION_SLOTS:
        name_col = f"Session{slot}"
        date_col = f"Session{slot}DateUtc"
        if name_col in row and row[name_col] == "Race" and pd.notna(row[date_col]):
            return row[date_col].to_pydatetime()
    return None


def _load_session_results(year: int, round_num: int, identifier: str) -> pd.DataFrame:
    """Load one session's results, serialised behind the module-wide lock."""
    with _fastf1_lock:
        session = fastf1.get_session(year, round_num, identifier)
        session.load(telemetry=False, laps=False, weather=False)
    return session.results


def _race_gap(time_val: object) -> str:
    """A race gap trimmed to milliseconds."""
    text = str(time_val).split("days")[-1].strip()
    if "." in text:
        text = text[: text.find(".") + 4]
    return text.removeprefix("00:")


def _classification_time(status: str, time_val: object, format_time: Callable[[object], str]) -> str:
    """Finish time, lap deficit or retirement reason for one classified car."""
    if status != "Finished":
        return status if "Lap" in status else f"DNF - {status}"
    return format_time(time_val) if pd.notna(time_val) else ""


def _classification_rows(results: pd.DataFrame, format_time: Callable[[object], str]) -> list[dict]:
    """Per-driver classification rows, shared by the race and the sprint.

    The two differ only in how a finishing time is rendered, so the formatter is
    the parameter rather than the whole row-building loop being duplicated.
    """
    rows = []
    for _, entry in results.iterrows():
        status = entry["Status"]
        grid = entry["GridPosition"]
        rows.append(
            {
                "position": int(entry["Position"]) if pd.notna(entry["Position"]) else None,
                "driver": entry.get("Abbreviation", ""),
                "full_name": _full_name(entry),
                "team": entry.get("TeamName", "Unknown"),
                "grid": int(grid) if pd.notna(grid) and grid > 0 else None,
                "time": _classification_time(status, entry["Time"], format_time),
                "points": float(entry["Points"]) if pd.notna(entry["Points"]) else 0,
                "status": status,
            }
        )
    return rows


def _qualifying_phases(results: pd.DataFrame) -> dict | None:
    """Q1/Q2/Q3 order, omitting any phase that produced no times."""
    qualifying = {}
    for phase in _QUALIFYING_PHASES:
        if phase not in results.columns:
            continue
        ordered = results[results[phase].notna()].sort_values(by=phase)
        rows = [
            {
                "position": position,
                "driver": entry["Abbreviation"],
                "full_name": _full_name(entry),
                "team": entry["TeamName"],
                "time": _fmt_td(entry[phase]),
            }
            for position, (_, entry) in enumerate(ordered.iterrows(), 1)
        ]
        if rows:
            qualifying[phase] = rows
    return qualifying or None


def _load_race_classification(year: int, round_num: int) -> tuple[list[dict] | None, list[dict] | None]:
    """Race classification and podium; ``(None, None)`` when the load fails."""
    try:
        results = _load_session_results(year, round_num, "R").sort_values(by="Position")
    except Exception as e:
        logger.exception("api.race_results.load_error", year=year, round=round_num, error=str(e))
        return None, None

    rows = _classification_rows(results, _race_gap)
    podium = sorted(
        (row for row in rows if row["position"] and row["position"] <= 3),
        key=lambda row: row["position"],
    )
    return rows, podium


def _load_qualifying(year: int, round_num: int) -> dict | None:
    """Qualifying order, or None when it could not be loaded."""
    try:
        return _qualifying_phases(_load_session_results(year, round_num, "Q"))
    except Exception as e:
        logger.exception("api.qualifying.load_error", year=year, round=round_num, error=str(e))
        return None


def _load_sprint(year: int, round_num: int) -> list[dict] | None:
    """Sprint classification, or None when it could not be loaded."""
    try:
        results = _load_session_results(year, round_num, "S").sort_values(by="Position")
    except Exception as e:
        logger.exception("api.sprint_results.load_error", year=year, round=round_num, error=str(e))
        return None
    return _classification_rows(results, _fmt_td) or None


def _load_sprint_qualifying(year: int, round_num: int) -> dict | None:
    """Sprint qualifying order, or None when it could not be loaded."""
    try:
        return _qualifying_phases(_load_session_results(year, round_num, "SQ"))
    except Exception as e:
        logger.exception("api.sprint_qualifying.load_error", year=year, round=round_num, error=str(e))
        return None


def build_race_detail(year: int, round_num: int) -> dict:
    """
    Synchronous helper that loads enriched race data from FastF1.

    Returns a dict with circuit info, race results, qualifying, and podium.
    Called via asyncio.to_thread() to avoid blocking the event loop.

    Each session loads independently and logs its own failure, so one missing
    session leaves its key null rather than emptying the whole response.
    """
    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    event_row = schedule[schedule["RoundNumber"] == round_num]
    if event_row.empty:
        return {"error": f"Round {round_num} not found for {year}"}

    row = event_row.iloc[0]
    location_str = f"{row['Location']}, {row['Country']}"
    is_sprint_weekend = "Sprint" in _session_names(row)

    result = {
        "round": round_num,
        "name": row["EventName"],
        "location": location_str,
        "date": _event_date(row),
        "sessions": _session_schedule(row),
        "circuit": get_circuit_info(location_str),
        "race_results": None,
        "qualifying": None,
        "podium": None,
        "is_sprint": is_sprint_weekend,
        "sprint_results": None,
        "sprint_qualifying": None,
    }

    race_start = _race_start(row)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if not race_start or now_utc <= race_start + _RACE_COMPLETE_BUFFER:
        return result

    result["race_results"], result["podium"] = _load_race_classification(year, round_num)
    result["qualifying"] = _load_qualifying(year, round_num)

    if is_sprint_weekend:
        result["sprint_results"] = _load_sprint(year, round_num)
        result["sprint_qualifying"] = _load_sprint_qualifying(year, round_num)

    return result


@router.get("/race/{year}/{round_num}")
async def get_race_detail(year: int, round_num: int) -> dict:
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
            asyncio.to_thread(build_race_detail, year, round_num),
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
