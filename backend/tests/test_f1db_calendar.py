"""Tests for app.data.f1db_calendar: the season calendar from f1db, in FastF1's schedule shape.

On f1db v2026.20.0's real rows (``fixtures/f1db_calendar``):

* A conventional 2026 weekend (Mexico City, R19) lists three practices,
  qualifying and the race; a sprint weekend (Singapore, R17) lists sprint
  qualifying and the sprint instead of FP2 and FP3. The starts are the ones
  OpenF1 lists for R19 and R20.
* f1db sets no session times before 2024, so a 2023 weekend lists no sessions;
  its race day and format still come through.
* A season f1db does not hold, or an f1db that cannot be read, is an
  unavailable calendar (a ValueError, as FastF1's was), never an empty one.
"""

from __future__ import annotations

from datetime import UTC
import json
from pathlib import Path

import pandas as pd
import pytest

from app.data.f1db_calendar import CalendarUnavailableError, season_schedule
from app.services.live_timing import parse_iso

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"


def _row(year: int, round_num: int) -> pd.Series:
    schedule = season_schedule(year)
    return schedule[schedule["RoundNumber"] == round_num].iloc[0]


def _sessions(row: pd.Series) -> list[tuple[str, pd.Timestamp]]:
    return [(row[f"Session{i}"], row[f"Session{i}DateUtc"]) for i in range(1, 6) if row[f"Session{i}"] is not None]


def test_a_conventional_weekend_maps_to_fastf1s_columns(calendar_f1db):
    row = _row(2026, 19)

    assert row["EventName"] == "Mexican Grand Prix"
    assert (row["Location"], row["Country"], row["CircuitId"]) == ("Mexico City", "Mexico", "mexico-city")
    assert row["EventDate"] == pd.Timestamp("2026-11-01")
    assert row["EventFormat"] == "conventional"
    assert _sessions(row) == [
        ("Practice 1", pd.Timestamp("2026-10-30 18:30")),
        ("Practice 2", pd.Timestamp("2026-10-30 22:00")),
        ("Practice 3", pd.Timestamp("2026-10-31 17:30")),
        ("Qualifying", pd.Timestamp("2026-10-31 21:00")),
        ("Race", pd.Timestamp("2026-11-01 20:00")),
    ]


def test_a_sprint_weekend_lists_sprint_qualifying_and_the_sprint_in_running_order(calendar_f1db):
    row = _row(2026, 17)

    assert (row["EventName"], row["Location"], row["EventFormat"]) == ("Singapore Grand Prix", "Singapore", "sprint")
    assert _sessions(row) == [
        ("Practice 1", pd.Timestamp("2026-10-09 08:30")),
        ("Sprint Qualifying", pd.Timestamp("2026-10-09 12:30")),
        ("Sprint", pd.Timestamp("2026-10-10 09:00")),
        ("Qualifying", pd.Timestamp("2026-10-10 13:00")),
        ("Race", pd.Timestamp("2026-10-11 12:00")),
    ]


@pytest.mark.parametrize(
    ("round_num", "capture"), [(19, "mexico_2026_r19"), (20, "sao_paulo_2026_r20")], ids=["R19", "R20"]
)
def test_session_starts_are_the_ones_openf1_lists(calendar_f1db, round_num, capture):
    openf1 = json.loads((FIXTURES / capture / "openf1_sessions.json").read_text())

    starts = [start.tz_localize(UTC) for _name, start in _sessions(_row(2026, round_num))]

    assert starts == [parse_iso(session["date_start"]) for session in openf1]


def test_the_2026_calendar_has_every_round_and_the_bahrain_grand_prix_at_sepang(calendar_f1db):
    schedule = season_schedule(2026)

    assert schedule["RoundNumber"].tolist() == list(range(1, 24))
    assert (schedule["EventFormat"] == "sprint").sum() == 6
    bahrain = _row(2026, 16)
    assert (bahrain["EventName"], bahrain["Location"], bahrain["Country"]) == (
        "Bahrain Grand Prix",
        "Sepang",
        "Malaysia",
    )


def test_a_season_before_2024_has_race_days_and_formats_but_no_session_times(calendar_f1db):
    schedule = season_schedule(2023)
    baku = _row(2023, 4)

    assert len(schedule) == 22
    assert schedule["Session1"].isna().all()
    assert schedule["Session1DateUtc"].isna().all()
    assert (baku["EventName"], baku["EventDate"], baku["EventFormat"]) == (
        "Azerbaijan Grand Prix",
        pd.Timestamp("2023-04-30"),
        "sprint",
    )
    assert _row(2023, 5)["EventFormat"] == "conventional"


def test_a_season_f1db_does_not_hold_yet_is_an_unavailable_calendar(calendar_f1db):
    with pytest.raises(CalendarUnavailableError, match="2027"):
        season_schedule(2027)


def test_an_unreadable_f1db_is_an_unavailable_calendar():
    # The autouse fixture leaves an empty f1db with no tables.
    with pytest.raises(CalendarUnavailableError):
        season_schedule(2026)


def test_an_unavailable_calendar_is_the_value_error_callers_already_handle():
    assert issubclass(CalendarUnavailableError, ValueError)
