"""Tests for picking the weekend whose lineup a provisional grid carries over.

Before a weekend's first session there is no entry list for it, so the grid
borrows the most recent weekend that *has* run. For a race weeks away that is
not ``round - 1`` — the rounds in between have not run either, and loading them
would be a string of slow, failing FastF1 calls.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.data.predictions import _previous_started_round

NOW = datetime.now(timezone.utc)


def schedule(*rounds_and_first_session_offsets_days):
    """A minimal event schedule: one row per round, FP1 ``offset`` days from now."""
    rows = []
    for round_num, offset_days in rounds_and_first_session_offsets_days:
        first = pd.Timestamp(NOW + timedelta(days=offset_days))
        rows.append(
            {
                "RoundNumber": round_num,
                "Session1DateUtc": first,
                "Session5DateUtc": first + pd.Timedelta(days=2),
            }
        )
    return pd.DataFrame(rows)


SEASON = schedule((13, -24), (14, -17), (15, -5), (16, 3), (17, 10), (18, 24))


def test_next_race_carries_over_the_weekend_just_run():
    assert _previous_started_round(SEASON, 16) == 15


def test_a_race_weeks_away_skips_rounds_that_have_not_run_either():
    assert _previous_started_round(SEASON, 18) == 15


def test_the_first_round_of_a_season_has_nothing_to_carry_over():
    assert _previous_started_round(SEASON, 13) is None


def test_an_unknown_schedule_carries_nothing_over():
    assert _previous_started_round(None, 16) is None
