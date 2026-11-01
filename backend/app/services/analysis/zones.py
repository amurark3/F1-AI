"""Braking zones, high-speed stretches and headline figures of one lap.

Brake is published as on/off at about 4 Hz, so a zone's start is only known to
within one sample, roughly 20 m at 300 km/h: the zones are **modelled** from
measured samples. A single "on" sample with no real slowing is a dab or noise,
not a braking zone, and a single "off" sample inside a zone is a dropout, not
two zones.

High-speed stretches are defined from speed, not throttle. In 2026 cars lift
and coast and run out of deployment on the straights, so full throttle no
longer marks where a car is quickest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.services.analysis.trace_points import TracePoints

BRAKE_ON = 50.0
MIN_BRAKE_SAMPLES = 2
MIN_BRAKE_DROP_KMH = 15.0
# A stretch counts as high speed at this share of the lap's top speed or more.
HIGH_SPEED_SHARE = 0.92
MIN_HIGH_SPEED_METRES = 100.0
FULL_THROTTLE = 98.0


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (first, last) index of every run of True."""
    padded = np.concatenate(([False], mask.astype(bool), [False]))
    edges = np.flatnonzero(np.diff(padded.astype(int)))
    return [(int(start), int(stop) - 1) for start, stop in zip(edges[::2], edges[1::2], strict=True)]


def fill_single_gaps(mask: np.ndarray) -> np.ndarray:
    """One False between two Trues becomes True."""
    filled = mask.astype(bool).copy()
    if len(filled) >= 3:
        filled[1:-1] |= filled[:-2] & filled[2:]
    return filled


def braking_zones(points: TracePoints) -> list[dict]:
    zones: list[dict] = []
    last = len(points.speed) - 1
    for start, end in runs(fill_single_gaps(points.brake >= BRAKE_ON)):
        # The car keeps slowing for a moment after the brake is released.
        stop = min(end + 1, last)
        slowest = start + int(np.argmin(points.speed[start : stop + 1]))
        drop = float(points.speed[start] - points.speed[slowest])
        if end - start + 1 < MIN_BRAKE_SAMPLES and drop < MIN_BRAKE_DROP_KMH:
            continue
        zones.append(
            {
                "start": round(float(points.distance[start]), 1),
                "end": round(float(points.distance[end]), 1),
                "entry_speed": round(float(points.speed[start])),
                "min_speed": round(float(points.speed[slowest])),
                "x": round(float(points.x[start]), 1),
                "y": round(float(points.y[start]), 1),
            }
        )
    return zones


def high_speed_zones(points: TracePoints) -> list[dict]:
    top = float(points.speed.max())
    zones: list[dict] = []
    for start, end in runs(points.speed >= HIGH_SPEED_SHARE * top):
        if points.distance[end] - points.distance[start] < MIN_HIGH_SPEED_METRES:
            continue
        peak = start + int(np.argmax(points.speed[start : end + 1]))
        zones.append(
            {
                "start": round(float(points.distance[start]), 1),
                "end": round(float(points.distance[end]), 1),
                "peak_speed": round(float(points.speed[peak])),
                "x": round(float(points.x[peak]), 1),
                "y": round(float(points.y[peak]), 1),
            }
        )
    return zones


def _time_share(points: TracePoints, mask: np.ndarray) -> float:
    """Share of the lap's time spent where ``mask`` holds, as a percentage."""
    steps = np.diff(points.t)
    total = float(steps.sum())
    if total <= 0:
        return 0.0
    return round(100 * float(steps[mask[:-1]].sum()) / total, 1)


def lap_stats(points: TracePoints) -> dict:
    top = int(np.argmax(points.speed))
    return {
        "top_speed": {
            "speed": round(float(points.speed[top])),
            "distance": round(float(points.distance[top]), 1),
            "x": round(float(points.x[top]), 1),
            "y": round(float(points.y[top]), 1),
        },
        "full_throttle_pct": _time_share(points, points.throttle >= FULL_THROTTLE),
        "braking_pct": _time_share(points, points.brake >= BRAKE_ON),
        "distance_m": round(points.length),
    }
