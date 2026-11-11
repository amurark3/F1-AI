"""The prediction's ``weather_impact``: the race-day forecast, graded as the risk register grades it.

Until 11 Nov 2026 every prediction said ``"dry"``, a placeholder. That included
R20 São Paulo, which ran under an 88–92 % forecast for the race window. The call
now reads the Race session's Open-Meteo forecast through the weekend payload the
Command Center shows (``build_session_weather`` → ``race_day_block``) and grades
its peak race-window rain probability with the risk register's own cut-offs:

    wet      at or above ``RAIN_RISK_HIGH``
    mixed    at or above ``RAIN_RISK_MODERATE``
    dry      below it, only with a real Open-Meteo race-window reading
    unknown  no reading the call could have had

No OpenWeatherMap figure can reach it: ``race_day_block`` reads Open-Meteo's
series and nothing else, so a feed outage is ``unknown``, never ``dry``.

It is a label on the call, not a model input: no predicted position reads it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog

from app.services.race_control.risk import RAIN_RISK_HIGH, RAIN_RISK_MODERATE
from app.services.race_control.session_weather import (
    RACE_SESSION,
    build_session_weather,
    race_day_block,
    session_slots,
)
from app.services.race_control.weather import race_day_reason
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()

WEATHER_WET = "wet"
WEATHER_MIXED = "mixed"
WEATHER_DRY = "dry"
WEATHER_UNKNOWN = "unknown"

# FastF1's schedule row names its sessions in slots Session1..Session5.
SCHEDULE_SLOTS = range(1, 6)

REASON_NO_RACE = "the schedule has no race session"
REASON_STARTED = "computed after the race started; its forecast is no longer a forecast"
REASON_FETCHED_LATE = "the stored forecast was fetched after the race started"


def race_weekend(event_row: Any) -> dict | None:
    """The weekend as ``build_session_weather`` reads it: venue and every session's start.

    Built from the FastF1 schedule row the way ``season_events`` builds the
    Command Center's race, so both ask Open-Meteo for the same window and share
    its cached answer.
    """
    if event_row is None:
        return None
    slots = ((event_row.get(f"Session{index}"), event_row.get(f"Session{index}DateUtc")) for index in SCHEDULE_SLOTS)
    return {
        "location": f"{event_row.get('Location')}, {event_row.get('Country')}",
        "sessions": {
            name: utc_isoformat(start) for name, start in slots if isinstance(name, str) and not pd.isna(start)
        },
    }


def rain_impact(rain_pct: float) -> str:
    """The call for a race-window peak rain probability, on the risk register's cut-offs."""
    if rain_pct >= RAIN_RISK_HIGH:
        return WEATHER_WET
    if rain_pct >= RAIN_RISK_MODERATE:
        return WEATHER_MIXED
    return WEATHER_DRY


def _unknown(reason: str) -> str:
    logger.info("predictions.weather_impact", impact=WEATHER_UNKNOWN, reason=reason)
    return WEATHER_UNKNOWN


def weather_impact(session_weather: dict, race_start: datetime) -> str:
    """Grade the race-day forecast in a weekend payload; ``unknown`` without one the call had.

    The payload's ``as_of`` is set only when the live call failed and the
    venue's stored series stands in. A stored series stamped at or after lights
    out holds hours that had already run, so the call cannot show it had that
    forecast first and it is not graded.
    """
    block = race_day_block(session_weather)
    if block is None:
        return _unknown(race_day_reason(session_weather))
    as_of = session_weather.get("as_of")
    if as_of and datetime.fromisoformat(as_of) >= race_start:
        return _unknown(REASON_FETCHED_LATE)
    impact = rain_impact(block["rain_risk"])
    logger.info("predictions.weather_impact", impact=impact, rain_pct=block["rain_risk"], source=block["confidence"])
    return impact


def race_weather_impact(event_row: Any, now: datetime | None = None) -> str:
    """The race-day weather call for a prediction computed at ``now`` (default: this moment).

    Point in time: a call may use only a forecast it could have had when it was
    computed. Once the race has started, Open-Meteo's hours for the race window
    are its model record of what happened (the payload's "Race-day model
    reading"), and the venue's stored copy keeps only the latest fetch, so the
    forecast a pre-race call saw is gone. A call computed at or after lights
    out (a backfill, a recompute of a past race) is therefore ``unknown``, and
    Open-Meteo is not asked. Before the start, whatever series is served was
    fetched no later than ``now``: live now, or the stored copy with its
    ``as_of`` (checked against the start in ``weather_impact``).

    The forecast comes through ``fetch_hourly``'s cache and failure cooldown,
    the path every weather view takes; a race beyond the forecast horizon or at
    an unknown venue makes no call at all.
    """
    moment = now or datetime.now(UTC)
    weekend = race_weekend(event_row)
    race = next((slot for slot in session_slots(weekend) if slot.name == RACE_SESSION), None)
    if race is None:
        return _unknown(REASON_NO_RACE)
    if moment >= race.start:
        return _unknown(REASON_STARTED)
    return weather_impact(build_session_weather(weekend, moment), race.start)
