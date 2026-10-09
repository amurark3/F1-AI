"""Tests for app.utils.f1_values — coercion of Ergast/FastF1 cell values.

These helpers exist because F1 dataframes use NaN, None and numpy scalars
interchangeably for "no value". Every branch below is one of those shapes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.f1_values import safe_float, safe_int, safe_str, utc_isoformat


class _FakeTimestamp:
    """Stand-in for a pandas Timestamp, which exposes ``to_pydatetime()``."""

    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def to_pydatetime(self) -> datetime:
        return self._dt


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        (float("nan"), 0),
        (7, 7),
        (7.9, 7),  # truncates toward zero, matching int()
        ("12", 12),
        (True, 1),
    ],
    ids=["none", "nan", "int", "float-truncates", "numeric-str", "bool"],
)
def test_safe_int_coerces_or_falls_back(value, expected):
    assert safe_int(value) == expected


@pytest.mark.unit
def test_safe_int_honours_custom_default():
    assert safe_int(None, default=-1) == -1
    assert safe_int(float("nan"), default=99) == 99


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0.0),
        (float("nan"), 0.0),
        (1.5, 1.5),
        (3, 3.0),
        ("2.25", 2.25),
    ],
    ids=["none", "nan", "float", "int", "numeric-str"],
)
def test_safe_float_coerces_or_falls_back(value, expected):
    assert safe_float(value) == expected


@pytest.mark.unit
def test_safe_float_honours_custom_default():
    assert safe_float(None, default=9.5) == 9.5
    assert safe_float(float("nan"), default=-3.0) == -3.0


@pytest.mark.unit
def test_safe_float_preserves_infinity():
    # inf is a real measurement (an unset delta), not a missing value.
    assert safe_float(float("inf")) == float("inf")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "key", "expected"),
    [
        ({"Driver": "VER"}, "Driver", "VER"),
        ({"Driver": None}, "Driver", ""),
        ({"Driver": float("nan")}, "Driver", ""),
        ({"Driver": 44}, "Driver", "44"),
        ({}, "Missing", ""),
    ],
    ids=["present", "none", "nan", "non-str", "absent"],
)
def test_safe_str_reads_row_key(row, key, expected):
    assert safe_str(row, key) == expected


@pytest.mark.unit
def test_safe_str_default_is_used_for_absent_and_null_alike():
    assert safe_str({}, "Team", default="Unknown") == "Unknown"
    assert safe_str({"Team": None}, "Team", default="Unknown") == "Unknown"


@pytest.mark.unit
def test_utc_isoformat_stamps_naive_datetimes_as_utc():
    naive = datetime(2026, 3, 8, 14, 30, 0)

    assert utc_isoformat(naive) == "2026-03-08T14:30:00Z"


@pytest.mark.unit
def test_utc_isoformat_converts_aware_datetimes_to_utc():
    # +02:00 local time is two hours ahead of the UTC instant it denotes.
    aware = datetime(2026, 3, 8, 16, 30, 0, tzinfo=timezone(timedelta(hours=2)))

    assert utc_isoformat(aware) == "2026-03-08T14:30:00Z"


@pytest.mark.unit
def test_utc_isoformat_unwraps_pandas_timestamps():
    stamp = _FakeTimestamp(datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc))

    assert utc_isoformat(stamp) == "2026-07-01T09:00:00Z"


@pytest.mark.unit
def test_utc_isoformat_always_ends_in_z_never_offset():
    # The frontend parses these with `new Date(...)`; a bare "+00:00" is legal
    # ISO but the Z form is what the clients are written against.
    assert not utc_isoformat(datetime(2026, 1, 1, tzinfo=timezone.utc)).endswith("+00:00")
