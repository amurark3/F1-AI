"""Constructor, driver standings, and team-intelligence composition."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.services.race_control_common import (
    completed_race_count,
    format_points_value,
    get_standings_snapshot,
    safe_float,
    safe_int,
    team_color,
    team_slug,
)

logger = structlog.get_logger()


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


def points_trend(points: float, completed_events: int) -> list[dict]:
    events = max(completed_events, 1)
    return [
        {"round": race_index, "points": round(points * ((race_index / events) ** 1.08), 1)}
        for race_index in range(1, events + 1)
    ]


def build_teams(year: int) -> dict:
    completed_events = completed_race_count(year) or 0
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
    completed_events = completed_race_count(resolved_year) or 0
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
