"""Which of a driver's laps is analysed.

By default the fastest **valid** lap: it has a time and a start, it did not
begin in the pit lane, and race control did not delete it. Car 1's quickest
Austin 2026 qualifying time (1:34.379) was deleted for track limits, so picking
the plain minimum would have mapped a lap that does not count.

A caller may ask for a specific lap instead, a deleted one included; the answer
then says it was deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.data.openf1.laps import Lap
    from app.data.openf1.session_laps import SessionLaps


@dataclass(frozen=True)
class LapChoice:
    lap: Lap
    # The driver's fastest valid lap, for "is this the best one?"; None if none counts.
    fastest: Lap | None


def is_timed(lap: Lap) -> bool:
    """A lap with a start and a time that did not begin in the pit lane."""
    return lap.time is not None and lap.start is not None and not lap.pit_out


def fastest_valid_lap(laps: tuple[Lap, ...]) -> Lap | None:
    valid = [lap for lap in laps if is_timed(lap) and not lap.deleted]
    return min(valid, key=lambda lap: (lap.time, lap.number), default=None)


def choose_lap(session: SessionLaps, driver_number: int, lap_number: int | None) -> LapChoice | None:
    """The lap asked for (or the fastest valid one); None when there is no such timed lap."""
    own = session.laps_of(driver_number)
    fastest = fastest_valid_lap(own)
    if lap_number is None:
        return None if fastest is None else LapChoice(lap=fastest, fastest=fastest)
    lap = next((lap for lap in own if lap.number == lap_number and is_timed(lap)), None)
    return None if lap is None else LapChoice(lap=lap, fastest=fastest)


def timed_laps(session: SessionLaps, driver_number: int) -> list[dict]:
    """Every timed lap of a driver, for the lap picker."""
    own = session.laps_of(driver_number)
    fastest = fastest_valid_lap(own)
    return [
        {
            "number": lap.number,
            "time": lap.time,
            "deleted": lap.deleted,
            "is_fastest": fastest is not None and lap.number == fastest.number,
        }
        for lap in own
        if is_timed(lap)
    ]
