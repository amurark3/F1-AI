"""Detecting notable events in the live timing stream."""

from __future__ import annotations

from dataclasses import dataclass, field

# Session statuses that count as an interruption worth commentating on.
INTERRUPTION_STATUSES = frozenset({"safety car", "vsc", "virtual safety car", "red flag"})


@dataclass(frozen=True)
class Snapshot:
    """One poll of the live feed — the three streams event detection compares.

    Detection is a function of two successive snapshots, so the three streams
    travel together rather than as six loose positional arguments a caller can
    transpose without anything noticing.
    """

    positions: list[dict] = field(default_factory=list)
    session_status: str = ""
    stints: dict[str, int] = field(default_factory=dict)


def _by_driver(positions: list[dict]) -> dict[str, dict]:
    """Index position rows by driver code, last row winning."""
    return {row["driver"]: row for row in positions}


def _safety_car_event(previous: Snapshot, current: Snapshot) -> dict | None:
    """A newly-deployed safety car, VSC or red flag."""
    status = current.session_status
    if status and status != previous.session_status and status.lower() in INTERRUPTION_STATUSES:
        return {"type": "safety_car", "status": status}
    return None


def _position_change_event(previous: Snapshot, current: Snapshot) -> dict | None:
    """The first driver found to have changed position between snapshots."""
    previous_rows = _by_driver(previous.positions)
    for driver, row in _by_driver(current.positions).items():
        prior = previous_rows.get(driver)
        if prior and row["position"] != prior["position"]:
            return {
                "type": "position_change",
                "driver": driver,
                "from_pos": prior["position"],
                "to_pos": row["position"],
                "positions": current.positions[:5],
            }
    return None


def _pit_stop_event(previous: Snapshot, current: Snapshot) -> dict | None:
    """The first driver whose stint count rose, which means they pitted."""
    current_rows = _by_driver(current.positions)
    for driver, stint in current.stints.items():
        if stint > previous.stints.get(driver, 1):
            return {
                "type": "pit_stop",
                "driver": driver,
                "pit_count": stint - 1,  # stints = pit_stops + 1
                "position": current_rows.get(driver, {}).get("position", "?"),
            }
    return None


# Highest priority first — the first detector to fire owns the cooldown window.
_DETECTORS = (_safety_car_event, _position_change_event, _pit_stop_event)


def _detect_event(previous: Snapshot, current: Snapshot) -> dict | None:
    """Compare successive snapshots and return the highest-priority event, or None."""
    for detector in _DETECTORS:
        event = detector(previous, current)
        if event:
            return event
    return None
