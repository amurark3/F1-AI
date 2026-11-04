"""Shared helpers for the LLM-callable tools.

Drivers and teams are labelled under f1db's names ("Kimi Antonelli (ANT)",
"Racing Bulls"), not FastF1's ("Andrea Kimi Antonelli", "RB F1 Team"); FastF1's
own words stay when f1db cannot say. See :mod:`app.data.canonical_names`.
"""

from __future__ import annotations

import pandas as pd

from app.data.canonical_names import driver_identity, feed_text, team_display_name

#: What a cell prints when there is nothing honest to put in it.
MISSING = "-"


def _fmt_timedelta(time_val: pd.Timedelta | None) -> str:
    """
    Converts a pandas Timedelta (or NaT) to a clean lap-time string.

    Examples:
      0 days 00:01:23.456 → "1:23.456"
      0 days 00:00:45.123 → "45.123"
      NaT                 → "-"
    """
    if pd.isna(time_val):
        return "-"
    s = str(time_val).split("days")[-1].strip()
    s = s.removeprefix("00:")  # Remove the leading "00:" hour field when zero
    if len(s) > 10:
        s = s[:9]  # Trim sub-millisecond precision
    return s


def _fmt_driver(row: pd.Series, year: int) -> str:
    """'Kimi Antonelli (ANT)' — f1db's name for the driver, with FastF1's code as a handle.

    A bare code invites the model to guess who it is, and its memory of the
    grid predates the current season: given only "ANT" it wrote "Fernando
    Alonso". The name is resolved from the row's code, car number and
    FullName; when none of them names anyone (FastF1 leaves FullName blank
    when its driver-info fetch fails), the code alone is all that can honestly
    be shown. A missing code is left out rather than printed as "nan".
    """
    code = feed_text(row.get("Abbreviation"))
    name = driver_identity(year, code=code, number=row.get("DriverNumber"), name=row.get("FullName")).name
    if name and code:
        return f"{name} ({code})"
    return name or code or MISSING


def _fmt_team(row: pd.Series, year: int) -> str:
    """f1db's name for the row's team ("RB F1 Team" -> "Racing Bulls"), else FastF1's spelling."""
    return team_display_name(year, row.get("TeamName")) or MISSING


def _fmt_points(value: float) -> str:
    """FastF1 stores points as floats; "25.0" in a results table reads wrong."""
    return str(value).removesuffix(".0")
