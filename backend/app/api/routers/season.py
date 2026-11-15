"""Season schedule and championship standings routes.

Both standings read f1db, whose names are canonical. A season f1db has no
table for yet answers an empty list.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.api.errors import client_error
from app.data.f1db_calendar import season_schedule
from app.data.f1db_standings import (
    constructor_standings_detailed,
    driver_standings_detailed,
)
from app.utils.f1_values import safe_int, utc_isoformat

logger = structlog.get_logger()
router = APIRouter(tags=["season"])


@router.get("/schedule/{year}")
async def get_schedule(year: int) -> list[dict] | dict:
    """Returns the full season schedule for `year` with UTC timestamps, from f1db's calendar."""

    try:
        schedule = season_schedule(year)
        return [build_schedule_event(row) for _, row in schedule.iterrows()]
    except Exception as exc:
        return client_error("api.schedule.error", exc, year=year)


def build_schedule_event(row: pd.Series) -> dict:
    event_date = row["EventDate"].isoformat()
    if not event_date.endswith("Z") and "+" not in event_date:
        event_date += "Z"

    location = f"{row['Location']}, {row['Country']}"
    event = {
        "round": safe_int(row["RoundNumber"]),
        "name": row["EventName"],
        "location": location,
        "date": event_date,
        "sessions": {},
        "circuit": get_circuit_info(location),
    }

    first_session_date = None
    last_session_date = None
    for i in range(1, 6):
        name_col = f"Session{i}"
        date_col = f"Session{i}DateUtc"
        if name_col not in row or pd.isna(row[name_col]):
            continue
        session_date = row[date_col]
        if pd.isna(session_date):
            continue

        event["sessions"][row[name_col]] = utc_isoformat(session_date)
        timestamp = session_date.to_pydatetime()
        first_session_date = timestamp if first_session_date is None else min(first_session_date, timestamp)
        last_session_date = timestamp if last_session_date is None else max(last_session_date, timestamp)

    event["is_sprint"] = "Sprint" in event["sessions"]
    # f1db sets no session times before 2024; such a weekend is dated by race day.
    last_session_date = last_session_date or row["EventDate"].to_pydatetime()
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    if last_session_date and now_utc > last_session_date + pd.Timedelta(hours=3):
        event["status"] = "completed"
    elif first_session_date and now_utc >= first_session_date:
        event["status"] = "in_progress"
    else:
        event["status"] = "upcoming"
    return event


@router.get("/standings/drivers/{year}")
async def get_driver_standings(year: int) -> list[dict]:
    """Returns World Drivers' Championship standings for `year`."""

    # f1db: no rate limits, and it carries the current season.
    detailed = driver_standings_detailed(year)
    if detailed:
        return [
            {
                "position": row["position"],
                "driver": row["name"],
                "team": row["team"],
                "points": row["points"],
                "wins": row["wins"],
            }
            for row in detailed
        ]

    return []


@router.get("/standings/constructors/{year}")
async def get_constructor_standings(year: int) -> list[dict]:
    """Returns World Constructors' Championship standings for `year`."""

    # f1db: no rate limits, and it carries the current season.
    detailed = constructor_standings_detailed(year)
    if detailed:
        return [
            {
                "position": row["position"],
                "team": row["team"],
                "points": row["points"],
                "wins": row["wins"],
            }
            for row in detailed
        ]

    return []
