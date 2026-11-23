"""OpenF1's trackside station, summarised per session."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.data.openf1.track_weather import summarise_track_weather

pytestmark = pytest.mark.unit

START = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
END = datetime(2026, 11, 1, 22, 0, tzinfo=UTC)

# Hand-built OpenF1 /weather rows (the real fields), deliberately out of order.
ROWS = [
    {"date": "2026-11-01T21:00:00+00:00", "track_temperature": 20.0, "air_temperature": 15.0, "rainfall": 1},
    {"date": "2026-11-01T20:00:00+00:00", "track_temperature": 18.0, "air_temperature": 14.0, "rainfall": 0},
    {"date": "2026-11-01T20:30:00+00:00", "track_temperature": None, "air_temperature": "warm", "rainfall": True},
    {"date": "2026-11-01T12:00:00+00:00", "track_temperature": 40.0, "air_temperature": 30.0, "rainfall": 0},
    {"date": "not a date", "track_temperature": 99.0},
]


def test_summary_is_mean_range_and_rain_flags_in_time_order():
    assert summarise_track_weather(ROWS, START, END) == {
        "track_temp_c": 19.0,
        "track_temp_min_c": 18.0,
        "track_temp_max_c": 20.0,
        "air_temp_c": 14.5,
        "rainfall": [False, True],
    }


def test_rows_outside_the_session_are_kept_when_a_bound_is_unknown():
    assert summarise_track_weather(ROWS, START, None)["track_temp_max_c"] == 40.0
    assert summarise_track_weather(ROWS, None, END)["track_temp_c"] == 26.0


def test_no_numeric_value_is_no_summary():
    assert (
        summarise_track_weather([{"date": "2026-11-01T20:00:00+00:00", "track_temperature": "x"}], None, None) is None
    )
    assert summarise_track_weather([], START, END) is None


def test_a_partial_reading_keeps_the_nulls():
    only_air = [{"date": "2026-11-01T20:00:00+00:00", "air_temperature": 13.25}]
    assert summarise_track_weather(only_air, None, None) == {
        "track_temp_c": None,
        "track_temp_min_c": None,
        "track_temp_max_c": None,
        "air_temp_c": 13.2,
        "rainfall": [],
    }
