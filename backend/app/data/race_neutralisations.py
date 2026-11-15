"""The laps a race ran under a safety car, a virtual safety car or a red flag.

OpenF1's race-control messages give each period as a time window; a chart
needs lap numbers. Laps are numbered per car, so the windows are read against
one reference car: the one that ran the most laps (the lowest car number on a
tie), whose lap numbers are the race's.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import structlog

from app.data.openf1.client import OpenF1UnavailableError
from app.data.openf1.race_control import RED_FLAG
from app.data.openf1.session_laps import load_session_laps

if TYPE_CHECKING:
    from app.data.openf1.laps import Lap
    from app.data.openf1.race_control import Window

logger = structlog.get_logger()


def _reference_laps(laps: tuple[Lap, ...]) -> tuple[Lap, ...]:
    counts = Counter(lap.driver for lap in laps)
    if not counts:
        return ()
    reference = min(counts, key=lambda driver: (-counts[driver], driver))
    return tuple(lap for lap in laps if lap.driver == reference)


def _under(lap: Lap, window: Window) -> bool:
    if lap.start is None:
        return False
    return (lap.end or lap.start) > window.start and (window.end is None or lap.start < window.end)


def lap_ranges(laps: tuple[Lap, ...], windows: tuple[Window, ...]) -> list[dict]:
    """Each window as ``{kind, start_lap, end_lap}``; a window no lap ran under is left out."""
    reference = _reference_laps(laps)
    ranges = []
    for window in windows:
        numbers = [lap.number for lap in reference if _under(lap, window)]
        if numbers:
            ranges.append({"kind": window.kind, "start_lap": min(numbers), "end_lap": max(numbers)})
    return _yield_to_red(ranges)


def _yield_to_red(ranges: list[dict]) -> list[dict]:
    """A safety car window runs on until the track clears, past a red flag; it ends where the red flag starts."""
    reds = [row["start_lap"] for row in ranges if row["kind"] == RED_FLAG]
    clipped = []
    for row in ranges:
        stop = next((red - 1 for red in reds if row["start_lap"] < red <= row["end_lap"]), None)
        clipped.append(row if row["kind"] == RED_FLAG or stop is None else {**row, "end_lap": stop})
    return clipped


def race_neutralisations(year: int, round_num: int) -> list[dict] | None:
    """The race's neutralised periods by lap; None when OpenF1 cannot say, [] when there were none."""
    try:
        session = load_session_laps(year, round_num, "R")
    except OpenF1UnavailableError as exc:
        logger.warning("race_neutralisations.unavailable", year=year, round=round_num, error=str(exc))
        return None
    if session is None:
        return None
    return lap_ranges(session.laps, session.windows)
