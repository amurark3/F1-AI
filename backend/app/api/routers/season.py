"""Season schedule and championship standings routes.

Both standings read f1db, whose names are canonical. The Ergast (Jolpica)
fallback prints f1db's names too: a driver resolves from Jolpica's code, car
number and name, never its ``driverId`` ("max_verstappen" is not an f1db id),
and a team from its spelling ("RB F1 Team" -> "Racing Bulls"). Jolpica's own
words stay when f1db cannot say. See :mod:`app.data.canonical_names`.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
import fastf1
from fastf1.ergast import Ergast
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.api.errors import client_error
from app.data.canonical_names import driver_identity, team_display_name
from app.data.f1db_standings import (
    constructor_standings_detailed,
    driver_standings_detailed,
)
from app.utils.f1_values import safe_float, safe_int, safe_str, utc_isoformat

logger = structlog.get_logger()
router = APIRouter(tags=["season"])


@router.get("/schedule/{year}")
async def get_schedule(year: int) -> list[dict] | dict:
    """Returns the full season schedule for `year` with UTC timestamps."""

    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
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

    # f1db first — no rate limits and carries the current season; Ergast fallback.
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

    try:
        ergast = Ergast()
        data = ergast.get_driver_standings(season=year)
        if data.content:
            return [
                build_driver_standing(row, idx, year)
                for idx, (_, row) in enumerate(data.content[0].iterrows(), start=1)
            ]
        return build_zero_point_driver_standings(ergast, year)
    except Exception as exc:
        logger.exception("api.driver_standings.error", error=str(exc))
        return []


def jolpica_driver_name(row: pd.Series, year: int) -> str:
    """f1db's name for a Jolpica driver row, from its code, number and name; Jolpica's driverId is never used."""
    feed_name = f"{safe_str(row, 'givenName')} {safe_str(row, 'familyName')}".strip()
    return driver_identity(year, code=row.get("driverCode"), number=row.get("driverNumber"), name=feed_name).name


def build_driver_standing(row: pd.Series, fallback_position: int, year: int) -> dict:
    has_position = "position" in row and not (isinstance(row["position"], float) and pd.isna(row["position"]))
    team_name = "Unknown"
    if "constructorName" in row:
        team_name = row["constructorName"]
    elif "constructorNames" in row:
        names = row["constructorNames"]
        team_name = names[-1] if isinstance(names, list) and names else str(names)

    return {
        "position": safe_int(row["position"]) if has_position else fallback_position,
        "driver": jolpica_driver_name(row, year),
        "team": team_display_name(year, team_name) or "Unknown",
        "points": safe_float(row.get("points", 0)),
        "wins": safe_int(row.get("wins", 0)),
    }


def build_zero_point_driver_standings(ergast: Ergast, year: int) -> list[dict]:
    constructors = ergast.get_constructor_info(season=year)
    if constructors.empty:
        return []

    results = []
    position = 1
    for _, constructor in constructors.iterrows():
        drivers = ergast.get_driver_info(season=year, constructor=constructor["constructorId"])
        for _, driver in drivers.iterrows():
            results.append(
                {
                    "position": position,
                    "driver": jolpica_driver_name(driver, year),
                    "team": team_display_name(year, constructor["constructorName"]),
                    "points": 0.0,
                    "wins": 0,
                }
            )
            position += 1
    return results


@router.get("/standings/constructors/{year}")
async def get_constructor_standings(year: int) -> list[dict]:
    """Returns World Constructors' Championship standings for `year`."""

    # f1db first — no rate limits and carries the current season; Ergast fallback.
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

    try:
        ergast = Ergast()
        data = ergast.get_constructor_standings(season=year)
        if data.content:
            return [
                build_constructor_standing(row, idx, year)
                for idx, (_, row) in enumerate(data.content[0].iterrows(), start=1)
            ]
        return build_zero_point_constructor_standings(ergast, year)
    except Exception as exc:
        logger.exception("api.constructor_standings.error", error=str(exc))
        return []


def build_constructor_standing(row: pd.Series, fallback_position: int, year: int) -> dict:
    has_position = "position" in row and not (isinstance(row["position"], float) and pd.isna(row["position"]))
    return {
        "position": safe_int(row["position"]) if has_position else fallback_position,
        "team": team_display_name(year, row.get("constructorName")) or "Unknown",
        "points": safe_float(row.get("points", 0)),
        "wins": safe_int(row.get("wins", 0)),
    }


def build_zero_point_constructor_standings(ergast: Ergast, year: int) -> list[dict]:
    constructors = ergast.get_constructor_info(season=year)
    if constructors.empty:
        return []
    return [
        {
            "position": idx,
            "team": team_display_name(year, row["constructorName"]),
            "points": 0.0,
            "wins": 0,
        }
        for idx, (_, row) in enumerate(constructors.iterrows(), start=1)
    ]
