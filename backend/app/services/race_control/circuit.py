"""The circuit segment of the command centre: the map to draw and the record behind it.

Three sources, each optional and each failing on its own:

* the outline and corner numbers, from MultiViewer — unofficial, and labelled
  as such on the page;
* the layout's facts and the circuit's history, from f1db;
* the lap record, from the app's own circuit table.

The outline is turned to MultiViewer's map orientation and scaled into a square
SVG viewbox here, so the page draws it without any geometry of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

from app.data.analysis_cache import analysis_cache
from app.data.multiviewer import CircuitInfo, CircuitLayout, load_circuit_layout
from app.data.openf1.client import OpenF1UnavailableError, new_client as openf1_client
from app.data.openf1.sessions import find_meeting
from app.data.profiles.circuit_record import circuit_record
from app.services.analysis.trace_points import rotate
from app.services.analysis.track_map import corner_markers

logger = structlog.get_logger()

# OpenF1's circuit key for a round never changes once the meeting is listed, and
# OpenF1 refuses every request while a session is live, so it is kept for good.
KEY_KIND = "circuit-key"
KEY_VERSION = 1
LAYOUT_SOURCE = "MultiViewer"
# The map is scaled so its longer side spans the viewbox, inside a margin that
# leaves room for the corner numbers pushed off the track.
VIEWBOX_SIZE = 1000.0
VIEWBOX_PADDING = 60.0


def resolve_circuit_key(year: int, round_num: int) -> int | None:
    """OpenF1's circuit key for the round, matched by location and date; None when unknown."""
    key = f"{year}:{round_num}"
    kept = analysis_cache.get(KEY_KIND, key, KEY_VERSION)
    if kept is not None:
        return kept["circuit_key"]
    try:
        with openf1_client() as client:
            meeting = find_meeting(client, year, round_num)
    except OpenF1UnavailableError as exc:
        logger.warning("race_control.circuit_key.unavailable", year=year, round=round_num, error=str(exc))
        return None
    circuit_key = (meeting or {}).get("circuit_key")
    if not isinstance(circuit_key, int):
        return None
    analysis_cache.put(KEY_KIND, key, KEY_VERSION, {"circuit_key": circuit_key})
    return circuit_key


@dataclass(frozen=True)
class _Frame:
    """Places a turned point in the viewbox, with y flipped for SVG."""

    min_x: float
    max_y: float
    scale: float

    def place(self, x: float, y: float) -> list[float]:
        return [
            round((x - self.min_x) * self.scale + VIEWBOX_PADDING, 1),
            round((self.max_y - y) * self.scale + VIEWBOX_PADDING, 1),
        ]


def drawable_map(layout: CircuitLayout) -> dict:
    """The outline and corners as SVG coordinates in a viewbox ``VIEWBOX_SIZE`` across."""
    xs, ys = rotate(np.asarray(layout.x), np.asarray(layout.y), layout.rotation)
    min_x, max_x = float(xs.min()), float(xs.max())
    min_y, max_y = float(ys.min()), float(ys.max())
    span = max(max_x - min_x, max_y - min_y) or 1.0
    frame = _Frame(min_x=min_x, max_y=max_y, scale=(VIEWBOX_SIZE - 2 * VIEWBOX_PADDING) / span)
    markers = corner_markers(CircuitInfo(rotation=layout.rotation, corners=layout.corners))
    return {
        "source": LAYOUT_SOURCE,
        "season": layout.season,
        "width": round((max_x - min_x) * frame.scale + 2 * VIEWBOX_PADDING, 1),
        "height": round((max_y - min_y) * frame.scale + 2 * VIEWBOX_PADDING, 1),
        "points": [frame.place(x, y) for x, y in zip(xs.tolist(), ys.tolist(), strict=True)],
        "corners": [
            {
                "label": marker["label"],
                **dict(zip(("x", "y"), frame.place(marker["x"], marker["y"]), strict=True)),
                **dict(zip(("label_x", "label_y"), frame.place(marker["label_x"], marker["label_y"]), strict=True)),
            }
            for marker in markers
        ],
    }


def _record(year: int, round_num: int) -> dict | None:
    try:
        return circuit_record(year, round_num)
    except Exception as exc:
        logger.warning("race_control.circuit_record.failed", year=year, round=round_num, error=str(exc))
        return None


def build_circuit_segment(year: int, race: dict | None) -> dict:
    """The selected round's circuit: f1db record, lap record and drawable map, each or None."""
    round_num = (race or {}).get("round")
    if not race or not round_num:
        return {"record": None, "lap_record": None, "map": None}
    layout = load_circuit_layout(resolve_circuit_key(year, round_num), year)
    return {
        "record": _record(year, round_num),
        "lap_record": (race.get("circuit") or {}).get("lap_record"),
        "map": drawable_map(layout) if layout else None,
    }
