"""Shared helpers for the LLM-callable tools."""

from __future__ import annotations

import pandas as pd


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


def _fmt_driver(row: pd.Series) -> str:
    """'Andrea Kimi Antonelli (ANT)' — the full name, with the code as a handle.

    A bare code invites the model to guess who it is, and its memory of the
    grid predates the current season: given only "ANT" it wrote "Fernando
    Alonso". FastF1 leaves FullName blank when its driver-info fetch fails, and
    then the code alone is all that can honestly be shown.
    """
    name = row.get("FullName")
    code = row["Abbreviation"]
    return f"{name.strip()} ({code})" if isinstance(name, str) and name.strip() else code


def _fmt_points(value: float) -> str:
    """FastF1 stores points as floats; "25.0" in a results table reads wrong."""
    return str(value).removesuffix(".0")
