"""Race classification loading and post-race debrief generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import fastf1
import pandas as pd

from app.services.race_control_common import safe_float, safe_int


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
