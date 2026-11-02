"""Corner numbers and map rotation for a circuit, from MultiViewer.

MultiViewer's circuit API is what FastF1's ``get_circuit_info`` reads. It gives
each corner's position in the same x/y frame as OpenF1's ``/location`` feed,
and the rotation that turns that frame into the familiar map orientation.

The same answer carries the circuit's outline as ``x``/``y`` arrays, which is
what the Command Center draws its circuit map from: a layout costs one small
request instead of a lap of OpenF1 car positions.

It is unofficial and optional: the map draws without corner labels when it
fails, so every failure here ends in ``None``. Corner positions are a third
party's, not measured by this app, and are labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.config import OPENF1_HTTP_TIMEOUT_SECONDS
from app.data.analysis_cache import analysis_cache

logger = structlog.get_logger()

MULTIVIEWER_BASE = "https://api.multiviewer.app/api/v1/circuits"
CIRCUIT_KIND = "circuit"
CIRCUIT_VERSION = 1
LAYOUT_KIND = "circuit-layout"
LAYOUT_VERSION = 1
# Fewer points than this is not a circuit anyone would recognise.
MIN_OUTLINE_POINTS = 20


@dataclass(frozen=True)
class Corner:
    number: int
    letter: str
    x: float
    y: float
    # The direction, in degrees, a label is pushed off the track.
    angle: float


@dataclass(frozen=True)
class CircuitInfo:
    rotation: float
    corners: tuple[Corner, ...]

    def to_json(self) -> dict:
        return {"rotation": self.rotation, "corners": [corner.__dict__ for corner in self.corners]}

    @classmethod
    def from_json(cls, payload: dict) -> CircuitInfo:
        return cls(
            rotation=float(payload["rotation"]),
            corners=tuple(Corner(**row) for row in payload["corners"]),
        )


def _corner(row: object) -> Corner | None:
    if not isinstance(row, dict):
        return None
    position = row.get("trackPosition")
    if not isinstance(position, dict):
        return None
    try:
        return Corner(
            number=int(row["number"]),
            letter=str(row.get("letter") or ""),
            x=float(position["x"]),
            y=float(position["y"]),
            angle=float(row.get("angle") or 0.0),
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CircuitLayout:
    """The outline of a circuit in MultiViewer's frame, for the season it was drawn from."""

    season: int
    rotation: float
    x: tuple[float, ...]
    y: tuple[float, ...]
    corners: tuple[Corner, ...]

    def to_json(self) -> dict:
        return {
            "season": self.season,
            "rotation": self.rotation,
            "x": list(self.x),
            "y": list(self.y),
            "corners": [corner.__dict__ for corner in self.corners],
        }

    @classmethod
    def from_json(cls, payload: dict) -> CircuitLayout:
        return cls(
            season=int(payload["season"]),
            rotation=float(payload["rotation"]),
            x=tuple(payload["x"]),
            y=tuple(payload["y"]),
            corners=tuple(Corner(**row) for row in payload["corners"]),
        )


def _rotation(payload: dict) -> float:
    try:
        return float(payload.get("rotation") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def parse_circuit_info(payload: object) -> CircuitInfo | None:
    """MultiViewer's answer as corners and a rotation; None when it has no usable corners."""
    if not isinstance(payload, dict) or not isinstance(payload.get("corners"), list):
        return None
    corners = tuple(corner for row in payload["corners"] if (corner := _corner(row)) is not None)
    if not corners:
        return None
    return CircuitInfo(rotation=_rotation(payload), corners=tuple(sorted(corners, key=lambda c: (c.number, c.letter))))


def _coordinates(values: object) -> tuple[float, ...] | None:
    if not isinstance(values, list):
        return None
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        return None
    return tuple(float(value) for value in values)


def parse_circuit_layout(payload: object, season: int) -> CircuitLayout | None:
    """MultiViewer's outline, rotation and corners; None without a drawable outline."""
    if not isinstance(payload, dict):
        return None
    xs, ys = _coordinates(payload.get("x")), _coordinates(payload.get("y"))
    if xs is None or ys is None or len(xs) != len(ys) or len(xs) < MIN_OUTLINE_POINTS:
        return None
    info = parse_circuit_info(payload)
    return CircuitLayout(
        season=season,
        rotation=_rotation(payload),
        x=xs,
        y=ys,
        corners=info.corners if info else (),
    )


def new_client() -> httpx.Client:
    return httpx.Client(timeout=OPENF1_HTTP_TIMEOUT_SECONDS)


def _fetch_payload(circuit_key: int, year: int) -> object | None:
    try:
        with new_client() as client:
            response = client.get(f"{MULTIVIEWER_BASE}/{circuit_key}/{year}")
        if response.status_code != httpx.codes.OK:
            logger.warning(
                "multiviewer.circuit_unavailable", circuit=circuit_key, year=year, status=response.status_code
            )
            return None
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("multiviewer.circuit_failed", circuit=circuit_key, year=year, error=str(exc))
        return None


def _fetch(circuit_key: int, year: int) -> CircuitInfo | None:
    return parse_circuit_info(_fetch_payload(circuit_key, year))


def load_circuit_info(circuit_key: int | None, year: int) -> CircuitInfo | None:
    """The circuit's corners and rotation for the season; None when unknown."""
    if circuit_key is None:
        return None
    key = f"{circuit_key}:{year}"
    kept = analysis_cache.get(CIRCUIT_KIND, key, CIRCUIT_VERSION)
    if kept is not None:
        return CircuitInfo.from_json(kept)
    info = _fetch(circuit_key, year)
    if info is not None:
        analysis_cache.put(CIRCUIT_KIND, key, CIRCUIT_VERSION, info.to_json())
    return info


def _layout_for(circuit_key: int, season: int) -> CircuitLayout | None:
    key = f"{circuit_key}:{season}"
    kept = analysis_cache.get(LAYOUT_KIND, key, LAYOUT_VERSION)
    if kept is not None:
        return CircuitLayout.from_json(kept)
    layout = parse_circuit_layout(_fetch_payload(circuit_key, season), season)
    if layout is not None:
        analysis_cache.put(LAYOUT_KIND, key, LAYOUT_VERSION, layout.to_json())
    return layout


def load_circuit_layout(circuit_key: int | None, year: int) -> CircuitLayout | None:
    """The circuit's outline for ``year``, else the season before; None when neither is mapped.

    MultiViewer maps a season's circuits as they are raced, so a new season's
    round can be missing before its weekend. The previous season's outline is
    kept under that season, not this one, so the new outline replaces it as soon
    as MultiViewer publishes it.
    """
    if circuit_key is None:
        return None
    return _layout_for(circuit_key, year) or _layout_for(circuit_key, year - 1)
