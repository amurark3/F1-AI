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
