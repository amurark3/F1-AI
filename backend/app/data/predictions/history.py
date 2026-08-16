"""Durable prediction history: reading, writing and recording results.

Predictions are stored per (year, round) so a later run can compare what was
predicted against what actually happened. Writes take a lock because a snapshot
is a read-modify-write of one document.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from typing import TYPE_CHECKING

import fastf1
import structlog

from app.data.predictions.fastf1_lock import _fastf1_lock
from app.data.predictions.incidents import _classify_status
from app.data.store import DOCUMENT_PREDICTION_HISTORY, document_store

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

_history_file_lock = threading.Lock()

# How long to wait before retrying a result load that produced nothing, and the
# (year, round) -> earliest-next-attempt monotonic deadlines it is tracked with.
ACTUAL_RESULT_RETRY_SECONDS = 900.0
_actual_result_attempts: dict[tuple[int, int], float] = {}
_actual_result_attempt_lock = threading.Lock()


def _read_prediction_history() -> tuple[dict, bool]:
    """Return ``(history, readable)`` from the document store.

    ``readable`` is false when the backend failed, which is not the same as an
    empty history: every caller here does read-modify-write, so writing after a
    failed read would replace the accumulated history with a single entry.
    """
    read = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not read.ok:
        logger.error("prediction_history.read_failed", error=read.error)
        return {}, False
    return (read.payload if isinstance(read.payload, dict) else {}), True


def _load_prediction_history() -> dict:
    """Load prediction history from the document store (Postgres or JSON fallback).

    Returns an empty dict if absent, malformed, or unreadable.
    Never raises — graceful degradation is paramount.
    """
    history, _ = _read_prediction_history()
    return history


def _save_prediction_history(data: dict) -> None:
    """Persist prediction history via the document store (Postgres or JSON fallback).

    Durable when DATABASE_URL is configured; falls back to an atomic local file
    write otherwise.  Never raises.
    """
    result = document_store.write(DOCUMENT_PREDICTION_HISTORY, data)
    if not result.ok:
        logger.error("prediction_history.write_failed", error=result.error)


def save_prediction(year: int, round_num: int, predictions: dict) -> None:
    """Save a prediction to the history file for later accuracy comparison.

    Stores predicted positions keyed by ``"(year,round)"`` along with
    metadata.  Thread-safe via ``_history_file_lock``.
    """
    key = f"({year},{round_num})"

    # Extract predicted positions: driver_code -> predicted position
    predicted_positions = {}
    for entry in predictions.get("predictions", []):
        code = entry.get("driver_code", "")
        pos = entry.get("position")
        if code and pos is not None:
            predicted_positions[code] = pos

    if not predicted_positions:
        return

    risk_predictions = {
        entry.get("driver_code", ""): {
            "dnf_risk_pct": entry.get("dnf_risk_pct"),
            "crash_risk_pct": entry.get("crash_risk_pct"),
            "mechanical_risk_pct": entry.get("mechanical_risk_pct"),
            "risk_level": entry.get("risk_level"),
        }
        for entry in predictions.get("risk_predictions", [])
        if entry.get("driver_code")
    }
    snapshot = {
        "generated_at": predictions.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "prediction_phase": predictions.get("prediction_phase"),
        "data_sources": predictions.get("data_sources") or [],
        "predicted_positions": predicted_positions,
        "risk_predictions": risk_predictions,
    }

    with _history_file_lock:
        history, readable = _read_prediction_history()
        if not readable:
            # Writing now would replace the accumulated history with this one
            # race. Skipping costs a single record; overwriting costs all of them.
            logger.error("predictions.save_skipped_unreadable_history", key=key)
            return
        existing = history.get(key, {})
        snapshots = list(existing.get("snapshots") or [])
        snapshots.append(snapshot)
        history[key] = {
            **existing,
            "predicted_positions": predicted_positions,
            "risk_predictions": risk_predictions,
            "generated_at": snapshot["generated_at"],
            "prediction_phase": snapshot["prediction_phase"],
            "data_sources": snapshot["data_sources"],
            "actual_positions": existing.get("actual_positions"),
            "actual_statuses": existing.get("actual_statuses"),
            "actual_incidents": existing.get("actual_incidents"),
            "snapshots": snapshots[-8:],
        }
        _save_prediction_history(history)

    logger.info("predictions.saved", key=key, drivers=len(predicted_positions))


def _should_attempt_actual_load(year: int, round_num: int) -> bool:
    """Rate-limit result loads for a race that has no result yet.

    A future (or unpublished) race fails every load, so an unguarded call from
    a request path would pay a slow failing FastF1 round trip on every page
    view. Failed attempts back off; a successful load records the result and
    never comes back here.
    """
    now = time.monotonic()
    with _actual_result_attempt_lock:
        if now < _actual_result_attempts.get((year, round_num), 0.0):
            return False
        _actual_result_attempts[(year, round_num)] = now + ACTUAL_RESULT_RETRY_SECONDS
        return True


def _classify_results(results: pd.DataFrame) -> tuple[dict[str, int], dict[str, str], dict[str, dict]]:
    """Split a race classification into positions, statuses and incident flags.

    A row whose position will not coerce to an int contributes nothing at all —
    recording a status without the position it belongs to would leave the three
    maps disagreeing about which drivers were classified.
    """
    positions: dict[str, int] = {}
    statuses: dict[str, str] = {}
    incidents: dict[str, dict] = {}

    for _, row in results.iterrows():
        code = str(row.get("Abbreviation", ""))
        position = row.get("Position")
        if not code or position is None:
            continue
        try:
            positions[code] = int(position)
        except (ValueError, TypeError):
            continue
        status = str(row.get("Status", "") or row.get("status", ""))
        statuses[code] = status
        incidents[code] = _classify_status(status)

    return positions, statuses, incidents


def record_actual_result(year: int, round_num: int) -> None:
    """Load actual race finishing positions from FastF1 and store in history.

    Called lazily when accuracy stats or a post-race review are requested and
    actual data is missing for a past race.
    """
    key = f"({year},{round_num})"

    with _history_file_lock:
        history = _load_prediction_history()

        # Only update if we have a prediction but no actual result yet
        entry = history.get(key)
        if not entry or entry.get("actual_positions"):
            return

    if not _should_attempt_actual_load(year, round_num):
        return

    # Load actual results (outside the file lock to avoid holding it during I/O)
    actual_positions = {}
    actual_statuses = {}
    actual_incidents = {}
    try:
        with _fastf1_lock:
            session = fastf1.get_session(year, round_num, "R")
            session.load(telemetry=False, laps=False, weather=False)

        results = session.results
        if results is not None and not results.empty:
            actual_positions, actual_statuses, actual_incidents = _classify_results(results)
    except Exception as exc:
        logger.warning(
            "predictions.actual_result_load_error",
            year=year,
            round=round_num,
            error=str(exc),
        )
        return

    if not actual_positions:
        return

    # Write back with file lock
    with _history_file_lock:
        history = _load_prediction_history()
        if key in history:
            history[key]["actual_positions"] = actual_positions
            history[key]["actual_statuses"] = actual_statuses
            history[key]["actual_incidents"] = actual_incidents
            _save_prediction_history(history)
            logger.info("predictions.actual_recorded", key=key, drivers=len(actual_positions))
