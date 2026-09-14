"""Every session a race weekend actually ran, in running order.

The weekend's format is *discovered*, never assumed. A conventional weekend
runs FP1, FP2 and FP3; a sprint weekend runs FP1, sprint qualifying, the sprint
and then Grand Prix qualifying, with FP2 and FP3 simply not existing. Rather
than branch on a calendar "is sprint" flag — which describes the schedule as
planned, not the sessions that ran — this module asks f1db for each candidate
session and keeps the ones that returned a classification.

That has two benefits. A cancelled session (Suzuka 2022's washed-out practice,
Imola 2023's abandoned weekend) drops out on its own, and a future change to
the sprint format needs a new entry in :data:`WEEKEND_SESSIONS` rather than new
branching.

The sprint grid is deliberately routed through :mod:`app.data.f1db_grid`, the
same reader the Grand Prix grid uses, so a sprint grid penalty is surfaced the
same way and with the same honesty about what f1db records.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.f1db_grid import TYPE_SPRINT_GRID, GridSlot, starting_grid
from app.data.f1db_sessions import (
    KIND_PRACTICE,
    KIND_QUALIFYING,
    KIND_RACE,
    TYPE_PRACTICE_1,
    TYPE_PRACTICE_2,
    TYPE_PRACTICE_3,
    TYPE_SPRINT_QUALIFYING,
    TYPE_SPRINT_RACE,
    SessionEntry,
    session_classification,
)

logger = structlog.get_logger()

#: A grid is its own kind: it is an order, not a classification, and it is the
#: only one carrying penalties.
KIND_GRID = "grid"

NO_SESSIONS_WARNING = (
    "No session results published for this round yet. Practice, sprint and "
    "race classifications are released together once the weekend is complete."
)


@dataclass(frozen=True)
class SessionSpec:
    """One session that a weekend may or may not have run."""

    #: Stable key the UI uses for its tab.
    id: str
    #: Short label, e.g. "FP1".
    label: str
    #: Full name for the panel heading.
    name: str
    kind: str
    #: The f1db ``race_data.type`` holding its classification.
    result_type: str


# Listed in the order they are run, which is the order the tabs appear in.
# FP2/FP3 sit before the sprint entries because a weekend has one set or the
# other, never both interleaved.
WEEKEND_SESSIONS: tuple[SessionSpec, ...] = (
    SessionSpec("fp1", "FP1", "Free Practice 1", KIND_PRACTICE, TYPE_PRACTICE_1),
    SessionSpec("fp2", "FP2", "Free Practice 2", KIND_PRACTICE, TYPE_PRACTICE_2),
    SessionSpec("fp3", "FP3", "Free Practice 3", KIND_PRACTICE, TYPE_PRACTICE_3),
    SessionSpec("sprint_qualifying", "SQ", "Sprint Qualifying", KIND_QUALIFYING, TYPE_SPRINT_QUALIFYING),
    SessionSpec("sprint_grid", "Sprint Grid", "Sprint Starting Grid", KIND_GRID, TYPE_SPRINT_GRID),
    SessionSpec("sprint", "Sprint", "Sprint Race", KIND_RACE, TYPE_SPRINT_RACE),
)


def _entry_payload(entry: SessionEntry) -> dict:
    return {
        "driver_code": entry.driver_code,
        "driver_name": entry.driver_name,
        "team": entry.team,
        "position": entry.position,
        "position_text": entry.position_text,
        "time": entry.time,
        "gap": entry.gap,
        "laps": entry.laps,
        "q1": entry.q1,
        "q2": entry.q2,
        "q3": entry.q3,
        "points": entry.points,
        "grid": entry.grid,
        "retired": entry.retired,
    }


def _grid_payload(slot: GridSlot) -> dict:
    """A sprint grid slot, shaped exactly like the Grand Prix grid's rows.

    Same shape means the frontend's starting-grid drawing renders a sprint grid
    with no second implementation.
    """
    return {
        "driver_code": slot.driver_code,
        "driver_name": slot.driver_name,
        "team": slot.team,
        "position": slot.position,
        "qualifying_position": slot.qualifying_position,
        "penalty_positions": slot.penalty_positions,
        "start_from_back": slot.start_from_back,
        "pit_lane": slot.pit_lane,
        "penalised": slot.penalised,
        "places_lost": slot.places_lost,
    }


def _load_session(year: int, round_num: int, spec: SessionSpec) -> dict | None:
    """One session's payload, or ``None`` when the weekend did not run it."""
    if spec.kind == KIND_GRID:
        slots = starting_grid(year, round_num, spec.result_type)
        if not slots:
            return None
        rows = [_grid_payload(slot) for slot in slots]
        return {
            "id": spec.id,
            "label": spec.label,
            "name": spec.name,
            "kind": spec.kind,
            "entries": rows,
            "penalties": [row for row in rows if row["penalised"]],
        }

    entries = session_classification(year, round_num, spec.result_type, spec.kind)
    if not entries:
        return None
    return {
        "id": spec.id,
        "label": spec.label,
        "name": spec.name,
        "kind": spec.kind,
        "entries": [_entry_payload(entry) for entry in entries],
    }


def build_weekend_sessions(year: int, round_num: int) -> dict:
    """Every session f1db holds a classification for, in running order."""
    sessions = [
        payload
        for spec in WEEKEND_SESSIONS
        if (payload := _load_session(year, round_num, spec)) is not None
    ]
    # A sprint weekend is one that actually ran a sprint, not one a calendar
    # flag says was scheduled to.
    is_sprint = any(session["id"] == "sprint" for session in sessions)

    logger.info(
        "weekend_sessions.built",
        year=year,
        round=round_num,
        sessions=[session["id"] for session in sessions],
        is_sprint=is_sprint,
    )
    return {
        "year": year,
        "round": round_num,
        "available": bool(sessions),
        "is_sprint": is_sprint,
        "sessions": sessions,
        "warnings": [] if sessions else [NO_SESSIONS_WARNING],
    }
