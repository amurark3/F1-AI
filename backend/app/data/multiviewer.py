"""Corner numbers and map rotation for a circuit, from MultiViewer.

MultiViewer's circuit API is what FastF1's ``get_circuit_info`` reads. It gives
each corner's position in the same x/y frame as OpenF1's ``/location`` feed,
and the rotation that turns that frame into the familiar map orientation.

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


def parse_circuit_info(payload: object) -> CircuitInfo | None:
    """MultiViewer's answer as corners and a rotation; None when it has no usable corners."""
    if not isinstance(payload, dict) or not isinstance(payload.get("corners"), list):
        return None
    corners = tuple(corner for row in payload["corners"] if (corner := _corner(row)) is not None)
    if not corners:
        return None
    try:
        rotation = float(payload.get("rotation") or 0.0)
    except (TypeError, ValueError):
        rotation = 0.0
    return CircuitInfo(rotation=rotation, corners=tuple(sorted(corners, key=lambda c: (c.number, c.letter))))


def new_client() -> httpx.Client:
    return httpx.Client(timeout=OPENF1_HTTP_TIMEOUT_SECONDS)


def _fetch(circuit_key: int, year: int) -> CircuitInfo | None:
    try:
        with new_client() as client:
            response = client.get(f"{MULTIVIEWER_BASE}/{circuit_key}/{year}")
        if response.status_code != httpx.codes.OK:
            logger.warning(
                "multiviewer.circuit_unavailable", circuit=circuit_key, year=year, status=response.status_code
            )
            return None
        return parse_circuit_info(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("multiviewer.circuit_failed", circuit=circuit_key, year=year, error=str(exc))
        return None


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
