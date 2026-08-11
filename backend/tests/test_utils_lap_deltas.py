"""Tests for app.utils.lap_deltas — head-to-head lap and sector gap arithmetic.

The chat tool and the MCP server both render this comparison, so a sign slip or
a NaT leaking through is shown to a user as a driver being *faster* than a rival
they were actually slower than. The unknown-gap path carries most of the risk:
a deleted lap or an incomplete sector must render as unknown, never as a dead
heat, because ``NaT.total_seconds()`` is nan and nan > 0 is False.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.utils.lap_deltas import (
    LAP_DELTA_COLUMNS,
    delta_indicator,
    format_delta,
    lap_deltas,
    sector_delta,
)


def _lap(**times: float | None) -> pd.Series:
    """A timing row: seconds per column, or None for a missing/deleted time."""
    return pd.Series(
        {column: pd.NaT if value is None else pd.Timedelta(seconds=value) for column, value in times.items()}
    )


# ---------------------------------------------------------------------------
# sector_delta
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sector_delta_is_positive_when_the_first_lap_is_slower():
    gap = sector_delta(_lap(LapTime=91.512), _lap(LapTime=90.312), "LapTime")

    assert gap == pytest.approx(1.2)


@pytest.mark.unit
def test_sector_delta_is_negative_when_the_first_lap_is_faster():
    gap = sector_delta(_lap(Sector1Time=28.100), _lap(Sector1Time=28.450), "Sector1Time")

    assert gap == pytest.approx(-0.35)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("first", "second"),
    [(None, 90.0), (90.0, None), (None, None)],
    ids=["first-lap-deleted", "second-lap-deleted", "both-deleted"],
)
def test_sector_delta_reports_a_missing_time_as_unknown(first, second):
    """A missing time is an unknown gap — reporting 0.0 would imply a dead heat."""
    assert sector_delta(_lap(LapTime=first), _lap(LapTime=second), "LapTime") is None


# ---------------------------------------------------------------------------
# format_delta
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1.2, "+1.200s"),
        (-0.35, "-0.350s"),
        (0.0, "0.000s"),
        (0.0004, "+0.000s"),
        (None, "-"),
    ],
    ids=["slower", "faster", "dead-heat", "rounds-to-zero-but-still-slower", "unknown"],
)
def test_format_delta_renders_the_gap_to_the_millisecond(seconds, expected):
    assert format_delta(seconds) == expected


# ---------------------------------------------------------------------------
# delta_indicator
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "labelled", "expected"),
    [
        (0.4, False, "🔴"),
        (0.4, True, "🔴 Slower"),
        (-0.4, False, "🟢"),
        (-0.4, True, "🟢 Faster"),
        (0.0, True, "🟢 Faster"),
        (None, False, "⚪"),
        (None, True, "⚪ Unknown"),
    ],
)
def test_delta_indicator_colours_the_gap(seconds, labelled, expected):
    assert delta_indicator(seconds, labelled=labelled) == expected


# ---------------------------------------------------------------------------
# lap_deltas
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lap_deltas_returns_one_gap_per_column_in_the_order_given():
    first = _lap(LapTime=90.5, Sector1Time=28.0, Sector2Time=None, Sector3Time=32.5)
    second = _lap(LapTime=90.0, Sector1Time=28.4, Sector2Time=30.0, Sector3Time=32.0)

    gaps = lap_deltas(first, second, LAP_DELTA_COLUMNS)

    assert gaps[0] == pytest.approx(0.5)
    assert gaps[1] == pytest.approx(-0.4)
    assert gaps[2] is None, "a missing sector must not collapse into a zero gap"
    assert gaps[3] == pytest.approx(0.5)


@pytest.mark.unit
def test_lap_deltas_of_no_columns_is_empty():
    assert lap_deltas(_lap(LapTime=90.0), _lap(LapTime=90.0), []) == []


@pytest.mark.unit
def test_lap_delta_columns_lead_with_the_total_lap_then_the_three_sectors():
    assert LAP_DELTA_COLUMNS == ("LapTime", "Sector1Time", "Sector2Time", "Sector3Time")
