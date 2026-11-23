"""Which OpenF1 pit rows are real tyre stops, shared by the Debrief radio and Race Rewind.

A row is a stop when its pit-lane time is under STOP_LANE_FACTOR x the race's
median lane time. Red-flag pit-lane entries and restart pit-lane waits sit far
above it. OpenF1 omits ``stop_duration`` for some stops that are on the
official pit sheet, so it is not required.
"""

from statistics import median

STOP_LANE_FACTOR = 1.5


def lane_seconds(row: dict) -> float | None:
    """OpenF1's pit-lane time for one pass; ``pit_duration`` is the same figure under its older name."""
    value = row.get("lane_duration")
    return row.get("pit_duration") if value is None else value


def stop_lane_limit(pit: list[dict]) -> float | None:
    """1.5 x the race's median pit-lane time; None when no row has a lane time."""
    lanes = [lane for row in pit if (lane := lane_seconds(row)) is not None]
    return STOP_LANE_FACTOR * median(lanes) if lanes else None


def is_stop(row: dict, limit: float | None) -> bool:
    """A tyre stop: on a lap, with a lane time under the limit."""
    lane = lane_seconds(row)
    return limit is not None and lane is not None and lane < limit and row.get("lap_number") is not None
