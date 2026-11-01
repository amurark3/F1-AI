"""A lap's samples put on the lap's own clock, with distance along the lap.

The kept trace runs from before the line to past it (see
:mod:`app.data.openf1.telemetry`). Here every channel is interpolated to exactly
``t = 0`` and ``t = lap time`` and the samples outside are dropped, so a lap's
trace ends when its official time says it does. That is what makes the
head-to-head delta at the line equal the published gap.

**Distance is modelled.** OpenF1 publishes no distance channel, so it is
integrated from speed (trapezoids between ~0.24 s samples). It comes out within
a percent or two of the circuit length, which is why two laps are put on a
common length before they are compared.

Rotation turns OpenF1's x/y frame into the usual map orientation, using the
angle MultiViewer publishes for the circuit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.data.openf1.telemetry import LapTrace

# Samples that stop more than this short of either end of the lap leave that end
# held at the last known value, which is worth saying.
EDGE_GAP_WARNING_SECONDS = 0.5
KMH_PER_METRE_PER_SECOND = 3.6


@dataclass(frozen=True)
class TracePoints:
    t: np.ndarray
    distance: np.ndarray
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    gear: np.ndarray
    x: np.ndarray
    y: np.ndarray

    @property
    def length(self) -> float:
        return float(self.distance[-1])


def _held(t: np.ndarray, grid: np.ndarray, values: tuple[float, ...]) -> np.ndarray:
    """A stepped channel (gear, brake) at each grid time: the last sample at or before it."""
    index = np.clip(np.searchsorted(t, grid, side="right") - 1, 0, len(t) - 1)
    return np.asarray(values, dtype=float)[index]


def integrate_distance(t: np.ndarray, speed_kmh: np.ndarray) -> np.ndarray:
    """Metres covered by each sample, from speed in km/h."""
    metres_per_second = speed_kmh / KMH_PER_METRE_PER_SECOND
    steps = np.diff(t) * (metres_per_second[1:] + metres_per_second[:-1]) / 2
    return np.concatenate(([0.0], np.cumsum(steps)))


def on_lap_clock(trace: LapTrace) -> tuple[TracePoints, list[str]]:
    """The lap from its start to its official time, and any warning about the samples' reach."""
    t = np.asarray(trace.t, dtype=float)
    lap_time = trace.lap_time
    grid = np.concatenate(([0.0], t[(t > 0) & (t < lap_time)], [lap_time]))

    def smooth(values: tuple[float, ...]) -> np.ndarray:
        return np.interp(grid, t, np.asarray(values, dtype=float))

    speed = smooth(trace.speed)
    warnings = []
    if t[0] > EDGE_GAP_WARNING_SECONDS or t[-1] < lap_time - EDGE_GAP_WARNING_SECONDS:
        warnings.append("OpenF1's samples stop short of the start or end of this lap; that stretch is held flat.")
    points = TracePoints(
        t=grid,
        distance=integrate_distance(grid, speed),
        speed=speed,
        throttle=smooth(trace.throttle),
        brake=_held(t, grid, trace.brake),
        gear=_held(t, grid, trace.gear),
        x=smooth(trace.x),
        y=smooth(trace.y),
    )
    return points, warnings


def rotate(x: np.ndarray, y: np.ndarray, degrees: float) -> tuple[np.ndarray, np.ndarray]:
    """Turn points counter-clockwise about the origin."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return x * cos - y * sin, x * sin + y * cos


def rotated(points: TracePoints, degrees: float) -> TracePoints:
    x, y = rotate(points.x, points.y, degrees)
    return replace(points, x=x, y=y)


def on_length(points: TracePoints, length: float) -> TracePoints:
    """The same lap with its distance scaled to end at ``length``."""
    if points.length <= 0:
        return points
    return replace(points, distance=points.distance * (length / points.length))


def rounded(values: np.ndarray, decimals: int = 1) -> list[float]:
    return [float(value) for value in np.round(values, decimals)]
