"""Two drivers' laps side by side: where one gains time on the other.

Both laps are put on one distance axis first. Integrated distance differs
between two laps of the same track by tens of metres, so each is scaled to the
pair's mean length, then sampled every :data:`GRID_STEP_METRES`.

The delta is ``t_b(d) − t_a(d)``: how far B is behind A at each point, positive
when A is ahead. Each lap's clock ends exactly at its official time (see
:mod:`app.services.analysis.trace_points`), so the delta at the line is the
published gap, and the gains of any set of stretches that cover the lap add up
to it. A stretch's gain is the change in delta across it: positive means A
was quicker through it.

Measured: lap and sector times, and every sample's speed, throttle, brake and
gear. Modelled: the distance axis, the delta trace, mini-sector and corner
gains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from app.data.multiviewer import load_circuit_info
from app.services.analysis.common import SOURCE, driver_json, lap_json, session_json
from app.services.analysis.loading import require_lap, require_session
from app.services.analysis.trace_points import TracePoints, on_lap_clock, on_length, rotate, rounded
from app.services.analysis.track_map import DELETED_LAP_WARNING, corner_markers

if TYPE_CHECKING:
    from app.data.multiviewer import CircuitInfo
    from app.services.analysis.common import DriverLap, SessionRef
    from app.services.analysis.loading import LoadedLap

GRID_STEP_METRES = 10.0
MINI_SECTOR_COUNT = 25
TOP_GAIN_COUNT = 3
# Gains smaller than this (seconds) are a tie.
EVEN_SECONDS = 0.0005


def distance_grid(length: float) -> np.ndarray:
    return np.append(np.arange(0.0, length, GRID_STEP_METRES), length)


def _stepped(points: TracePoints, grid: np.ndarray, values: np.ndarray) -> np.ndarray:
    index = np.clip(np.searchsorted(points.distance, grid, side="right") - 1, 0, len(values) - 1)
    return values[index]


def resample(points: TracePoints, grid: np.ndarray) -> dict[str, np.ndarray]:
    """Every channel at the grid's distances."""
    return {
        "t": np.interp(grid, points.distance, points.t),
        "speed": np.interp(grid, points.distance, points.speed),
        "throttle": np.interp(grid, points.distance, points.throttle),
        "brake": _stepped(points, grid, points.brake),
        "gear": _stepped(points, grid, points.gear),
    }


def stretch_gains(grid: np.ndarray, delta: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """A's gain over B through each stretch between consecutive edges."""
    at_edges = np.interp(edges, grid, delta)
    return np.diff(at_edges)


def _faster(gain: float) -> str:
    if abs(gain) < EVEN_SECONDS:
        return "even"
    return "a" if gain > 0 else "b"


def _stretch(label: str, start: float, end: float, gain: float) -> dict:
    return {
        "label": label,
        "start": round(start, 1),
        "end": round(end, 1),
        "gain": round(gain, 3),
        "faster": _faster(gain),
    }


def mini_sectors(grid: np.ndarray, delta: np.ndarray, length: float) -> list[dict]:
    edges = np.linspace(0.0, length, MINI_SECTOR_COUNT + 1)
    gains = stretch_gains(grid, delta, edges)
    return [
        _stretch(f"Mini-sector {index + 1}", float(edges[index]), float(edges[index + 1]), float(gain))
        for index, gain in enumerate(gains)
    ]


def corner_distances(points: TracePoints, circuit: CircuitInfo) -> list[tuple[str, float]]:
    """Each corner's distance along the lap: where the lap passes closest to it."""
    found = []
    for corner in circuit.corners:
        nearest = int(np.argmin(np.hypot(points.x - corner.x, points.y - corner.y)))
        found.append((f"Turn {corner.number}{corner.letter}", float(points.distance[nearest])))
    return sorted(found, key=lambda item: item[1])


def corner_stretches(grid: np.ndarray, delta: np.ndarray, corners: list[tuple[str, float]]) -> list[dict]:
    """Gains corner by corner; each corner owns the track halfway to its neighbours."""
    if not corners:
        return []
    length = float(grid[-1])
    marks = np.array([distance for _, distance in corners])
    edges = np.concatenate(([0.0], (marks[:-1] + marks[1:]) / 2, [length]))
    gains = stretch_gains(grid, delta, edges)
    return [
        _stretch(label, float(edges[index]), float(edges[index + 1]), float(gains[index]))
        for index, (label, _) in enumerate(corners)
    ]


def biggest_gains(stretches: list[dict]) -> dict[str, list[dict]]:
    by_gain = sorted(stretches, key=lambda stretch: stretch["gain"])
    return {
        "a": [stretch for stretch in reversed(by_gain) if stretch["faster"] == "a"][:TOP_GAIN_COUNT],
        "b": [stretch for stretch in by_gain if stretch["faster"] == "b"][:TOP_GAIN_COUNT],
    }


def sector_gains(a: LoadedLap, b: LoadedLap) -> list[dict]:
    rows = []
    for index, (time_a, time_b) in enumerate(zip(a.choice.lap.sectors, b.choice.lap.sectors, strict=True)):
        gain = None if time_a is None or time_b is None else round(time_b - time_a, 3)
        rows.append({"sector": index + 1, "a": time_a, "b": time_b, "gain": gain})
    return rows


def _side(loaded: LoadedLap, year: int) -> dict:
    return {"driver": driver_json(loaded.driver, year), "lap": lap_json(loaded.choice.lap, loaded.choice.fastest)}


def _trace(grid: np.ndarray, a: dict[str, np.ndarray], b: dict[str, np.ndarray]) -> dict:
    trace: dict[str, list[float]] = {"distance": rounded(grid, 0), "delta": rounded(b["t"] - a["t"], 3)}
    for channel in ("speed", "throttle", "brake", "gear"):
        trace[f"{channel}_a"] = rounded(a[channel], 0)
        trace[f"{channel}_b"] = rounded(b[channel], 0)
    return trace


def _map(points: TracePoints, circuit: CircuitInfo | None) -> dict:
    x, y = rotate(points.x, points.y, circuit.rotation if circuit is not None else 0.0)
    return {"distance": rounded(points.distance), "x": rounded(x), "y": rounded(y)}


def build_comparison(ref: SessionRef, pick_a: DriverLap, pick_b: DriverLap) -> dict:
    session = require_session(ref)
    a, b = require_lap(session, pick_a), require_lap(session, pick_b)
    circuit = load_circuit_info(session.session.circuit_key, ref.year)
    (points_a, warnings_a), (points_b, warnings_b) = on_lap_clock(a.trace), on_lap_clock(b.trace)
    length = (points_a.length + points_b.length) / 2
    points_a, points_b = on_length(points_a, length), on_length(points_b, length)
    grid = distance_grid(length)
    on_grid_a, on_grid_b = resample(points_a, grid), resample(points_b, grid)
    delta = on_grid_b["t"] - on_grid_a["t"]
    corners = corner_stretches(grid, delta, corner_distances(points_a, circuit) if circuit is not None else [])
    sectors = mini_sectors(grid, delta, length)
    deleted = [f"{side.driver.code}: {DELETED_LAP_WARNING}" for side in (a, b) if side.choice.lap.deleted]
    return {
        "available": True,
        "pending": False,
        "source": SOURCE,
        "session": session_json(session),
        "a": _side(a, ref.year),
        "b": _side(b, ref.year),
        "gap": round(float(delta[-1]), 3),
        "trace": _trace(grid, on_grid_a, on_grid_b),
        "mini_sectors": sectors,
        "corners": corners,
        "sectors": sector_gains(a, b),
        "biggest_gains": biggest_gains(corners or sectors),
        "map": _map(points_a, circuit),
        "corner_markers": corner_markers(circuit),
        "modeled": ["distance", "delta", "mini_sectors", "corners"],
        "warnings": sorted(set(warnings_a + warnings_b)) + deleted,
    }
