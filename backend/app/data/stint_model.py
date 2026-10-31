"""One tyre stint, as every stint source reports it.

Shared by :mod:`app.data.race_stints` (FastF1), :mod:`app.data.openf1_stints`
and :mod:`app.data.race_stints_store`, so each source normalises onto the same
meaning rather than the chart learning two of them.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What FastF1 writes when it has lap rows but no compound for them.
UNKNOWN_COMPOUND = "UNKNOWN"


@dataclass(frozen=True)
class Stint:
    """One run on one set of tyres."""

    driver_code: str
    #: Constructor the driver ran for, for livery-tinting a stint chart.
    team: str
    #: Which stint of the race, counting from 1.
    stint: int
    #: Tyre compound, or ``None`` when the source has no compound for it.
    compound: str | None
    start_lap: int
    end_lap: int
    laps: int
    #: Laps already on the set when the stint began: 0 for a new set.
    tyre_life_start: int | None
    #: Whether the set was new when fitted. ``None`` when not recorded.
    fresh: bool | None
    #: True when the lap this stint ended on was red-flagged, which makes the
    #: tyre change a consequence of the suspension rather than a pit stop.
    ended_under_red_flag: bool


def clean_compound(value: object) -> str | None:
    """A compound name, or ``None`` for a blank, NaN or unknown one."""
    text = str(value or "").strip().upper()
    if not text or text in {"NAN", "NONE", UNKNOWN_COMPOUND}:
        return None
    return text
