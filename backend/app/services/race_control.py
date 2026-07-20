"""Race Control overview orchestration and public service facade.

Focused feature services live beside this module. This file keeps the existing
router contract stable while limiting itself to command-center composition.
"""

from __future__ import annotations

from datetime import datetime, timezone

import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.services.predictions import get_or_compute_race_prediction
from app.services.race_control_battles import build_driver_battle
from app.services.race_control_championship import build_championship_forecast
from app.services.race_control_common import get_driver_options, get_standings_snapshot, safe_int
from app.services.race_control_debriefs import build_race_debrief
from app.services.race_control_standings import build_intel, build_teams
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()


def build_strategy_dashboard(year: int) -> dict:
    """Build the command-center shell from schedule and standings data."""

    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    events = []
    for _, row in schedule.iterrows():
        location = f"{row['Location']}, {row['Country']}"
        sessions = {}
        first_session_date = None
        last_session_date = None
        race_session_date = None

        for i in range(1, 6):
            name_col = f"Session{i}"
            date_col = f"Session{i}DateUtc"
            if name_col not in row or pd.isna(row[name_col]):
                continue

            session_name = row[name_col]
            session_date = row[date_col]
            if pd.isna(session_date):
                continue

            sessions[session_name] = utc_isoformat(session_date)
            timestamp = session_date.to_pydatetime()
            first_session_date = timestamp if first_session_date is None else min(first_session_date, timestamp)
            last_session_date = timestamp if last_session_date is None else max(last_session_date, timestamp)
            if session_name == "Race":
                race_session_date = timestamp

        if last_session_date and now_utc > last_session_date + pd.Timedelta(hours=3):
            status = "completed"
        elif first_session_date and now_utc >= first_session_date:
            status = "in_progress"
        else:
            status = "upcoming"

        days_until = None
        if first_session_date and status == "upcoming":
            days_until = max(0, int((first_session_date - now_utc).total_seconds() // 86400))

        events.append({
            "round": safe_int(row["RoundNumber"]),
            "name": row["EventName"],
            "location": location,
            "country": row["Country"],
            "status": status,
            "date": row["EventDate"].isoformat(),
            "sessions": sessions,
            "is_sprint": "Sprint" in sessions,
            "days_until": days_until,
            "circuit": get_circuit_info(location),
            "race_session": utc_isoformat(race_session_date) if race_session_date else None,
        })

    active_event = next((event for event in events if event["status"] == "in_progress"), None)
    next_event = next((event for event in events if event["status"] == "upcoming"), None)
    selected_event = active_event or next_event or (events[-1] if events else None)
    drivers, constructors = get_standings_snapshot(year)

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "focus": focus_for_event(selected_event),
        "race": selected_event,
        "season": {
            "total_events": len(events),
            "completed_events": len([event for event in events if event["status"] == "completed"]),
            "upcoming_events": len([event for event in events if event["status"] == "upcoming"]),
        },
        "championship": {
            "drivers": drivers[:5],
            "constructors": constructors[:5],
        },
        "risk_register": build_risk_register(selected_event),
        "workstreams": build_workstreams(selected_event),
    }


def focus_for_event(event: dict | None) -> str:
    if not event:
        return "Season review"
    if event["status"] == "in_progress":
        return "Live session control"
    if event["days_until"] is not None and event["days_until"] <= 10:
        return "Race-week strategy lock"
    return "Pre-race simulation build"


def build_risk_register(event: dict | None) -> list[dict]:
    if not event:
        return []

    risks = []
    if event["is_sprint"]:
        risks.append({
            "level": "High",
            "title": "Sprint format compression",
            "detail": "Reduced practice time increases setup and parc ferme decision pressure.",
        })
    if event["circuit"] and event["circuit"].get("circuit_type") == "Street":
        risks.append({
            "level": "High",
            "title": "Safety car exposure",
            "detail": "Street circuit profile raises track-position and pit-window volatility.",
        })
    risks.extend([
        {
            "level": "Medium",
            "title": "Weather confirmation",
            "detail": "Lock dry/wet branches once the latest circuit forecast is available.",
        },
        {
            "level": "Medium",
            "title": "Rival offset plans",
            "detail": "Prepare undercut and overcut responses for the closest championship rivals.",
        },
    ])
    return risks


def build_workstreams(event: dict | None) -> list[dict]:
    return [
        {
            "id": "weekend-brief",
            "title": "Weekend Brief",
            "owner": "Strategy",
            "priority": "P1",
            "status": "Ready" if event else "Waiting",
            "href": "/race-control",
        },
        {
            "id": "race-model",
            "title": "Race Model",
            "owner": "Performance",
            "priority": "P1",
            "status": "Build",
            "href": "/race-control/predictions",
        },
        {
            "id": "rival-watch",
            "title": "Rival Watch",
            "owner": "Competitor Intel",
            "priority": "P2",
            "status": "Monitor",
            "href": "/race-control/teams",
        },
        {
            "id": "live-control",
            "title": "Live Control",
            "owner": "Pit Wall",
            "priority": "P1",
            "status": "Standby",
            "href": "/race-control/live",
        },
    ]


def build_overview(year: int) -> dict:
    dashboard = build_strategy_dashboard(year)
    race = dashboard.get("race")
    championship = dashboard.get("championship", {})
    constructors = championship.get("constructors", [])

    predictions = None
    if race and race.get("round"):
        try:
            predictions = get_or_compute_race_prediction(year, race["round"])
        except Exception as exc:
            logger.warning("race_control.predictions.failed", year=year, error=str(exc))

    return {
        **dashboard,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
        "strategy_context": build_strategy_context(race, constructors, predictions),
        "weather": {
            "rain_risk": None,
            "track_temp_c": None,
            "wind_kph": None,
            "confidence": "External forecast feed not connected",
        },
        "live_status": {
            "connected": bool(race and race.get("status") == "in_progress"),
            "label": "Live session active" if race and race.get("status") == "in_progress" else "Standby",
        },
    }


def build_strategy_context(race: dict | None, constructors: list[dict], predictions: dict | None) -> dict:
    """Build transparent decision-support context for the command center."""

    laps = safe_int((race or {}).get("circuit", {}).get("laps") if race else None, 58)
    circuit_type = ((race or {}).get("circuit") or {}).get("circuit_type", "Permanent")
    is_street = str(circuit_type).lower() == "street"
    is_sprint = bool((race or {}).get("is_sprint"))
    pit_loss = 24 if is_street else 21
    primary_stop = max(16, min(laps - 18, round(laps * (0.38 if is_street else 0.42))))
    offset_stop = max(10, primary_stop - (5 if is_street else 4))
    late_stop = min(laps - 8, primary_stop + (8 if is_street else 10))
    podium = (predictions or {}).get("predictions", [])[:3]
    lead_prediction = podium[0] if podium else None

    competitor_rows = []
    leader_points = constructors[0]["points"] if constructors else 0
    for index, team in enumerate(constructors[:5], start=1):
        gap = max(0, leader_points - team["points"])
        competitor_rows.append({
            "rank": index,
            "team": team["team"],
            "points": team["points"],
            "gap_to_leader": round(gap, 1),
            "threat": "Primary" if index == 1 else "High" if gap <= 60 else "Monitor",
            "operating_read": (
                "Benchmark car; protect against clean-air extensions."
                if index == 1
                else "Undercut exposure if they qualify within one pit-loss window."
                if gap <= 60
                else "Scenario dependent; watch safety-car offsets."
            ),
        })

    return {
        "phase": "Live race desk" if race and race.get("status") == "in_progress" else "Pre-race build",
        "primary_call": {
            "title": "Base race plan",
            "summary": f"Model a medium-to-hard one-stop around L{primary_stop}; keep a two-stop branch open if tyre age exceeds the working life before the stop.",
            "confidence": "medium" if lead_prediction else "low",
        },
        "decision_gates": [
            {
                "gate": "Parc ferme lock",
                "trigger": "After qualifying",
                "owner": "Performance",
                "decision": "Freeze wing level and cooling assumptions before strategy branches are finalised.",
            },
            {
                "gate": "First stop call",
                "trigger": f"L{offset_stop}-L{primary_stop}",
                "owner": "Strategy",
                "decision": "Commit to undercut only if rejoin traffic is below medium and rival gap is inside 2.5s.",
            },
            {
                "gate": "Safety-car branch",
                "trigger": f"L{primary_stop}-L{late_stop}",
                "owner": "Pit Wall",
                "decision": "Box if field spread creates a free stop or tyre offset protects track position.",
            },
        ],
        "stint_plan": [
            {
                "stint": "Opening",
                "compound": "Medium",
                "window": f"L1-L{primary_stop}",
                "target": "Hold tyre surface temperatures, avoid early traffic damage.",
            },
            {
                "stint": "Race finish",
                "compound": "Hard",
                "window": f"L{primary_stop + 1}-L{laps}",
                "target": "Protect track position; switch to two-stop if degradation crosses the cliff.",
            },
        ],
        "pit_model": {
            "pit_loss_seconds": pit_loss,
            "undercut_delta": round(1.2 + (0.4 if is_street else 0.2), 1),
            "overcut_delta": round(0.8 + (0.2 if is_sprint else 0.1), 1),
            "traffic_threshold": "medium",
        },
        "competitors": competitor_rows,
        "assumptions": [
            "Race context is derived from the season schedule, circuit metadata, standings, and cached prediction snapshots.",
            "Weather is not treated as live until an external forecast feed is connected.",
            "Tyre windows are planning assumptions, not live telemetry.",
        ],
    }
