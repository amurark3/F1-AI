"""Championship forecast calculations for Race Control."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from app.services.race_control_common import (
    completed_race_rounds,
    get_standings_snapshot,
    safe_float,
    safe_int,
)
from app.services.race_control_debriefs import load_race_classification

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


@dataclass(frozen=True)
class SeasonProgress:
    """Where the season stands, counted in events.

    ``loaded_recent`` is separate from ``completed`` because form is computed
    only over the races whose classification could actually be loaded, which is
    usually fewer than the races that have been run.
    """

    completed: int
    loaded_recent: int
    remaining: int


@dataclass(frozen=True)
class EntrantAccessors:
    """How to read a standings row — drivers and constructors key differently."""

    key: Callable[[dict], str]
    name: Callable[[dict], str]
    team: Callable[[dict], str]
    type_label: str


def build_championship_forecast(year: int) -> dict:
    drivers, constructors = get_standings_snapshot(year)
    completed_rounds, total_events = completed_race_rounds(year)
    completed_events = len(completed_rounds)
    remaining_events = max(0, total_events - completed_events)

    recent_driver_points: dict[str, float] = defaultdict(float)
    recent_constructor_points: dict[str, float] = defaultdict(float)
    loaded_recent_events = 0
    for round_num in completed_rounds[-5:]:
        try:
            detail = load_race_classification(year, round_num)
        except Exception as exc:
            logger.warning("race_control.forecast_recent_form.failed", year=year, round=round_num, error=str(exc))
            continue

        results = detail.get("race_results") or []
        if not results:
            continue

        loaded_recent_events += 1
        for row in results:
            points = safe_float(row.get("points", 0))
            recent_driver_points[str(row.get("driver", "")).upper()] += points
            recent_constructor_points[str(row.get("team", "Unknown"))] += points

    progress = SeasonProgress(
        completed=completed_events,
        loaded_recent=loaded_recent_events,
        remaining=remaining_events,
    )
    driver_rows = forecast_rows(
        entries=drivers,
        recent_points=recent_driver_points,
        progress=progress,
        accessors=EntrantAccessors(
            key=lambda row: row["code"],
            name=lambda row: row["driver"],
            team=lambda row: row["team"],
            type_label="driver",
        ),
    )
    constructor_rows = forecast_rows(
        entries=constructors,
        recent_points=recent_constructor_points,
        progress=progress,
        accessors=EntrantAccessors(
            key=lambda row: row["team"],
            name=lambda row: row["team"],
            team=lambda row: row["team"],
            type_label="constructor",
        ),
    )

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jolpica-ergast-standings + FastF1 recent race classifications",
        "completed_events": completed_events,
        "remaining_events": remaining_events,
        "recent_window": loaded_recent_events,
        "drivers": driver_rows,
        "constructors": constructor_rows,
        "notes": [
            "Current points already include every completed race and sprint result in the standings feed.",
            "Forecast adds a blended season-rate and recent-form rate across remaining Grands Prix.",
            "Recent form uses completed race classifications that could be loaded locally; sprint-specific form is not separately projected.",
        ],
        "error": None if drivers or constructors else "Championship standings are unavailable for this season.",
    }


def _trend_label(trend_delta: float) -> str:
    """Whether recent form is running ahead of, behind, or level with the season."""
    if trend_delta > 1.5:
        return "Gaining"
    if trend_delta < -1.5:
        return "Sliding"
    return "Holding"


def forecast_rows(
    entries: list[dict],
    recent_points: dict[str, float],
    progress: SeasonProgress,
    accessors: EntrantAccessors,
) -> list[dict]:
    base_events = max(progress.completed, 1)
    recent_events = max(progress.loaded_recent, 1)
    rows = []

    for entry in entries:
        raw_key = str(accessors.key(entry))
        key = raw_key.upper() if accessors.type_label == "driver" else raw_key
        current_points = safe_float(entry.get("points", 0))
        season_rate = current_points / base_events
        recent_rate = recent_points.get(key, 0) / recent_events if progress.loaded_recent else season_rate
        form_rate = (recent_rate * 0.62) + (season_rate * 0.38)
        projected_points = current_points + form_rate * progress.remaining

        rows.append(
            {
                "key": key,
                "code": entry.get("code"),
                "name": accessors.name(entry),
                "team": accessors.team(entry),
                "current_position": safe_int(entry.get("position")),
                "current_points": round(current_points, 1),
                "wins": safe_int(entry.get("wins", 0)),
                "season_points_per_event": round(season_rate, 2),
                "recent_points_per_event": round(recent_rate, 2),
                "projected_points": round(projected_points, 1),
                "trend": _trend_label(recent_rate - season_rate),
                "confidence": "Medium" if progress.loaded_recent >= 3 else "Low",
            }
        )

    rows.sort(key=lambda row: (-row["projected_points"], row["current_position"]))
    for index, row in enumerate(rows, start=1):
        row["projected_position"] = index
        row["position_delta"] = row["current_position"] - index
    return rows
