"""Tests for app.api.tools.formatting — lap times as the model reads them back.

``_fmt_timedelta`` is the last step before a lap time reaches the user through
the LLM, and pandas renders a ``Timedelta`` as ``0 days 00:01:23.456000`` —
unusable in a timing table. The risks pinned here are a missing time silently
formatting as a real one, and the fixed-width trim mangling a long time.

Drivers and teams are labelled under f1db's names ("Kimi Antonelli (ANT)",
"Racing Bulls"), not FastF1's ("Andrea Kimi Antonelli", "RB F1 Team"), with
FastF1's code as the handle, and FastF1's own words when f1db cannot be read.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest
import structlog

from app.api.tools.formatting import _fmt_driver, _fmt_points, _fmt_team, _fmt_timedelta
from app.data import f1db_source
from tests.identity_support import mexico_fastf1_results


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


@pytest.mark.unit
def test_a_driver_is_labelled_with_full_name_and_code():
    """A bare code invites a guess: given only ANT, the model wrote "Fernando Alonso (ANT)"."""
    assert _fmt_driver(pd.Series({"FullName": "Andrea Kimi Antonelli", "Abbreviation": "ANT"}), 2026) == (
        "Andrea Kimi Antonelli (ANT)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["", "  ", float("nan"), None])
def test_a_driver_with_no_full_name_falls_back_to_the_code(missing):
    """FastF1 leaves FullName blank when its driver-info fetch fails; "nan (ANT)" would read as a name."""
    assert _fmt_driver(pd.Series({"FullName": missing, "Abbreviation": "ANT"}), 2026) == "ANT"


@pytest.mark.unit
@pytest.mark.parametrize(("raw", "expected"), [(25.0, "25"), (8.0, "8"), (0.0, "0"), (0.5, "0.5")])
def test_whole_points_lose_their_trailing_decimal(raw, expected):
    assert _fmt_points(raw) == expected


def _mexico_row(number: int) -> pd.Series:
    """A FastF1 Mexico City result row (2026 R19), with the FullName FastF1 joins from its two halves."""
    row = next(row for row in mexico_fastf1_results() if int(row["DriverNumber"]) == number)
    return pd.Series({**row, "FullName": f"{row['FirstName']} {row['LastName']}"})


@pytest.mark.integration
@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (12, "Kimi Antonelli (ANT)"),
        (55, "Carlos Sainz Jr. (SAI)"),
        (27, "Nico Hülkenberg (HUL)"),
        # FastF1 had no abbreviation for him: his car number names him, and no "nan" handle is printed.
        (50, "Ryō Hirakawa"),
    ],
)
def test_a_driver_is_labelled_with_f1dbs_name_and_fastf1s_code(identity_f1db, number, expected):
    assert _fmt_driver(_mexico_row(number), 2026) == expected


@pytest.mark.integration
@pytest.mark.parametrize(
    ("number", "expected"),
    [(30, "Racing Bulls"), (50, "Haas"), (11, "Cadillac"), (3, "Red Bull")],
)
def test_a_team_is_labelled_with_f1dbs_name(identity_f1db, number, expected):
    assert _fmt_team(_mexico_row(number), 2026) == expected


@pytest.mark.unit
def test_a_row_with_no_team_and_no_way_to_name_the_driver_prints_dashes():
    """Neither "nan" nor a guess: a blank cell the model cannot mistake for a name."""
    row = pd.Series({"Abbreviation": float("nan"), "FullName": float("nan"), "TeamName": float("nan")})

    assert (_fmt_driver(row, 2026), _fmt_team(row, 2026)) == ("-", "-")


@pytest.mark.integration
def test_an_unreadable_f1db_labels_drivers_and_teams_in_fastf1s_words_and_logs_why(monkeypatch):
    def connect() -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(f1db_source, "connect", connect)

    with structlog.testing.capture_logs() as logs:
        labels = (_fmt_driver(_mexico_row(12), 2026), _fmt_team(_mexico_row(30), 2026))

    assert labels == ("Andrea Kimi Antonelli (ANT)", "RB F1 Team")
    assert {log["event"] for log in logs} == {"canonical_names.f1db_unreadable"}
