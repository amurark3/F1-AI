"""The speed map: one lap drawn round the circuit, coloured by speed.

Measured: the lap and sector times, the speed traps, and every sample's speed,
throttle, brake, gear and position. Modelled, and listed under ``modeled``: the
distance along the lap, the braking and high-speed zones built from those
samples, and the corners (MultiViewer's positions and label directions, not
this app's; the page places each number clear of the track).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from app.data.multiviewer import load_circuit_info
from app.services.analysis.common import SOURCE, DriverLap, SessionRef, driver_json, lap_json, session_json
from app.services.analysis.loading import require_lap, require_session
from app.services.analysis.trace_points import on_lap_clock, rotate, rotated, rounded
from app.services.analysis.zones import braking_zones, high_speed_zones, lap_stats

if TYPE_CHECKING:
    from app.data.multiviewer import CircuitInfo

DELETED_LAP_WARNING = "Race control deleted this lap's time; it does not count."
FULL_TURN = 360.0


def corner_markers(circuit: CircuitInfo | None) -> list[dict]:
    """Each corner's apex and MultiViewer's label direction, turned with the map.

    ``angle`` is in degrees from +x toward +y, in the same frame as ``x``/``y``.
    It is where MultiViewer pushes the number; the page tries it first and moves
    the number until it clears the rest of the track (``app/ui/cornerLabels.ts``).
    """
    if circuit is None:
        return []
    markers = []
    for corner in circuit.corners:
        xs, ys = rotate(np.array([corner.x]), np.array([corner.y]), circuit.rotation)
        markers.append(
            {
                "number": corner.number,
                "label": f"{corner.number}{corner.letter}",
                "x": round(float(xs[0]), 1),
                "y": round(float(ys[0]), 1),
                "angle": round((corner.angle + circuit.rotation) % FULL_TURN, 1),
            }
        )
    return markers


def build_track_map(ref: SessionRef, pick: DriverLap) -> dict:
    session = require_session(ref)
    loaded = require_lap(session, pick)
    circuit = load_circuit_info(session.session.circuit_key, ref.year)
    points, warnings = on_lap_clock(loaded.trace)
    points = rotated(points, circuit.rotation if circuit is not None else 0.0)
    if loaded.choice.lap.deleted:
        warnings.append(DELETED_LAP_WARNING)
    return {
        "available": True,
        "pending": False,
        "source": SOURCE,
        "session": session_json(session),
        "driver": driver_json(loaded.driver, ref.year),
        "lap": lap_json(loaded.choice.lap, loaded.choice.fastest),
        "points": {
            "distance": rounded(points.distance),
            "x": rounded(points.x),
            "y": rounded(points.y),
            "speed": rounded(points.speed, 0),
            "throttle": rounded(points.throttle, 0),
            "brake": rounded(points.brake, 0),
            "gear": rounded(points.gear, 0),
        },
        "braking_zones": braking_zones(points),
        "high_speed_zones": high_speed_zones(points),
        "stats": lap_stats(points),
        "corners": corner_markers(circuit),
        "modeled": ["distance", "braking_zones", "high_speed_zones", "corners"],
        "warnings": warnings,
    }
