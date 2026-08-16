"""Tests for app.api.tools.formatting — lap times as the model reads them back.

``_fmt_timedelta`` is the last step before a lap time reaches the user through
the LLM, and pandas renders a ``Timedelta`` as ``0 days 00:01:23.456000`` —
unusable in a timing table. The risks pinned here are a missing time silently
formatting as a real one, and the fixed-width trim mangling a long time.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.api.tools.formatting import _fmt_timedelta


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0 days 00:01:23.456", "01:23.456"),
        ("0 days 00:00:45.123", "00:45.123"),
        # Whole seconds carry no fractional part, so nothing is trimmed.
        ("0 days 00:00:05", "00:05"),
        ("0 days 00:02:00", "02:00"),
    ],
)
def test_a_lap_time_loses_the_day_and_hour_fields(raw, expected):
    assert _fmt_timedelta(pd.Timedelta(raw)) == expected


@pytest.mark.unit
def test_sub_millisecond_precision_is_trimmed_away():
    """Timing screens stop at the millisecond; the extra digits are noise."""
    assert _fmt_timedelta(pd.Timedelta("0 days 00:01:23.456789")) == "01:23.456"


@pytest.mark.unit
def test_a_missing_time_renders_as_a_dash_not_a_zero():
    """A driver with no time set must not appear to have lapped instantly."""
    assert _fmt_timedelta(pd.NaT) == "-"


@pytest.mark.unit
def test_a_race_length_duration_is_truncated_to_nine_characters():
    """Pins current behaviour: the hour field survives but the trim cuts mid-number."""
    assert _fmt_timedelta(pd.Timedelta("0 days 01:02:03.456789")) == "01:02:03."
