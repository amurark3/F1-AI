"""Workstream status cards shown down the side of the command center."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def focus_for_event(event: dict | None) -> str:
    if not event:
        return "Season review"
    if event["status"] == "in_progress":
        return "Live session control"
    if event["days_until"] is not None and event["days_until"] <= 10:
        return "Race-week strategy lock"
    return "Pre-race simulation build"


def _weekend_brief_status(event: dict | None) -> str:
    if not event:
        return "Waiting"
    if event["status"] == "in_progress":
        return "Live"
    if event["status"] == "completed":
        return "Complete"
    return "Ready"


def _race_model_status(predictions: dict | None, data_source: dict) -> str:
    """Reflect whether the race model is telemetry-backed, still building, or missing."""
    if not (predictions or {}).get("predictions"):
        return "Waiting"
    return "Ready" if data_source.get("mode") == "telemetry" else "Build"


def _rival_watch_status(competitors: list[dict]) -> str:
    if not competitors:
        return "Standby"
    if any(row.get("threat") in ("Primary", "High") for row in competitors if row.get("rank", 0) > 1):
        return "Active"
    return "Monitor"


def _live_control_status(event: dict | None) -> str:
    if not event:
        return "Idle"
    if event["status"] == "in_progress":
        return "Live"
    if event["status"] == "completed":
        return "Complete"
    return "Standby"


def build_workstreams(
    event: dict | None,
    predictions: dict | None,
    strategy_context: dict,
) -> list[dict]:
    """Build the workstream board with statuses derived from live desk state.

    Priorities are fixed operational weightings (a config attribute of each
    stream), but every status reflects real progress: session state, whether the
    race model is telemetry-backed, and whether a close rival is in play.
    """
    data_source = (strategy_context or {}).get("data_source", {})
    competitors = (strategy_context or {}).get("competitors", [])
    return [
        {
            "id": "weekend-brief",
            "title": "Weekend Brief",
            "owner": "Strategy",
            "priority": "P1",
            "status": _weekend_brief_status(event),
            "href": "/race-control",
        },
        {
            "id": "race-model",
            "title": "Race Model",
            "owner": "Performance",
            "priority": "P1",
            "status": _race_model_status(predictions, data_source),
            "href": "/race-control/predictions",
        },
        {
            "id": "rival-watch",
            "title": "Rival Watch",
            "owner": "Competitor Intel",
            "priority": "P2",
            "status": _rival_watch_status(competitors),
            "href": "/race-control/teams",
        },
        {
            "id": "live-control",
            "title": "Live Control",
            "owner": "Pit Wall",
            "priority": "P1",
            "status": _live_control_status(event),
            "href": "/race-control/live",
        },
    ]
