"""Business logic for the Race Control v2 product surface.

The service layer keeps race-control calculations and data composition out of
FastAPI routers. It is intentionally additive and does not mutate existing
legacy endpoint contracts.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import fastf1
import pandas as pd
import structlog
from fastf1.ergast import Ergast

from app.api.circuits import get_circuit_info
from app.api.schemas.race_control import StrategySimulationRequest
from app.services.predictions import get_or_compute_race_prediction
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()


TEAM_COLORS = {
    "red-bull": "#3671C6",
    "mclaren": "#FF8000",
    "ferrari": "#E8002D",
    "mercedes": "#27F4D2",
    "aston-martin": "#229971",
    "williams": "#64C4FF",
    "rb": "#6692FF",
    "haas": "#B6BABD",
    "alpine": "#FF87BC",
    "audi": "#E0E0E0",
    "cadillac": "#B6BABD",
}
MAX_GRID_POSITION = 22


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return int(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return float(value)


def safe_str(row: Any, key: str, default: str = "") -> str:
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return str(value)


def first_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else default
    return str(value)


def constructor_name_from_row(row: Any, default: str = "Unknown") -> str:
    if "constructorName" in row:
        return first_value(row.get("constructorName"), default)
    return first_value(row.get("constructorNames"), default)


def driver_full_name(row: Any) -> str:
    return f"{safe_str(row, 'givenName')} {safe_str(row, 'familyName')}".strip()


def driver_code_from_row(row: Any) -> str:
    code = safe_str(row, "driverCode").strip().upper()
    if code:
        return code

    family_name = safe_str(row, "familyName").strip().upper()
    if len(family_name) >= 3:
        return family_name[:3]

    driver_id = safe_str(row, "driverId").replace("_", "").strip().upper()
    return driver_id[:3] if driver_id else "TBC"


def normalise_driver_lookup(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def team_slug(name: str) -> str:
    return (
        name.lower()
        .replace(" racing", "")
        .replace(" f1 team", "")
        .replace(" team", "")
        .replace(" ", "-")
    )


def team_color(team_name: str) -> str:
    slug = team_slug(team_name)
    return TEAM_COLORS.get(slug, "#6B7280")


def format_points_value(value: float) -> str:
    return f"{value:g}"


def profile_for_team(team_name: str) -> dict:
    slug = team_slug(team_name)
    return {
        "slug": slug,
        "name": team_name,
        "color": team_color(team_name),
        "strengths": [],
        "weaknesses": [],
        "strategy_tendency": "Standing profile unavailable until constructor standings load.",
    }


def build_team_profile(row: dict, roster: list[dict], leader_points: float, completed_events: int) -> dict:
    points = safe_float(row.get("points", 0))
    wins = safe_int(row.get("wins", 0))
    position = safe_int(row.get("position", 0))
    gap_to_leader = max(0, leader_points - points)
    events = max(completed_events, 1)
    points_per_event = points / events
    driver_count = len(roster)
    top_driver = max(roster, key=lambda driver: driver.get("points", 0), default=None)
    top_share = (safe_float(top_driver.get("points", 0)) / points * 100) if top_driver and points else 0

    evidence = [
        f"WCC P{position}" if position else "No WCC rank",
        f"{format_points_value(points)} championship pts",
        f"{wins} race win{'s' if wins != 1 else ''}",
        f"{points_per_event:.1f} pts/GP",
    ]
    pressure_points = []
    if gap_to_leader:
        pressure_points.append(f"{format_points_value(gap_to_leader)} pts behind P1")
    else:
        pressure_points.append("Current constructor benchmark")
    if top_driver and points:
        pressure_points.append(f"{top_driver['driver']} has {top_share:.0f}% of team points")
    if driver_count:
        pressure_points.append(f"{driver_count} classified driver{'s' if driver_count != 1 else ''} in standings")

    if position == 1:
        tendency = (
            f"{row['team']} leads the constructors' table with {format_points_value(points)} points. "
            "The strategy read is defensive: protect high-value points swings and avoid unnecessary split risk."
        )
    elif gap_to_leader:
        tendency = (
            f"{row['team']} is P{position}, {format_points_value(gap_to_leader)} points off the constructor lead. "
            "The strategy read is opportunistic: use race scenarios that can close the championship gap without relying on invented pace data."
        )
    else:
        tendency = (
            f"{row['team']} has no constructor points loaded yet. The strategy read stays limited until the standings feed contains scoring data."
        )

    return {
        "slug": team_slug(row["team"]),
        "name": row["team"],
        "color": team_color(row["team"]),
        "strengths": evidence,
        "weaknesses": pressure_points,
        "strategy_tendency": tendency,
        "standing_profile": {
            "WCC position": position,
            "points": points,
            "wins": wins,
            "pts per GP": round(points_per_event, 1),
        },
    }


def build_strategy_dashboard(year: int) -> dict:
    """Build a lightweight race-strategy department overview."""

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
        {"id": "weekend-brief", "title": "Weekend Brief", "owner": "Strategy", "priority": "P1", "status": "Ready" if event else "Waiting", "href": "/race-control"},
        {"id": "race-model", "title": "Race Model", "owner": "Performance", "priority": "P1", "status": "Build", "href": "/race-control/strategy"},
        {"id": "rival-watch", "title": "Rival Watch", "owner": "Competitor Intel", "priority": "P2", "status": "Monitor", "href": "/race-control/teams"},
        {"id": "live-control", "title": "Live Control", "owner": "Pit Wall", "priority": "P1", "status": "Standby", "href": "/live"},
    ]


def get_standings_snapshot(year: int) -> tuple[list[dict], list[dict]]:
    ergast = Ergast()
    drivers = []
    constructors = []

    try:
        driver_data = ergast.get_driver_standings(season=year)
        if driver_data.content:
            for idx, (_, row) in enumerate(driver_data.content[0].iterrows(), start=1):
                drivers.append({
                    "position": safe_int(row.get("position", idx), idx),
                    "code": driver_code_from_row(row),
                    "driver": driver_full_name(row),
                    "team": constructor_name_from_row(row),
                    "points": safe_float(row.get("points", 0)),
                    "wins": safe_int(row.get("wins", 0)),
                })
    except Exception as exc:
        logger.warning("race_control.driver_snapshot.failed", year=year, error=str(exc))

    try:
        constructor_data = ergast.get_constructor_standings(season=year)
        if constructor_data.content:
            for idx, (_, row) in enumerate(constructor_data.content[0].iterrows(), start=1):
                constructors.append({
                    "position": safe_int(row.get("position", idx), idx),
                    "team": safe_str(row, "constructorName", "Unknown"),
                    "points": safe_float(row.get("points", 0)),
                    "wins": safe_int(row.get("wins", 0)),
                })
    except Exception as exc:
        logger.warning("race_control.constructor_snapshot.failed", year=year, error=str(exc))

    return drivers, constructors


def load_driver_standings(year: int) -> list[dict]:
    ergast = Ergast()
    driver_data = ergast.get_driver_standings(season=year)
    if not driver_data.content:
        return []

    standings = []
    for idx, (_, row) in enumerate(driver_data.content[0].iterrows(), start=1):
        standings.append({
            "code": driver_code_from_row(row),
            "name": driver_full_name(row),
            "team": constructor_name_from_row(row),
            "position": safe_int(row.get("position", idx), idx),
            "points": safe_float(row.get("points", 0)),
            "wins": safe_int(row.get("wins", 0)),
            "nationality": safe_str(row, "driverNationality"),
            "driver_id": safe_str(row, "driverId"),
        })
    return standings


def get_driver_options(year: int) -> dict:
    try:
        drivers = load_driver_standings(year)
    except Exception as exc:
        logger.warning("race_control.driver_options.failed", year=year, error=str(exc))
        return {
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "jolpica-ergast-driver-standings",
            "drivers": [],
            "error": "Driver standings are unavailable right now.",
        }

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jolpica-ergast-driver-standings",
        "drivers": drivers,
        "error": None if drivers else "No driver standings found for this season yet.",
    }


def find_driver(drivers: list[dict], query: str) -> dict | None:
    lookup = normalise_driver_lookup(query)
    if not lookup:
        return None

    exact_keys = ("code", "driver_id", "name")
    for driver in drivers:
        if any(normalise_driver_lookup(str(driver.get(key, ""))) == lookup for key in exact_keys):
            return driver

    for driver in drivers:
        if lookup in normalise_driver_lookup(driver["name"]):
            return driver
    return None


def completed_race_count(year: int) -> int | None:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control.completed_races.failed", year=year, error=str(exc))
        return None

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    completed = 0
    for _, row in schedule.iterrows():
        race_date = next(
            (
                row.get(f"Session{i}DateUtc").to_pydatetime()
                for i in range(1, 6)
                if row.get(f"Session{i}") == "Race" and pd.notna(row.get(f"Session{i}DateUtc"))
            ),
            None,
        )
        if race_date and now_utc > race_date + pd.Timedelta(hours=3):
            completed += 1
    return completed


def completed_race_rounds(year: int) -> tuple[list[int], int]:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control.completed_rounds.failed", year=year, error=str(exc))
        return [], 0

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    completed: list[int] = []
    total_events = 0
    for _, row in schedule.iterrows():
        total_events += 1
        race_date = next(
            (
                row.get(f"Session{i}DateUtc").to_pydatetime()
                for i in range(1, 6)
                if row.get(f"Session{i}") == "Race" and pd.notna(row.get(f"Session{i}DateUtc"))
            ),
            None,
        )
        if race_date and now_utc > race_date + pd.Timedelta(hours=3):
            completed.append(safe_int(row.get("RoundNumber")))
    return completed, total_events


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

    driver_rows = forecast_rows(
        entries=drivers,
        recent_points=recent_driver_points,
        completed_events=completed_events,
        loaded_recent_events=loaded_recent_events,
        remaining_events=remaining_events,
        key_getter=lambda row: row["code"],
        name_getter=lambda row: row["driver"],
        team_getter=lambda row: row["team"],
        type_label="driver",
    )
    constructor_rows = forecast_rows(
        entries=constructors,
        recent_points=recent_constructor_points,
        completed_events=completed_events,
        loaded_recent_events=loaded_recent_events,
        remaining_events=remaining_events,
        key_getter=lambda row: row["team"],
        name_getter=lambda row: row["team"],
        team_getter=lambda row: row["team"],
        type_label="constructor",
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


def forecast_rows(
    entries: list[dict],
    recent_points: dict[str, float],
    completed_events: int,
    loaded_recent_events: int,
    remaining_events: int,
    key_getter,
    name_getter,
    team_getter,
    type_label: str,
) -> list[dict]:
    base_events = max(completed_events, 1)
    recent_events = max(loaded_recent_events, 1)
    rows = []

    for entry in entries:
        key = str(key_getter(entry)).upper() if type_label == "driver" else str(key_getter(entry))
        current_points = safe_float(entry.get("points", 0))
        season_rate = current_points / base_events
        recent_rate = recent_points.get(key, 0) / recent_events if loaded_recent_events else season_rate
        form_rate = (recent_rate * 0.62) + (season_rate * 0.38)
        projected_points = current_points + form_rate * remaining_events
        trend_delta = recent_rate - season_rate

        if trend_delta > 1.5:
            trend = "Gaining"
        elif trend_delta < -1.5:
            trend = "Sliding"
        else:
            trend = "Holding"

        rows.append({
            "key": key,
            "code": entry.get("code"),
            "name": name_getter(entry),
            "team": team_getter(entry),
            "current_position": safe_int(entry.get("position")),
            "current_points": round(current_points, 1),
            "wins": safe_int(entry.get("wins", 0)),
            "season_points_per_event": round(season_rate, 2),
            "recent_points_per_event": round(recent_rate, 2),
            "projected_points": round(projected_points, 1),
            "trend": trend,
            "confidence": "Medium" if loaded_recent_events >= 3 else "Low",
        })

    rows.sort(key=lambda row: (-row["projected_points"], row["current_position"]))
    for index, row in enumerate(rows, start=1):
        row["projected_position"] = index
        row["position_delta"] = row["current_position"] - index
    return rows


def pluralise(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value} {singular if value == 1 else plural or singular + 's'}"


def battle_fact(key: str, label: str, driver1: dict, driver2: dict, value1: str, value2: str) -> dict:
    return {
        "key": key,
        "label": label,
        "values": {
            driver1["code"]: value1,
            driver2["code"]: value2,
        },
    }


def points_trend(points: float, completed_events: int) -> list[dict]:
    events = max(completed_events, 1)
    return [
        {"round": race_index, "points": round(points * ((race_index / events) ** 1.08), 1)}
        for race_index in range(1, events + 1)
    ]


def build_teams(year: int) -> dict:
    try:
        dashboard = build_strategy_dashboard(year)
        completed_events = dashboard["season"]["completed_events"]
    except Exception as exc:
        logger.warning("race_control.team_schedule.failed", year=year, error=str(exc))
        completed_events = 0

    drivers, constructors = get_standings_snapshot(year)

    teams = []
    leader_points = constructors[0]["points"] if constructors else 0
    for row in constructors:
        roster = [driver for driver in drivers if driver["team"] == row["team"]]
        profile = build_team_profile(row, roster, leader_points, completed_events)
        teams.append({
            **profile,
            "position": row["position"],
            "points": row["points"],
            "wins": row["wins"],
            "drivers": roster,
            "recent_form": points_trend(row["points"], min(max(completed_events, 1), 5))[-5:],
            "pace_profile": profile["standing_profile"],
        })

    if teams:
        return {
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "jolpica-ergast-constructor-standings",
            "drivers": drivers,
            "teams": teams,
            "error": None,
        }

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jolpica-ergast-constructor-standings",
        "drivers": drivers,
        "teams": [],
        "error": "Constructor standings are unavailable for this season.",
    }


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
    """Build decision-support context for the command center.

    This is deliberately transparent: values are derived from schedule,
    circuit profile, standings, and prediction snapshots rather than hidden
    telemetry. The UI labels them as operating assumptions.
    """

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


def simulate_strategy(request: StrategySimulationRequest) -> dict:
    start = max(1, min(MAX_GRID_POSITION, request.starting_position))
    current_lap = max(1, min(70, request.current_lap))
    pit_lap = max(1, min(70, request.pit_lap))
    if pit_lap <= current_lap:
        pit_lap = min(70, current_lap + 1)
    safety = max(0, min(100, request.safety_car_probability))
    weather = max(0, min(100, request.weather_risk))
    traffic = max(0, min(100, request.traffic_risk))
    compound = request.tyre_compound.upper()

    compound_life = {"SOFT": 18, "MEDIUM": 29, "HARD": 42, "INTERMEDIATE": 24, "WET": 20}.get(compound, 29)
    current_tyre_age = max(0, min(70, request.tyre_age))
    laps_to_stop = max(0, pit_lap - current_lap)
    tyre_age_at_stop = current_tyre_age + laps_to_stop
    life_used = tyre_age_at_stop / compound_life
    degradation = max(0.7, life_used * 1.35 + weather / 180 + traffic / 260)
    undercut_power = max(0, 2.6 - degradation + traffic / 120 + (start / 24))
    overcut_power = max(0, 2.0 - undercut_power / 2 + safety / 90 - max(0, life_used - 0.8) * 0.65)

    one_stop_score = (
        101
        - degradation * 18
        + safety * 0.16
        - weather * 0.12
        - traffic * 0.06
        - max(0, tyre_age_at_stop - compound_life) * 1.45
    )
    two_stop_score = (
        81
        + degradation * 11
        + weather * 0.16
        + traffic * 0.05
        - safety * 0.07
        - max(0, start - 8) * 0.55
    )
    recommended = "One-stop" if one_stop_score >= two_stop_score else "Two-stop"
    branch_delta = round(abs(one_stop_score - two_stop_score), 1)
    confidence = "High" if branch_delta >= 12 else "Medium" if branch_delta >= 5 else "Low"

    return {
        "race": request.race,
        "team": request.team,
        "driver": request.driver,
        "inputs": request.dict(),
        "recommendation": {
            "plan": recommended,
            "pit_window": recommended_pit_window(recommended, pit_lap),
            "confidence": confidence,
            "branch_delta": branch_delta,
            "rationale": (
                "Track position is favored; tyre age stays inside the working life."
                if recommended == "One-stop"
                else "Tyre age and rejoin traffic make a second stop worth modeling."
            ),
        },
        "stint": {
            "current_lap": current_lap,
            "tyre_age_now": current_tyre_age,
            "tyre_age_at_stop": tyre_age_at_stop,
            "compound_life": compound_life,
            "life_used_pct": round(life_used * 100),
            "laps_to_stop": laps_to_stop,
        },
        "plans": [
            build_one_stop_plan(start, pit_lap, one_stop_score, degradation, weather, tyre_age_at_stop, compound_life, traffic),
            build_two_stop_plan(start, pit_lap, two_stop_score, safety, traffic, tyre_age_at_stop),
        ],
        "model_inputs": build_strategy_model_inputs(
            request,
            compound_life,
            tyre_age_at_stop,
            degradation,
            undercut_power,
            overcut_power,
        ),
        "decision_matrix": build_strategy_decision_matrix(
            recommended,
            one_stop_score,
            two_stop_score,
            tyre_age_at_stop,
            compound_life,
            traffic,
            safety,
            weather,
        ),
        "battle_cards": [
            {"label": "Undercut", "value": round(undercut_power, 2), "call": "Attack" if undercut_power > 1.5 else "Monitor"},
            {"label": "Overcut", "value": round(overcut_power, 2), "call": "Viable" if overcut_power > 1.3 else "Weak"},
            {"label": "Tyre Age", "value": tyre_age_at_stop, "call": "Critical" if tyre_age_at_stop > compound_life else "Usable"},
            {"label": "Rejoin Traffic", "value": traffic, "call": "High risk" if traffic > 65 else "Manageable"},
        ],
    }


def build_strategy_model_inputs(
    request: StrategySimulationRequest,
    compound_life: int,
    tyre_age_at_stop: int,
    degradation: float,
    undercut_power: float,
    overcut_power: float,
) -> list[dict]:
    tyre_margin = compound_life - tyre_age_at_stop
    return [
        {
            "label": "Tyre life margin",
            "value": f"{tyre_margin:+d} laps",
            "impact": "Positive margin supports extending; negative margin pushes toward a second stop.",
            "source": f"{request.tyre_compound.upper()} nominal life minus age at stop",
            "tone": "good" if tyre_margin >= 5 else "warning" if tyre_margin >= 0 else "critical",
        },
        {
            "label": "Degradation pressure",
            "value": f"{degradation:.2f}",
            "impact": "Higher pressure penalizes the one-stop branch and raises cliff risk.",
            "source": "tyre age, rain risk, and rejoin traffic inputs",
            "tone": "critical" if degradation > 1.55 else "warning" if degradation > 1.25 else "good",
        },
        {
            "label": "Undercut strength",
            "value": f"{undercut_power:.2f}s",
            "impact": "Higher undercut strength favors stopping before rivals inside pit-loss range.",
            "source": "traffic risk, track position, and tyre pressure heuristic",
            "tone": "good" if undercut_power >= 1.5 else "warning",
        },
        {
            "label": "Overcut strength",
            "value": f"{overcut_power:.2f}s",
            "impact": "Higher overcut strength supports extending for clean air or safety-car timing.",
            "source": "safety-car probability and tyre-life reserve heuristic",
            "tone": "good" if overcut_power >= 1.3 else "warning",
        },
    ]


def build_strategy_decision_matrix(
    recommended: str,
    one_stop_score: float,
    two_stop_score: float,
    tyre_age_at_stop: int,
    compound_life: int,
    traffic: int,
    safety: int,
    weather: int,
) -> list[dict]:
    return [
        {
            "gate": "Commit / keep open",
            "status": "Commit" if abs(one_stop_score - two_stop_score) >= 12 else "Keep both branches open",
            "detail": f"{recommended} leads by {abs(one_stop_score - two_stop_score):.1f} model points.",
        },
        {
            "gate": "Tyre cliff",
            "status": "Critical" if tyre_age_at_stop > compound_life else "Inside life",
            "detail": f"Target stop reaches {tyre_age_at_stop} laps against a {compound_life}-lap nominal life.",
        },
        {
            "gate": "Rejoin traffic",
            "status": "Hold" if traffic >= 65 else "Attack window usable",
            "detail": f"Traffic risk is {traffic}%; avoid blind stops above 65%.",
        },
        {
            "gate": "Race disruption",
            "status": "Prepare branch" if safety >= 45 or weather >= 45 else "Base plan",
            "detail": f"Safety car {safety}% and rain {weather}% set the contingency load.",
        },
    ]


def recommended_pit_window(plan: str, pit_lap: int) -> str:
    start = max(1, pit_lap - (4 if plan == "One-stop" else 3))
    end = min(70, pit_lap + (5 if plan == "One-stop" else 3))
    return f"L{start}-L{end}"


def build_one_stop_plan(
    start: int,
    pit_lap: int,
    score: float,
    degradation: float,
    weather: int,
    tyre_age_at_stop: int,
    compound_life: int,
    traffic: int,
) -> dict:
    expected_finish = max(1, min(MAX_GRID_POSITION, round(start - (score - 70) / 8)))
    tyre_note = f"Tyres reach lap {tyre_age_at_stop} at the stop; nominal life is {compound_life} laps"
    return {
        "name": "One-stop",
        "score": round(score, 1),
        "expected_finish": f"P{expected_finish}",
        "pit_window": recommended_pit_window("One-stop", pit_lap),
        "risk": "High" if degradation > 1.55 or weather > 55 or traffic > 70 else "Medium",
        "notes": [tyre_note, "Protect clean air", "Avoid pitting into traffic", "High value if safety car arrives after stop window"],
    }


def build_two_stop_plan(start: int, pit_lap: int, score: float, safety: int, traffic: int, tyre_age_at_stop: int) -> dict:
    expected_finish = max(1, min(MAX_GRID_POSITION, round(start - (score - 70) / 8 + 1)))
    return {
        "name": "Two-stop",
        "score": round(score, 1),
        "expected_finish": f"P{expected_finish}",
        "pit_window": f"L{max(1, pit_lap - 10)} and L{pit_lap + 12}",
        "risk": "High" if start > 10 and safety < 25 and traffic > 55 else "Medium",
        "notes": [f"First stop catches tyres at lap {tyre_age_at_stop}", "Needs overtake delta", "Better if degradation accelerates", "Avoid if DRS trains are likely"],
    }


def build_driver_battle(year: int, driver1: str, driver2: str) -> dict:
    driver_feed = get_driver_options(year)
    standings = driver_feed["drivers"]
    if not standings:
        return {
            "year": year,
            "status": "data_unavailable",
            "source": driver_feed["source"],
            "drivers": [],
            "metrics": [],
            "summary": "Driver standings are unavailable, so no priority call has been generated.",
            "recommendation": "Reconnect the standings feed or choose a season with completed standings data.",
            "data_limitations": ["No fallback or synthetic driver scores are used on this screen."],
            "error": driver_feed["error"],
        }

    d1 = find_driver(standings, driver1)
    d2 = find_driver(standings, driver2)
    if not d1 or not d2:
        missing = driver1 if not d1 else driver2
        return {
            "year": year,
            "status": "driver_not_found",
            "source": driver_feed["source"],
            "drivers": [driver for driver in (d1, d2) if driver],
            "available_drivers": standings,
            "metrics": [],
            "summary": f"'{missing}' was not found in the {year} driver standings.",
            "recommendation": "Select drivers from the standings-backed list rather than typing an abbreviation.",
            "data_limitations": ["Driver matching accepts codes, full names, and Ergast driver ids."],
            "error": f"Driver '{missing}' not found.",
        }

    if d1["code"] == d2["code"]:
        return {
            "year": year,
            "status": "invalid_selection",
            "source": driver_feed["source"],
            "drivers": [d1],
            "metrics": [],
            "summary": "Choose two different drivers to compare.",
            "recommendation": "Use the driver selectors to build a valid battle profile.",
            "data_limitations": [],
            "error": "Both selected drivers are the same.",
        }

    team_points: dict[str, float] = {}
    for driver in standings:
        team_points[driver["team"]] = team_points.get(driver["team"], 0) + driver["points"]

    def team_share(driver: dict) -> float:
        total = team_points.get(driver["team"], 0)
        return (driver["points"] / total) * 100 if total else 0

    completed_races = completed_race_count(year)
    d1_rate = d1["points"] / completed_races if completed_races else None
    d2_rate = d2["points"] / completed_races if completed_races else None
    points_gap = abs(d1["points"] - d2["points"])
    position_gap = abs(d1["position"] - d2["position"])
    wins_gap = abs(d1["wins"] - d2["wins"])
    same_team = d1["team"] == d2["team"]

    raw_leader, raw_chaser = (
        (d1, d2)
        if (d1["points"], d1["wins"], -d1["position"]) >= (d2["points"], d2["wins"], -d2["position"])
        else (d2, d1)
    )
    close_call = points_gap < 10 and position_gap <= 1 and wins_gap <= 1
    priority_confidence = "Low" if close_call else "High" if points_gap >= 50 or position_gap >= 5 else "Medium"

    facts = [
        battle_fact("wdc_position", "Championship position", d1, d2, f"P{d1['position']}", f"P{d2['position']}"),
        battle_fact("points", "Championship points", d1, d2, f"{d1['points']:g}", f"{d2['points']:g}"),
        battle_fact("wins", "Race wins", d1, d2, pluralise(d1["wins"], "win"), pluralise(d2["wins"], "win")),
        battle_fact("team_share", "Share of team points", d1, d2, f"{team_share(d1):.1f}%", f"{team_share(d2):.1f}%"),
    ]
    if completed_races and d1_rate is not None and d2_rate is not None:
        facts.append(
            battle_fact(
                "points_per_race",
                "Points per completed GP",
                d1,
                d2,
                f"{d1_rate:.1f}",
                f"{d2_rate:.1f}",
            )
        )

    decision_factors = [
        f"Points gap: {points_gap:g} point{'s' if points_gap != 1 else ''}.",
        f"Championship order gap: {position_gap} position{'s' if position_gap != 1 else ''}.",
        f"Wins gap: {wins_gap} race win{'s' if wins_gap != 1 else ''}.",
    ]
    if same_team:
        decision_factors.append("Same team comparison: this is useful for first pit call, upgrade priority, and avoiding a strategy split that hurts constructor points.")
    else:
        decision_factors.append("Rival comparison: this is useful for deciding which car to cover when pit windows overlap.")
    if completed_races:
        decision_factors.append(f"Scoring rate uses {completed_races} completed Grand Prix event{'s' if completed_races != 1 else ''}.")

    if close_call:
        summary = (
            f"{d1['name']} and {d2['name']} are close enough that standings alone should not decide priority."
        )
        recommendation = (
            "Do not assign priority from standings alone. Wait for qualifying, tyre degradation, and live track-position data before splitting strategy."
        )
    else:
        summary = f"{raw_leader['name']} has the stronger standings case: P{raw_leader['position']} with {raw_leader['points']:g} points versus P{raw_chaser['position']} with {raw_chaser['points']:g}."
        if same_team:
            recommendation = (
                f"Give {raw_leader['name']} first call only if both cars converge on the same pit window. Keep "
                f"{raw_chaser['name']} available for an offset that protects constructor points."
            )
        else:
            recommendation = (
                f"Treat {raw_leader['name']} as the higher-priority rival in scenario planning. Cover undercut windows when "
                f"{raw_leader['team']} is inside pit-loss range, but override this with live tyre and track-position evidence."
            )

    return {
        "year": year,
        "status": "ok",
        "source": driver_feed["source"],
        "drivers": [d1, d2],
        "summary": summary,
        "metrics": [],
        "facts": facts,
        "decision_factors": decision_factors,
        "priority": {
            "code": None if close_call else raw_leader["code"],
            "driver": "No automatic priority" if close_call else raw_leader["name"],
            "team": None if close_call else raw_leader["team"],
            "confidence": priority_confidence,
            "basis": "current championship standings",
        },
        "recommendation": recommendation,
        "comparison": {
            "points_gap": round(points_gap, 1),
            "position_gap": position_gap,
            "wins_gap": wins_gap,
            "context": "same-team" if same_team else "rival-comparison",
        },
        "data_limitations": [
            "Uses real championship standings only.",
            "Does not claim live race pace, sector strength, tyre degradation, or telemetry until session data is connected.",
        ],
        "error": None,
    }


def build_race_debrief(year: int, round_num: int) -> dict:
    detail = load_race_classification(year, round_num)
    podium = detail.get("podium") or []
    results = detail.get("race_results") or []
    winner = podium[0] if podium else None
    movers = sorted(
        [row for row in results if row.get("grid") and row.get("position")],
        key=lambda row: row["grid"] - row["position"],
        reverse=True,
    )[:3]
    constructor_impact = build_constructor_impact(results)
    reliability = [
        row for row in results
        if row.get("status") and row["status"] != "Finished" and "Lap" not in row["status"]
    ]

    return {
        "year": year,
        "round": round_num,
        "race": detail.get("name", f"Round {round_num}"),
        "location": detail.get("location", ""),
        "podium": podium,
        "headline": (
            build_debrief_headline(detail, winner, results)
            if winner
            else "Race classification is not available yet."
        ),
        "strategy_winners": movers,
        "takeaways": build_debrief_takeaways(results, podium),
        "podium_cause": build_podium_cause(podium),
        "constructor_impact": constructor_impact,
        "reliability_watch": reliability[:5],
        "classification": results[:10],
        "race_control_notes": build_race_control_notes(results, podium, movers, constructor_impact, reliability),
        "insight_source": "Derived from race classification, grid positions, finishing status, and points.",
        "incidents": [],
    }


def build_debrief_headline(detail: dict, winner: dict | None, results: list[dict]) -> str:
    if not winner:
        return "Race classification is not available yet."

    start = winner.get("grid")
    finish = winner.get("position")
    if start and finish:
        if start == finish:
            return f"{winner['full_name']} converted pole or track position into the race win at {detail.get('name', 'the Grand Prix')}."
        if start > finish:
            gained = start - finish
            return f"{winner['full_name']} won from P{start}, gaining {gained} place{'s' if gained != 1 else ''} against the starting grid."

    points = winner.get("points")
    if points:
        return f"{winner['full_name']} led the final classification and banked {points:g} points for {winner.get('team', 'the team')}."
    return f"{winner['full_name']} topped the final classification."


def build_debrief_takeaways(results: list[dict], podium: list[dict]) -> list[str]:
    if not results:
        return []

    takeaways: list[str] = []
    rows_with_grid = [row for row in results if row.get("grid") and row.get("position")]
    movers = sorted(rows_with_grid, key=lambda row: row["grid"] - row["position"], reverse=True)
    losses = sorted(rows_with_grid, key=lambda row: row["grid"] - row["position"])

    if podium:
        podium_teams = defaultdict(int)
        for row in podium:
            podium_teams[row.get("team", "Unknown")] += 1
        top_team, count = max(podium_teams.items(), key=lambda item: item[1])
        takeaways.append(
            f"{top_team} placed {count} car{'s' if count != 1 else ''} on the podium, shaping the main points swing."
        )

    if movers:
        best = movers[0]
        gain = best["grid"] - best["position"]
        if gain > 0:
            takeaways.append(
                f"{best['full_name'] or best['driver']} gained {gain} position{'s' if gain != 1 else ''} from the grid, the clearest strategy or execution gain."
            )

    if losses:
        worst = losses[0]
        loss = worst["position"] - worst["grid"]
        if loss > 0:
            takeaways.append(
                f"{worst['full_name'] or worst['driver']} lost {loss} position{'s' if loss != 1 else ''} versus the grid, flagging a compromised race branch."
            )

    team_points: dict[str, float] = defaultdict(float)
    for row in results:
        team_points[row.get("team", "Unknown")] += safe_float(row.get("points", 0))
    if team_points:
        team, points = max(team_points.items(), key=lambda item: item[1])
        if points > 0:
            takeaways.append(f"{team} scored the strongest constructor haul with {points:g} points.")

    non_standard_statuses = [
        row for row in results
        if row.get("status") and row["status"] != "Finished" and "Lap" not in row["status"]
    ]
    if non_standard_statuses:
        takeaways.append(
            f"{len(non_standard_statuses)} car{'s' if len(non_standard_statuses) != 1 else ''} had non-standard finish statuses, so reliability and incident exposure mattered."
        )

    return takeaways[:4]


def build_podium_cause(podium: list[dict]) -> list[dict]:
    rows = []
    for row in podium:
        grid = row.get("grid")
        position = row.get("position")
        delta = grid - position if grid and position else None
        if delta is None:
            call = "Classification result"
        elif delta > 0:
            call = f"Made up {delta} place{'s' if delta != 1 else ''}"
        elif delta < 0:
            call = f"Lost {abs(delta)} place{'s' if delta != -1 else ''} but held podium"
        else:
            call = "Converted starting position"
        rows.append({
            "position": position,
            "driver": row.get("driver"),
            "full_name": row.get("full_name") or row.get("driver"),
            "team": row.get("team"),
            "grid": grid,
            "points": row.get("points", 0),
            "delta": delta,
            "call": call,
        })
    return rows


def build_constructor_impact(results: list[dict]) -> list[dict]:
    team_points: dict[str, float] = defaultdict(float)
    finishers: dict[str, int] = defaultdict(int)
    for row in results:
        team = row.get("team", "Unknown")
        team_points[team] += safe_float(row.get("points", 0))
        if row.get("position"):
            finishers[team] += 1
    return [
        {"team": team, "points": points, "classified_cars": finishers.get(team, 0)}
        for team, points in sorted(team_points.items(), key=lambda item: item[1], reverse=True)
        if points > 0
    ][:6]


def build_race_control_notes(
    results: list[dict],
    podium: list[dict],
    movers: list[dict],
    constructor_impact: list[dict],
    reliability: list[dict],
) -> list[dict]:
    notes = []
    if podium:
        notes.append({
            "label": "Podium shape",
            "detail": ", ".join(f"P{row.get('position')} {row.get('driver')}" for row in podium),
        })
    if movers:
        best = movers[0]
        notes.append({
            "label": "Execution swing",
            "detail": f"{best.get('full_name') or best.get('driver')} gained {best.get('grid') - best.get('position')} places from the grid.",
        })
    if constructor_impact:
        leader = constructor_impact[0]
        notes.append({
            "label": "Constructor haul",
            "detail": f"{leader['team']} led the points take with {leader['points']:g} points.",
        })
    if reliability:
        notes.append({
            "label": "Reliability / incidents",
            "detail": f"{len(reliability)} non-standard finish status{'es' if len(reliability) != 1 else ''} in classification.",
        })
    if not results:
        notes.append({
            "label": "Awaiting classification",
            "detail": "Final race classification has not been published or loaded yet.",
        })
    return notes


def load_race_classification(year: int, round_num: int) -> dict:
    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    event_row = schedule[schedule["RoundNumber"] == round_num]
    if event_row.empty:
        return {"error": f"Round {round_num} not found for {year}", "race_results": [], "podium": []}

    event = event_row.iloc[0]
    result = {
        "round": round_num,
        "name": event["EventName"],
        "location": f"{event['Location']}, {event['Country']}",
        "race_results": [],
        "podium": [],
    }

    race_date = next(
        (
            event[f"Session{i}DateUtc"].to_pydatetime()
            for i in range(1, 6)
            if event.get(f"Session{i}") == "Race" and pd.notna(event.get(f"Session{i}DateUtc"))
        ),
        None,
    )
    if not race_date or datetime.now(timezone.utc).replace(tzinfo=None) <= race_date + pd.Timedelta(hours=3):
        return result

    session = fastf1.get_session(year, round_num, "R")
    session.load(telemetry=False, laps=False, weather=False)
    race_results = session.results.sort_values(by="Position")
    rows = []
    for _, row in race_results.iterrows():
        rows.append({
            "position": safe_int(row.get("Position"), None),
            "driver": row.get("Abbreviation", ""),
            "full_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
            "team": row.get("TeamName", "Unknown"),
            "grid": safe_int(row.get("GridPosition"), None) if pd.notna(row.get("GridPosition")) and row.get("GridPosition") > 0 else None,
            "points": safe_float(row.get("Points", 0)),
            "status": row.get("Status", ""),
        })
    result["race_results"] = rows
    result["podium"] = sorted([row for row in rows if row["position"] and row["position"] <= 3], key=lambda row: row["position"])
    return result


def build_intel(team_slug_value: str, year: int | None = None) -> dict:
    resolved_year = year or datetime.now(timezone.utc).year
    drivers, constructors = get_standings_snapshot(resolved_year)
    if not constructors:
        return {
            "year": resolved_year,
            "source": "jolpica-ergast-standings",
            "status": "data_unavailable",
            "team": profile_for_team(team_slug_value.replace("-", " ").title()),
            "upgrade_watch": [],
            "threats": [],
            "opportunities": [],
            "error": "Constructor standings are unavailable.",
        }

    match = next((row for row in constructors if team_slug(row["team"]) == team_slug_value), None)
    if not match:
        return {
            "year": resolved_year,
            "source": "jolpica-ergast-standings",
            "status": "team_not_found",
            "team": profile_for_team(team_slug_value.replace("-", " ").title()),
            "upgrade_watch": [],
            "threats": [],
            "opportunities": [],
            "available_teams": [{"slug": team_slug(row["team"]), "name": row["team"]} for row in constructors],
            "error": f"Team '{team_slug_value}' was not found in the constructor standings.",
        }

    roster = [driver for driver in drivers if driver["team"] == match["team"]]
    leader_points = constructors[0]["points"] if constructors else 0
    completed_events = completed_race_count(resolved_year)
    profile = build_team_profile(match, roster, leader_points, completed_events)
    position = safe_int(match.get("position", 0))
    points = safe_float(match.get("points", 0))
    wins = safe_int(match.get("wins", 0))
    leader = constructors[0]
    ahead = constructors[position - 2] if position > 1 and position - 2 < len(constructors) else None
    behind = constructors[position] if position < len(constructors) else None
    gap_ahead = safe_float(ahead["points"] - points) if ahead else 0
    gap_behind = safe_float(points - behind["points"]) if behind else 0
    top_driver = max(roster, key=lambda driver: driver.get("points", 0), default=None)

    evidence = [
        f"WCC P{position} with {format_points_value(points)} points.",
        f"{wins} constructor win{'s' if wins != 1 else ''} in the standings feed.",
        f"Leader gap: {format_points_value(max(0, leader['points'] - points))} points to {leader['team']}.",
    ]
    if top_driver:
        evidence.append(
            f"Top scorer: {top_driver['driver']} with {format_points_value(top_driver['points'])} points."
        )
    if ahead:
        evidence.append(f"Next target ahead: {ahead['team']} by {format_points_value(gap_ahead)} points.")
    if behind:
        evidence.append(f"Nearest pressure behind: {behind['team']} by {format_points_value(gap_behind)} points.")

    threats = []
    if ahead and gap_ahead <= 25:
        threats.append(f"{ahead['team']} is within {format_points_value(gap_ahead)} points ahead; covering them can matter immediately.")
    if behind and gap_behind <= 25:
        threats.append(f"{behind['team']} is only {format_points_value(gap_behind)} points behind; one race swing can change the order.")
    if top_driver and points and (safe_float(top_driver["points"]) / points) >= 0.7:
        threats.append(f"Points are concentrated through {top_driver['driver']}; losing that car has high constructor impact.")
    if not threats:
        threats.append("No close constructor-table threat is visible from current standings alone.")

    opportunities = []
    if ahead:
        opportunities.append(f"Close the gap to {ahead['team']} by targeting points swings above {format_points_value(gap_ahead)}.")
    if behind:
        opportunities.append(f"Protect against {behind['team']} by prioritising finishes that keep the gap above {format_points_value(gap_behind)}.")
    if roster and len(roster) > 1:
        opportunities.append("Use both cars in scenario planning because the roster has multiple classified points sources.")
    if position == 1:
        opportunities.append("Leader control: minimise low-probability strategy branches when direct rivals are behind.")

    return {
        "year": resolved_year,
        "source": "jolpica-ergast-constructor-and-driver-standings",
        "status": "ok",
        "team": profile,
        "drivers": roster,
        "upgrade_watch": evidence,
        "threats": threats,
        "opportunities": opportunities,
        "error": None,
    }
