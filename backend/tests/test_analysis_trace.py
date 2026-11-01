"""Tests for the lap-trace maths: lap clock, distance, rotation, braking and high-speed zones.

* A lap's clock is cut to exactly 0 → lap time, so a constant 360 km/h for
  10 s is exactly 1,000 m.
* Brake is on/off at ~4 Hz: one "on" sample with no real slowing is not a zone,
  and one "off" sample inside a zone does not split it.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.data.openf1.telemetry import LapTrace
from app.services.analysis.trace_points import (
    TracePoints,
    integrate_distance,
    on_lap_clock,
    on_length,
    rotate,
    rotated,
    rounded,
)
from app.services.analysis.zones import braking_zones, fill_single_gaps, high_speed_zones, lap_stats, runs

pytestmark = pytest.mark.unit


def _trace(t: list[float], speed: list[float], lap_time: float = 10.0, **channels) -> LapTrace:
    n = len(t)
    return LapTrace(
        driver=1,
        lap=8,
        lap_time=lap_time,
        t=tuple(t),
        speed=tuple(speed),
        throttle=tuple(channels.get("throttle", [100.0] * n)),
        brake=tuple(channels.get("brake", [0.0] * n)),
        gear=tuple(channels.get("gear", [8.0] * n)),
        rpm=tuple([11000.0] * n),
        x=tuple(channels.get("x", list(np.linspace(0, 1000, n)))),
        y=tuple(channels.get("y", [0.0] * n)),
    )


def _points(speed: list[float], brake: list[float] | None = None, throttle: list[float] | None = None) -> TracePoints:
    n = len(speed)
    t = np.arange(n, dtype=float)
    speeds = np.asarray(speed, dtype=float)
    return TracePoints(
        t=t,
        distance=integrate_distance(t, speeds),
        speed=speeds,
        throttle=np.asarray(throttle or [100.0] * n, dtype=float),
        brake=np.asarray(brake or [0.0] * n, dtype=float),
        gear=np.full(n, 8.0),
        x=t * 10,
        y=t * 0,
    )


# ---------------------------------------------------------------------------
# Lap clock and distance
# ---------------------------------------------------------------------------


def test_the_lap_runs_exactly_from_zero_to_its_time_and_distance_follows_speed():
    t = [-1.0 + 0.25 * step for step in range(49)]
    points, warnings = on_lap_clock(_trace(t, [360.0] * len(t)))

    assert points.t[0] == 0.0
    assert points.t[-1] == 10.0
    assert points.length == pytest.approx(1000.0)
    assert warnings == []


def test_stepped_channels_hold_the_last_sample_rather_than_blend():
    t = [-1.0, 4.0, 11.0]
    points, _ = on_lap_clock(_trace(t, [300.0] * 3, gear=[6.0, 7.0, 8.0], brake=[0.0, 100.0, 0.0]))

    assert list(points.t) == [0.0, 4.0, 10.0]
    assert list(points.gear) == [6.0, 7.0, 7.0]
    assert list(points.brake) == [0.0, 100.0, 100.0]


@pytest.mark.parametrize(("t", "label"), [([1.0, 5.0, 11.0], "late start"), ([-1.0, 5.0, 9.0], "early end")])
def test_samples_that_stop_short_of_the_lap_are_warned_about(t, label):
    _, warnings = on_lap_clock(_trace(t, [300.0] * 3))

    assert len(warnings) == 1, label


def test_rotation_turns_counter_clockwise():
    x, y = rotate(np.array([1.0]), np.array([0.0]), 90)

    assert (round(float(x[0]), 6), round(float(y[0]), 6)) == (0.0, 1.0)
    turned = rotated(_points([100.0, 100.0]), 180)
    assert rounded(turned.x) == [0.0, -10.0]


def test_a_lap_is_scaled_onto_a_common_length():
    points = _points([360.0] * 11)

    assert on_length(points, 2000.0).length == pytest.approx(2000.0)
    still = _points([0.0, 0.0])
    assert on_length(still, 2000.0) is still


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


def test_runs_are_found_inclusive():
    assert runs(np.array([False, True, True, False, True])) == [(1, 2), (4, 4)]
    assert runs(np.array([], dtype=bool)) == []


def test_a_single_dropout_inside_a_run_is_filled():
    assert list(fill_single_gaps(np.array([True, False, True, False, False, True]))) == [
        True,
        True,
        True,
        False,
        False,
        True,
    ]
    assert list(fill_single_gaps(np.array([True, False]))) == [True, False]


def test_braking_zones_skip_a_dab_but_keep_a_short_hard_stop():
    speed = [300, 300, 300, 299, 300, 300, 290, 200, 120, 125, 300, 300, 250, 200]
    brake = [0, 0, 0, 100, 0, 0, 100, 100, 100, 0, 0, 0, 100, 0]

    zones = braking_zones(_points(speed, brake=brake))

    assert [(zone["entry_speed"], zone["min_speed"]) for zone in zones] == [(290, 120), (250, 200)]
    assert zones[0]["x"] == 60.0


def test_a_braking_run_at_the_end_of_the_lap_still_counts():
    zones = braking_zones(_points([300, 300, 250, 150], brake=[0, 0, 100, 100]))

    assert [(zone["entry_speed"], zone["min_speed"]) for zone in zones] == [(250, 150)]


def test_high_speed_stretches_are_set_by_speed_and_must_be_long_enough():
    speed = [200, 330, 335, 340, 200, 200, 335, 200]

    zones = high_speed_zones(_points(speed))

    assert [(zone["peak_speed"], zone["x"]) for zone in zones] == [(340, 30.0)]


def test_lap_stats_share_time_spent_flat_out_and_braking():
    stats = lap_stats(_points([300, 320, 310, 200, 250], brake=[0, 0, 100, 0, 0], throttle=[100, 100, 0, 50, 100]))

    assert stats["top_speed"]["speed"] == 320
    assert stats["full_throttle_pct"] == 50.0
    assert stats["braking_pct"] == 25.0


def test_a_lap_with_no_elapsed_time_has_no_shares():
    still = TracePoints(*(np.zeros(2) for _ in range(8)))

    assert lap_stats(still)["full_throttle_pct"] == 0.0
