"""One lap's car telemetry and position, merged onto one clock.

OpenF1 publishes car data (speed, throttle, brake, gear, rpm) and position
(x, y) as two separate feeds, each sampled about every 0.24 s and not at the
same instants. Position is interpolated onto the car-data timestamps, so each
sample carries every channel. Times are seconds from the lap's start.

Both feeds are fetched for a window padded by :data:`PADDING_SECONDS` either
side of the lap. Without it the first sample lands ~0.2 s after the line and the
last ~0.8 s before it, and a lap rebuilt from them comes up about 120 m short.

All channels are measured. ``brake`` is on/off (0 or 100), not a pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import timedelta
from typing import TYPE_CHECKING

import numpy as np
import structlog

from app.data.analysis_cache import analysis_cache
from app.data.openf1.client import get_json, new_client
from app.data.openf1.sessions import session_ended
from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from datetime import datetime

    from app.data.openf1.laps import Lap
    from app.data.openf1.session_laps import SessionLaps

logger = structlog.get_logger()

LAP_TRACE_KIND = "lap_trace"
LAP_TRACE_VERSION = 1
PADDING_SECONDS = 2.0
# Rounding of kept samples: milliseconds for time, decimetres for position.
TIME_DECIMALS = 3

_CAR_CHANNELS = ("speed", "throttle", "brake", "n_gear", "rpm")


@dataclass(frozen=True)
class LapTrace:
    """Samples of one lap; ``t`` runs from before 0 to past the lap time (the padding)."""

    driver: int
    lap: int
    lap_time: float
    t: tuple[float, ...]
    speed: tuple[float, ...]
    throttle: tuple[float, ...]
    brake: tuple[float, ...]
    gear: tuple[float, ...]
    rpm: tuple[float, ...]
    x: tuple[float, ...]
    y: tuple[float, ...]

    def to_json(self) -> dict:
        return {
            field.name: list(value) if isinstance(value := getattr(self, field.name), tuple) else value
            for field in fields(self)
        }

    @classmethod
    def from_json(cls, payload: dict) -> LapTrace:
        return cls(**{key: tuple(value) if isinstance(value, list) else value for key, value in payload.items()})


def _seconds(moment: datetime, start: datetime) -> float:
    return (moment - start).total_seconds()


def _car_samples(rows: list[dict], start: datetime) -> list[tuple[float, ...]]:
    samples: list[tuple[float, ...]] = []
    for row in rows:
        moment = parse_iso(row.get("date"))
        values = [row.get(channel) for channel in _CAR_CHANNELS]
        if moment is None or any(not isinstance(value, int | float) for value in values):
            continue
        samples.append((_seconds(moment, start), *(float(value) for value in values)))
    return sorted(samples)


def _positions(rows: list[dict], start: datetime) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for row in rows:
        moment, x, y = parse_iso(row.get("date")), row.get("x"), row.get("y")
        if moment is None or not isinstance(x, int | float) or not isinstance(y, int | float):
            continue
        points.append((_seconds(moment, start), float(x), float(y)))
    return sorted(points)


def merge_samples(lap: Lap, car_rows: list[dict], location_rows: list[dict]) -> LapTrace | None:
    """Car data with position interpolated onto it; None without a timed lap or two of each sample."""
    if lap.start is None or lap.time is None:
        return None
    car = _car_samples(car_rows, lap.start)
    where = _positions(location_rows, lap.start)
    if len(car) < 2 or len(where) < 2:
        return None
    t, speed, throttle, brake, gear, rpm = (np.array(column) for column in zip(*car, strict=True))
    t_where, x_where, y_where = (np.array(column) for column in zip(*where, strict=True))

    def kept(values: np.ndarray, decimals: int = 1) -> tuple[float, ...]:
        return tuple(float(value) for value in np.round(values, decimals))

    return LapTrace(
        driver=lap.driver,
        lap=lap.number,
        lap_time=lap.time,
        t=kept(t, TIME_DECIMALS),
        speed=kept(speed),
        throttle=kept(throttle),
        brake=kept(brake),
        gear=kept(gear, 0),
        rpm=kept(rpm, 0),
        x=kept(np.interp(t, t_where, x_where)),
        y=kept(np.interp(t, t_where, y_where)),
    )


def _fetch(session_key: int, lap: Lap) -> LapTrace | None:
    if lap.start is None or lap.time is None:
        return None
    padding = timedelta(seconds=PADDING_SECONDS)
    query = {
        "session_key": session_key,
        "driver_number": lap.driver,
        "date>": (lap.start - padding).isoformat(),
        "date<": (lap.start + timedelta(seconds=lap.time) + padding).isoformat(),
    }
    with new_client() as client:
        car_rows = get_json(client, "car_data", query)
        location_rows = get_json(client, "location", query)
    return merge_samples(lap, car_rows, location_rows)


def load_lap_trace(session: SessionLaps, lap: Lap) -> LapTrace | None:
    """The lap's merged samples; None when OpenF1 holds too few of them."""
    key = f"{session.session.session_key}:{lap.driver}:{lap.number}"
    kept = analysis_cache.get(LAP_TRACE_KIND, key, LAP_TRACE_VERSION)
    if kept is not None:
        return LapTrace.from_json(kept)
    trace = _fetch(session.session.session_key, lap)
    if trace is not None and session_ended(session.session):
        analysis_cache.put(LAP_TRACE_KIND, key, LAP_TRACE_VERSION, trace.to_json())
    logger.info("openf1.lap_trace.loaded", key=key, samples=0 if trace is None else len(trace.t))
    return trace
