"""Durable prediction history: reading, writing and recording results.

Predictions are stored per (year, round) so a later run can compare what was
predicted against what actually happened. Writes take a lock because a snapshot
is a read-modify-write of one document.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading
import time

import structlog

from app.data.fia_documents.results import FIA_FINAL_SOURCE
from app.data.predictions.graded import with_graded_fields
from app.data.predictions.incidents import _classify_status
from app.data.predictions.phases import trim_snapshots
from app.data.race_classification import JOLPICA_SOURCE, RaceClassification, race_classification
from app.data.store import DOCUMENT_PREDICTION_HISTORY, document_store

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


def prediction_call(predictions: dict) -> dict | None:
    """The call a compute made, in the shape prediction history stores it.

    ``None`` when the compute produced no finishing order: there is nothing to
    grade.
    """
    predicted_positions = {}
    for entry in predictions.get("predictions", []):
        code = entry.get("driver_code", "")
        pos = entry.get("position")
        if code and pos is not None:
            predicted_positions[code] = pos

    if not predicted_positions:
        return None

    risk_predictions = {
        entry.get("driver_code", ""): {
            "dnf_risk_pct": entry.get("dnf_risk_pct"),
            "crash_risk_pct": entry.get("crash_risk_pct"),
            "mechanical_risk_pct": entry.get("mechanical_risk_pct"),
            "risk_level": entry.get("risk_level"),
            "risk_model": entry.get("risk_model"),
        }
        for entry in predictions.get("risk_predictions", [])
        if entry.get("driver_code")
    }
    return {
        "generated_at": predictions.get("generated_at", datetime.now(UTC).isoformat()),
        "prediction_phase": predictions.get("prediction_phase"),
        "data_sources": predictions.get("data_sources") or [],
        "predicted_positions": predicted_positions,
        "risk_predictions": risk_predictions,
    }


def save_prediction(year: int, round_num: int, predictions: dict) -> None:
    """Record a stored call in the race's history, for later accuracy comparison.

    Call this only once the call has been stored as a snapshot
    (``app.services.predictions``): a call the endpoint refused must never be
    graded. The call is appended to the race's ``snapshots``, and the entry's
    top-level fields are set to the race's graded call (``graded``), which a
    later pre-qualifying call does not replace. Thread-safe via
    ``_history_file_lock``.
    """
    key = f"({year},{round_num})"
    call = prediction_call(predictions)
    if call is None:
        return

    with _history_file_lock:
        history, readable = _read_prediction_history()
        if not readable:
            # Writing now would replace the accumulated history with this one
            # race. Skipping costs a single record; overwriting costs all of them.
            logger.error("predictions.save_skipped_unreadable_history", key=key)
            return
        existing = history.get(key, {})
        snapshots = list(existing.get("snapshots") or [])
        snapshots.append(call)
        history[key] = with_graded_fields(
            {
                **existing,
                "actual_positions": existing.get("actual_positions"),
                "actual_statuses": existing.get("actual_statuses"),
                "actual_incidents": existing.get("actual_incidents"),
                "snapshots": trim_snapshots(snapshots),
            }
        )
        _save_prediction_history(history)

    logger.info("predictions.saved", key=key, drivers=len(call["predicted_positions"]))


def _should_attempt_actual_load(year: int, round_num: int) -> bool:
    """Rate-limit result loads for a race that has no result yet.

    A future (or unpublished) race answers nothing, so an unguarded call from a
    request path would ask the feeds again on every page view. Failed attempts
    back off.
    """
    now = time.monotonic()
    with _actual_result_attempt_lock:
        if now < _actual_result_attempts.get((year, round_num), 0.0):
            return False
        _actual_result_attempts[(year, round_num)] = now + ACTUAL_RESULT_RETRY_SECONDS
        return True


# A car's status as stored in ``actual_statuses``: the review and the incident
# flags read it, so a retirement stays a retirement whatever place it is listed at.
STATUS_LABELS: dict[str, str] = {
    "finished": "Finished",
    "dnf": "DNF",
    "dns": "DNS",
    "dsq": "DSQ",
    "not_classified": "NC",
}

# Penalties land for a day or two after the flag. A result stands as provisional
# until a second read this long after the first one agrees with it.
CONFIRM_AFTER = timedelta(hours=24)


def _classify_results(classification: RaceClassification) -> tuple[dict[str, int], dict[str, str], dict[str, dict]]:
    """Split a race classification into positions, statuses and incident flags.

    The classification is in published order, so a car with no classified place
    (a retirement, a non-starter, a disqualification) is listed after the
    classified ones at its place in that order. Its status says what it is: it
    is never recorded as a place alone.
    """
    positions: dict[str, int] = {}
    statuses: dict[str, str] = {}
    incidents: dict[str, dict] = {}
    for index, driver in enumerate(classification.drivers, start=1):
        positions[driver.driver_code] = driver.position or index
        statuses[driver.driver_code] = STATUS_LABELS[driver.status]
        label = statuses[driver.driver_code]
        incidents[driver.driver_code] = _classify_status(f"{label} · {driver.reason}" if driver.reason else label)
    return positions, statuses, incidents


def actual_fields(entry: dict, classification: RaceClassification) -> dict:
    """The result fields of ``entry`` once ``classification`` is recorded on it.

    Final at once when read from the FIA final classification, the authority.
    Otherwise final only when it agrees with what ``entry`` already holds and
    is not Jolpica's, which shows the pre-penalty order. A Jolpica read never replaces a
    result from another source: it only moves ``actual_recorded_at``.
    """
    if classification.source == JOLPICA_SOURCE and entry.get("actual_source") not in (None, JOLPICA_SOURCE):
        return {"actual_recorded_at": datetime.now(UTC).isoformat()}
    positions, statuses, incidents = _classify_results(classification)
    agrees = entry.get("actual_positions") == positions and entry.get("actual_statuses") == statuses
    return {
        "actual_positions": positions,
        "actual_statuses": statuses,
        "actual_incidents": incidents,
        "actual_source": classification.source,
        "actual_provisional": not (
            classification.source == FIA_FINAL_SOURCE or (agrees and classification.source != JOLPICA_SOURCE)
        ),
        "actual_recorded_at": datetime.now(UTC).isoformat(),
    }


def actuals_pending(entry: dict) -> bool:
    """Whether a race's graded call still needs its result recorded or confirmed.

    A result recorded before provenance was stored (no ``actual_provisional``)
    is left to ``scripts.regrade_actuals``, which backs up and lists every
    change; it is never rewritten from a request path.
    """
    if not entry.get("actual_positions"):
        return True
    if entry.get("actual_provisional") is not True:
        return False
    recorded_at = entry.get("actual_recorded_at")
    return not isinstance(recorded_at, str) or datetime.now(UTC) - datetime.fromisoformat(recorded_at) >= CONFIRM_AFTER


def record_actual_result(year: int, round_num: int) -> None:
    """Grade a race against its published classification and store it in history.

    Called lazily when accuracy stats or a post-race review are requested and
    the result is missing, or recorded as provisional for a day. The
    classification is :func:`race_classification`'s (no FastF1): the order after
    post-race penalties, with each car's status. A read that finds nothing
    records nothing and is retried later.

    The result is stored with its ``actual_source`` and ``actual_provisional``.
    It is final at once when read from the FIA final classification. Otherwise
    it becomes final when a later read, a day after it was recorded, agrees with
    it and did not come from Jolpica, which shows the pre-penalty order. A read
    that differs replaces it (still provisional); the graded call is untouched.
    """
    key = f"({year},{round_num})"

    with _history_file_lock:
        entry = _load_prediction_history().get(key)
        if not entry or not actuals_pending(entry):
            return

    if not _should_attempt_actual_load(year, round_num):
        return

    classification = race_classification(year, round_num)
    if not classification.drivers:
        return

    # Write back with file lock
    with _history_file_lock:
        history = _load_prediction_history()
        if key in history:
            entry = history[key]
            history[key] = {**entry, **actual_fields(entry, classification)}
            _save_prediction_history(history)
            logger.info(
                "predictions.actual_recorded",
                key=key,
                drivers=len(classification.drivers),
                source=classification.source,
            )
