"""Tests for the schedule gates in app.data.predictions.sessions.

``_qualifying_has_occurred`` is what stops a prediction for a future race
spending its whole timeout on failing loads, and ``_weekend_has_started`` is why
the practice window is not left with no session data, so their clock arithmetic
is pinned in both directions. The loaders themselves are in
``test_predictions_session_inputs.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.data.predictions.sessions import _qualifying_has_occurred, _weekend_has_started

# ---------------------------------------------------------------------------
# Has qualifying run yet?
# ---------------------------------------------------------------------------


def _event(**fields: object) -> pd.Series:
    return pd.Series(fields)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("offset_hours", "expected"),
    [(-2, True), (2, False)],
)
def test_the_explicit_qualifying_slot_decides_whether_sessions_are_probed(offset_hours, expected):
    quali_at = datetime.now(UTC) + timedelta(hours=offset_hours)
    event = _event(
        Session1="Practice 1",
        Session4="Qualifying",
        Session4DateUtc=pd.Timestamp(quali_at.replace(tzinfo=None)),
        EventDate=pd.Timestamp(quali_at + timedelta(days=1)),
    )

    assert _qualifying_has_occurred(event) is expected


@pytest.mark.unit
def test_a_timezone_aware_schedule_entry_is_compared_in_utc():
    # FastF1 sometimes hands back tz-aware timestamps; naive comparison against
    # a UTC "now" would raise rather than answer.
    quali_at = datetime.now(UTC) - timedelta(hours=3)
    event = _event(Session4="Qualifying", Session4DateUtc=pd.Timestamp(quali_at).tz_convert("Europe/Rome"))

    assert _qualifying_has_occurred(event) is True


@pytest.mark.unit
def test_a_plain_datetime_in_the_schedule_is_handled_like_a_timestamp():
    event = _event(Session4="Qualifying", Session4DateUtc=datetime.now(UTC) - timedelta(hours=1))

    assert _qualifying_has_occurred(event) is True


@pytest.mark.unit
def test_a_qualifying_row_with_no_datetime_falls_back_to_the_race_date():
    # Named session, unknown time: the race date minus a day is the estimate.
    past = _event(Session4="Qualifying", Session4DateUtc=pd.NaT, EventDate=pd.Timestamp("2020-08-30"))
    future = _event(
        Session4="Qualifying",
        Session4DateUtc=pd.NaT,
        EventDate=pd.Timestamp(datetime.now(UTC) + timedelta(days=10)),
    )

    assert _qualifying_has_occurred(past) is True
    assert _qualifying_has_occurred(future) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("days_to_race", "expected"),
    [(3, False), (2, False), (0, True), (-1, True)],
)
def test_without_a_named_qualifying_session_the_race_date_minus_a_day_is_used(days_to_race, expected):
    # Qualifying is the day before the race on a conventional weekend, so a race
    # more than a day away means the weekend has not run.
    event = _event(
        Session1="Practice 1",
        EventDate=pd.Timestamp(datetime.now(UTC) + timedelta(days=days_to_race)),
    )

    assert _qualifying_has_occurred(event) is expected


@pytest.mark.unit
def test_an_unknown_schedule_attempts_the_load_rather_than_assuming_the_weekend_is_future():
    # Better to pay one failing load than to silently serve a historical-only
    # prediction for a race that has already been qualified for.
    assert _qualifying_has_occurred(_event(EventName="Unknown Grand Prix")) is True
    assert _qualifying_has_occurred(_event(Session4=None, EventDate=pd.NaT)) is True


# ---------------------------------------------------------------------------
# Has the weekend started?
# ---------------------------------------------------------------------------
# Practice pace and the entry list exist from FP1, so this gate is the earliest
# session, not qualifying.


@pytest.mark.unit
@pytest.mark.parametrize(("fp1_offset_hours", "expected"), [(-1, True), (6, False)])
def test_the_earliest_scheduled_session_decides_whether_the_weekend_has_started(fp1_offset_hours, expected):
    fp1_at = datetime.now(UTC) + timedelta(hours=fp1_offset_hours)
    event = _event(
        Session1="Practice 1",
        Session1DateUtc=pd.Timestamp(fp1_at.replace(tzinfo=None)),
        Session5="Race",
        Session5DateUtc=pd.Timestamp((fp1_at + timedelta(days=2)).replace(tzinfo=None)),
    )

    assert _weekend_has_started(event) is expected


@pytest.mark.unit
@pytest.mark.parametrize(("days_to_race", "expected"), [(3, False), (1, True), (-1, True)])
def test_without_session_times_the_race_date_minus_two_days_is_used(days_to_race, expected):
    event = _event(EventDate=pd.Timestamp(datetime.now(UTC) + timedelta(days=days_to_race)))

    assert _weekend_has_started(event) is expected


@pytest.mark.unit
def test_an_undated_weekend_is_assumed_to_have_started():
    """Attempting a load costs one failure; skipping it costs the whole session."""
    assert _weekend_has_started(_event(EventName="Unknown Grand Prix", EventDate=pd.NaT)) is True
