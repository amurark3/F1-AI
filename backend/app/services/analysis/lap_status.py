"""Why each race lap does, or does not, say something about tyre wear.

Each lap gets exactly one status, the first that applies in this order:

``lap1`` the standing start. ``no_time`` OpenF1 has no time for it. ``pit_out``
and ``pit_in`` the laps through the pit lane. ``red``, ``sc``, ``vsc`` the lap
ran under a red flag, safety car or virtual safety car, placed by *time*
against the car's own lap start (a lapped car is on another lap number than the
leader the message names). ``restart`` the first lap after a safety car or red
flag. ``wet`` rain was reported during it. ``unknown_age`` the set's age is not
published. ``traffic`` the car ran within :data:`TRAFFIC_GAP_SECONDS` of the
one ahead (a heuristic: dirty air, not the tyre, set the pace). ``outlier``
slower than 107% of the driver's median green-flag lap (a mistake, a battle).
Otherwise ``clean``, and only clean laps are fitted.

**Stint boundaries are snapped to OpenF1's own pit-out laps.** OpenF1's
``/stints`` numbers whole races a lap low at times (R1, R5, R6, R16 of 2026),
while lap times come from ``/laps``. A new stint's first lap is moved to the
pit-out lap within one lap of where ``/stints`` puts it; one with no pit-out lap
nearby is left where it is and counted in ``unchecked_boundaries``.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

from app.config import TRAFFIC_GAP_SECONDS
from app.data.openf1.race_control import RED_FLAG, SAFETY_CAR, VIRTUAL_SAFETY_CAR

if TYPE_CHECKING:
    from datetime import datetime

    from app.data.openf1.laps import Lap
    from app.data.openf1.race_context import RaceContext, TimeWindow
    from app.data.openf1.race_control import Window
    from app.data.openf1.session_laps import SessionLaps
    from app.data.stint_model import Stint

CLEAN = "clean"
LAP1 = "lap1"
NO_TIME = "no_time"
PIT_OUT = "pit_out"
PIT_IN = "pit_in"
RESTART = "restart"
WET = "wet"
UNKNOWN_AGE = "unknown_age"
TRAFFIC = "traffic"
OUTLIER = "outlier"

STATUS_LABELS: dict[str, str] = {
    CLEAN: "Clean lap",
    LAP1: "Opening lap",
    NO_TIME: "No lap time published",
    PIT_OUT: "Out-lap from the pits",
    PIT_IN: "In-lap to the pits",
    RED_FLAG: "Red flag",
    SAFETY_CAR: "Safety car",
    VIRTUAL_SAFETY_CAR: "Virtual safety car",
    RESTART: "First lap after a restart",
    WET: "Rain reported",
    UNKNOWN_AGE: "Tyre age not published",
    TRAFFIC: f"Within {TRAFFIC_GAP_SECONDS:g}s of the car ahead",
    OUTLIER: "Over 107% of the driver's median lap",
}

OUTLIER_FACTOR = 1.07
# Laps that count as green-flag running when the outlier median is taken.
_GREEN = frozenset({CLEAN, TRAFFIC})
# Neutralisations, most severe first.
_NEUTRALISED = (RED_FLAG, SAFETY_CAR, VIRTUAL_SAFETY_CAR)
SNAP_RANGE = 1


@dataclass(frozen=True)
class StintSpan:
    """A tyre set's laps for one car, on OpenF1's ``/laps`` lap numbers."""

    driver: int
    stint: int
    compound: str
    start: int
    end: int
    tyre_life_start: int | None
    checked: bool

    def tyre_age(self, lap: int) -> int | None:
        """Laps on the set at the end of ``lap`` (1 on a new set's first lap)."""
        return None if self.tyre_life_start is None else self.tyre_life_start + lap - self.start + 1


def _snap(start: int, pit_outs: set[int]) -> int | None:
    nearby = [lap for lap in pit_outs if abs(lap - start) <= SNAP_RANGE]
    return min(nearby, key=lambda lap: (abs(lap - start), lap), default=None)


def driver_spans(stints: list[Stint], laps: tuple[Lap, ...], driver: int) -> list[StintSpan]:
    """One driver's stints, boundaries snapped to their pit-out laps."""
    ordered = sorted(stints, key=lambda stint: stint.stint)
    pit_outs = {lap.number for lap in laps if lap.pit_out}
    last_lap = max((lap.number for lap in laps), default=0)
    starts: list[tuple[int, bool]] = [(1, True)]
    for stint in ordered[1:]:
        snapped = _snap(stint.start_lap, pit_outs)
        starts.append((stint.start_lap, False) if snapped is None else (snapped, True))
    spans = []
    for index, stint in enumerate(ordered):
        start, checked = starts[index]
        end = starts[index + 1][0] - 1 if index + 1 < len(ordered) else max(last_lap, stint.end_lap)
        spans.append(StintSpan(driver, index + 1, stint.compound, start, end, stint.tyre_life_start, checked))
    return spans


def all_spans(session: SessionLaps, context: RaceContext) -> dict[int, list[StintSpan]]:
    by_driver: dict[int, list[Stint]] = {}
    for stint in context.stints:
        driver = session.driver_by_code(stint.driver_code)
        if driver is not None:
            by_driver.setdefault(driver.number, []).append(stint)
    return {number: driver_spans(stints, session.laps_of(number), number) for number, stints in by_driver.items()}


def span_of(spans: list[StintSpan], lap: int) -> StintSpan | None:
    return next((span for span in spans if span.start <= lap <= span.end), None)


def _overlaps(lap: Lap, start: datetime, end: datetime | None) -> bool:
    if lap.start is None:
        return False
    lap_end = lap.end or lap.start
    return lap_end > start and (end is None or lap.start < end)


def neutralised(lap: Lap, windows: tuple[Window, ...]) -> str | None:
    kinds = {window.kind for window in windows if _overlaps(lap, window.start, window.end)}
    return next((kind for kind in _NEUTRALISED if kind in kinds), None)


def restart_laps(laps: tuple[Lap, ...], windows: tuple[Window, ...]) -> set[int]:
    """Each car's first lap begun after a safety car or red flag ended."""
    restarts = set()
    for window in windows:
        if window.kind == VIRTUAL_SAFETY_CAR or window.end is None:
            continue
        after = [lap.number for lap in laps if lap.start is not None and lap.start >= window.end]
        if after:
            restarts.add(min(after))
    return restarts


def is_wet(lap: Lap, rain: tuple[TimeWindow, ...]) -> bool:
    return any(_overlaps(lap, start, end) for start, end in rain)


@dataclass(frozen=True)
class LapFacts:
    """What one car's race says about its laps beyond their times."""

    spans: list[StintSpan]
    restarts: set[int]
    windows: tuple[Window, ...]
    rain: tuple[TimeWindow, ...]


def first_status(lap: Lap, facts: LapFacts, gap: float | None) -> str:
    """The lap's status before outliers are judged."""
    span = span_of(facts.spans, lap.number)
    checks = (
        (lap.number == 1, LAP1),
        (lap.time is None, NO_TIME),
        (lap.pit_out, PIT_OUT),
        (span is not None and lap.number == span.end and span is not facts.spans[-1], PIT_IN),
    )
    status = next((label for applies, label in checks if applies), None)
    if status is not None:
        return status
    neutral = neutralised(lap, facts.windows)
    later_checks = (
        (neutral is not None, neutral or ""),
        (lap.number in facts.restarts, RESTART),
        (is_wet(lap, facts.rain), WET),
        (span is None or span.tyre_life_start is None, UNKNOWN_AGE),
        (gap is not None and gap < TRAFFIC_GAP_SECONDS, TRAFFIC),
    )
    return next((label for applies, label in later_checks if applies), CLEAN)


def driver_statuses(laps: tuple[Lap, ...], facts: LapFacts, gaps: dict[tuple[int, int], float]) -> dict[int, str]:
    """Every lap's status for one car, outliers included."""
    statuses = {lap.number: first_status(lap, facts, gaps.get((lap.driver, lap.number))) for lap in laps}
    green = [lap.time for lap in laps if lap.time is not None and statuses[lap.number] in _GREEN]
    if not green:
        return statuses
    limit = OUTLIER_FACTOR * median(green)
    for lap in laps:
        if statuses[lap.number] == CLEAN and lap.time is not None and lap.time > limit:
            statuses[lap.number] = OUTLIER
    return statuses
