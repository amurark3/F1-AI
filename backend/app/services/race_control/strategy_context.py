"""Strategy context: the dashboard block and the numbers behind it."""

from __future__ import annotations

from datetime import UTC, datetime

import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.data.current_standings import current_standings
from app.services.race_control.live import live_session
from app.services.race_control.risk import RIVAL_GAP_MODERATE
from app.services.race_control.stakes import build_championship_stakes
from app.services.race_control.workstreams import focus_for_event
from app.services.race_control_common import safe_int
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()


def season_events(year: int) -> list[dict]:
    """Build the season's event list from the schedule, with derived status."""

    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    now_utc = datetime.now(UTC).replace(tzinfo=None)

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

        events.append(
            {
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
            }
        )

    return events


def select_event(events: list[dict]) -> dict | None:
    """Pick the event the command centre should be planning right now.

    A weekend that is under way wins; otherwise the next one on the calendar;
    otherwise the last race of a finished season.
    """
    active_event = next((event for event in events if event["status"] == "in_progress"), None)
    next_event = next((event for event in events if event["status"] == "upcoming"), None)
    return active_event or next_event or (events[-1] if events else None)


def build_strategy_dashboard(year: int) -> dict:
    """Build the command-center shell from schedule and standings data.

    The standings are ``current_standings``'s, so the stakes count from the
    newest round with published points, not f1db's last release.
    """

    events = season_events(year)
    selected_event = select_event(events)
    standings = current_standings(year)

    return {
        "year": year,
        "generated_at": datetime.now(UTC).isoformat(),
        "focus": focus_for_event(selected_event),
        "race": selected_event,
        "season": {
            "total_events": len(events),
            "completed_events": len([event for event in events if event["status"] == "completed"]),
            "upcoming_events": len([event for event in events if event["status"] == "upcoming"]),
        },
        "championship": {
            "drivers": standings.driver_rows()[:5],
            "constructors": standings.team_rows()[:5],
            **standings.meta(),
        },
        "stakes": build_championship_stakes(events, selected_event, standings),
    }


def build_competitor_rows(constructors: list[dict]) -> list[dict]:
    """Rank the top constructors by championship gap, with an operating read."""

    leader_points = constructors[0]["points"] if constructors else 0
    rows = []
    for index, team in enumerate(constructors[:5], start=1):
        gap = max(0, leader_points - team["points"])
        rows.append(
            {
                "rank": index,
                "team": team["team"],
                "points": team["points"],
                "gap_to_leader": round(gap, 1),
                "threat": "Primary" if index == 1 else "High" if gap <= RIVAL_GAP_MODERATE else "Monitor",
                "operating_read": (
                    "Benchmark car; protect against clean-air extensions."
                    if index == 1
                    else "Undercut exposure if they qualify within one pit-loss window."
                    if gap <= RIVAL_GAP_MODERATE
                    else "Scenario dependent; watch safety-car offsets."
                ),
            }
        )
    return rows


def build_strategy_context(race: dict | None, constructors: list[dict], baseline: dict) -> dict:
    """Decision-support context for the command center: the baseline plan and the rivals.

    ``baseline`` is :func:`app.services.race_control.baseline_plan.build_baseline`'s
    plan from the latest same-circuit edition, which invents no number: with no
    edition it says why there is no plan.
    """
    return {
        "phase": "Live race desk" if live_session(race) else "Pre-race build",
        **baseline,
        "competitors": build_competitor_rows(constructors),
    }
