"""What OpenF1's circuit weather station measured during a session.

OpenF1's ``weather`` endpoint is the trackside station, read about once a
minute: air and track temperature in degrees C. ``rainfall`` is a flag (0 or 1)
for that reading, never an amount, so it is kept as one flag per reading.
"""

from __future__ import annotations

from statistics import fmean
from typing import TYPE_CHECKING

from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from datetime import datetime


def _numbers(readings: list[dict], field: str) -> list[float]:
    return [
        float(value)
        for row in readings
        if isinstance(value := row.get(field), int | float) and not isinstance(value, bool)
    ]


def _in_window(rows: list[dict], start: datetime | None, end: datetime | None) -> list[dict]:
    """The rows whose date parses and lies in the session, in time order; any row when a bound is unknown."""
    stamped = sorted(
        ((moment, row) for row in rows if (moment := parse_iso(row.get("date"))) is not None),
        key=lambda pair: pair[0],
    )
    if start is None or end is None:
        return [row for _, row in stamped]
    return [row for moment, row in stamped if start <= moment <= end]


def summarise_track_weather(rows: list[dict], start: datetime | None, end: datetime | None) -> dict | None:
    """Mean and range of track temperature, mean air temperature and one rain flag per reading; None when empty."""
    readings = _in_window(rows, start, end)
    track = _numbers(readings, "track_temperature")
    air = _numbers(readings, "air_temperature")
    rain = _numbers(readings, "rainfall")
    if not (track or air or rain):
        return None
    return {
        "track_temp_c": round(fmean(track), 1) if track else None,
        "track_temp_min_c": round(min(track), 1) if track else None,
        "track_temp_max_c": round(max(track), 1) if track else None,
        "air_temp_c": round(fmean(air), 1) if air else None,
        "rainfall": [value > 0 for value in rain],
    }
