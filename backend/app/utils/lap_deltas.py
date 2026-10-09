"""Lap and sector gaps between two drivers, formatted for display.

Shared by the chat tool and the MCP server, which present the same head-to-head
comparison and previously carried their own copies of this arithmetic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Sequence

# Gap magnitudes are reported to the millisecond, matching timing-screen precision.
_GAP_PRECISION = 3

# Total lap followed by the three sectors — the order both comparison tables use.
LAP_DELTA_COLUMNS = ("LapTime", "Sector1Time", "Sector2Time", "Sector3Time")


def sector_delta(first_lap: pd.Series, second_lap: pd.Series, column: str) -> float | None:
    """Seconds ``first_lap`` is slower than ``second_lap`` on ``column``.

    Returns None when either lap lacks that time. A deleted lap or an incomplete
    sector is an unknown gap, not a dead heat: subtracting through it yields NaT,
    and NaT.total_seconds() is nan, which compares false against zero and would
    otherwise be rendered as the driver being *faster*.
    """
    delta = first_lap[column] - second_lap[column]
    if pd.isna(delta):
        return None
    return delta.total_seconds()


def format_delta(seconds: float | None) -> str:
    """Signed gap in seconds, or a dash when the gap is unknown."""
    if seconds is None:
        return "-"
    return f"{'+' if seconds > 0 else ''}{seconds:.{_GAP_PRECISION}f}s"


def delta_indicator(seconds: float | None, *, labelled: bool = False) -> str:
    """Red when slower, green when faster, neutral when the gap is unknown."""
    if seconds is None:
        return "⚪ Unknown" if labelled else "⚪"
    if seconds > 0:
        return "🔴 Slower" if labelled else "🔴"
    return "🟢 Faster" if labelled else "🟢"


def lap_deltas(first_lap: pd.Series, second_lap: pd.Series, columns: Sequence[str]) -> list[float | None]:
    """Gaps for several timing columns at once, in the order given."""
    return [sector_delta(first_lap, second_lap, column) for column in columns]
