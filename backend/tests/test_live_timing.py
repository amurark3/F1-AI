"""Unit tests for live-timing session resolution and freshness guards.

These cover the defects that let the Belgian Grand Prix's final classification
render as a live Dutch Grand Prix timing tower:

  * positional round->meeting indexing against a calendar that disagrees
  * "first Race session" selecting the Sprint on a sprint weekend
  * OpenF1 serving a finished session's last rows forever
  * a wall-clock staleness gate reading a quiet track as a dead feed
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.live_timing import (
    build_positions,
    derive_session_state,
    feed_belongs_to_session,
    match_meeting,
    newest_feed_sample,
    newest_sample_time,
    next_session_start,
    parse_iso,
    scheduled_session_now,
    select_active_session,
)

pytestmark = pytest.mark.unit


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# parse_iso
# --------------------------------------------------------------------------


def test_parse_iso_reads_offset_timestamps():
    assert parse_iso("2026-08-23T13:00:00+00:00") == _utc(2026, 8, 23, 13, 0)


def test_parse_iso_assumes_utc_for_naive_timestamps():
    assert parse_iso("2026-08-23T13:00:00") == _utc(2026, 8, 23, 13, 0)


@pytest.mark.parametrize("value", [None, "", "not-a-date", 42])
def test_parse_iso_returns_none_for_unusable_input(value):
    assert parse_iso(value) is None


# --------------------------------------------------------------------------
# match_meeting
# --------------------------------------------------------------------------

# Mirrors the real 2026 OpenF1 payload: it carries an April Bahrain and Saudi
# Arabian round that FastF1's schedule omits, so OpenF1's ordering runs two
# ahead. Indexing by round number lands on Belgium when asked for the Dutch GP.
MEETINGS_2026 = [
    {"meeting_key": 1279, "meeting_name": "Australian Grand Prix", "location": "Melbourne",
     "date_start": "2026-03-06T01:30:00+00:00"},
    {"meeting_key": 1282, "meeting_name": "Bahrain Grand Prix", "location": "Sakhir",
     "date_start": "2026-04-10T11:30:00+00:00"},
    {"meeting_key": 1283, "meeting_name": "Saudi Arabian Grand Prix", "location": "Jeddah",
     "date_start": "2026-04-17T13:30:00+00:00"},
    {"meeting_key": 1290, "meeting_name": "Belgian Grand Prix", "location": "Spa-Francorchamps",
     "date_start": "2026-07-17T10:30:00+00:00"},
    {"meeting_key": 1292, "meeting_name": "Dutch Grand Prix", "location": "Zandvoort",
     "date_start": "2026-08-21T10:30:00+00:00"},
]


def test_match_meeting_resolves_by_circuit_location():
    match = match_meeting(MEETINGS_2026, "Zandvoort", _utc(2026, 8, 23))
    assert match["meeting_key"] == 1292


def test_match_meeting_ignores_case_and_padding():
    match = match_meeting(MEETINGS_2026, "  zandvoort ", _utc(2026, 8, 23))
    assert match["meeting_key"] == 1292


def test_match_meeting_does_not_shift_when_calendars_disagree():
    """Regression: the Dutch GP must never resolve to the Belgian GP.

    FastF1 numbers the Dutch GP round 12; OpenF1's meeting list holds it at
    index 14. Any positional lookup returns Spa here.
    """
    match = match_meeting(MEETINGS_2026, "Zandvoort", _utc(2026, 8, 23))
    assert match["meeting_name"] == "Dutch Grand Prix"
    assert match["meeting_name"] != "Belgian Grand Prix"


def test_match_meeting_falls_back_to_the_event_date_window():
    renamed = [{"meeting_key": 1292, "meeting_name": "Dutch Grand Prix",
                "location": "Circuit Zandvoort", "date_start": "2026-08-21T10:30:00+00:00"}]
    match = match_meeting(renamed, "Zandvoort", _utc(2026, 8, 23))
    assert match["meeting_key"] == 1292


def test_match_meeting_rejects_a_date_outside_the_weekend_window():
    assert match_meeting(MEETINGS_2026, "Nowhere", _utc(2026, 5, 30)) is None


def test_match_meeting_returns_none_for_an_empty_calendar():
    assert match_meeting([], "Zandvoort", _utc(2026, 8, 23)) is None


# --------------------------------------------------------------------------
# select_active_session
# --------------------------------------------------------------------------

# The real Zandvoort 2026 weekend — a sprint weekend, so two sessions carry
# session_type "Race" and the Sprint sorts first.
DUTCH_SESSIONS = [
    {"session_key": 11343, "session_type": "Practice", "session_name": "Practice 1",
     "date_start": "2026-08-21T10:30:00+00:00", "date_end": "2026-08-21T11:30:00+00:00"},
    {"session_key": 11344, "session_type": "Qualifying", "session_name": "Sprint Qualifying",
     "date_start": "2026-08-21T14:30:00+00:00", "date_end": "2026-08-21T15:14:00+00:00"},
    {"session_key": 11348, "session_type": "Race", "session_name": "Sprint",
     "date_start": "2026-08-22T10:00:00+00:00", "date_end": "2026-08-22T10:44:00+00:00"},
    {"session_key": 11349, "session_type": "Qualifying", "session_name": "Qualifying",
     "date_start": "2026-08-22T14:00:00+00:00", "date_end": "2026-08-22T15:00:00+00:00"},
    {"session_key": 11353, "session_type": "Race", "session_name": "Race",
     "date_start": "2026-08-23T13:00:00+00:00", "date_end": "2026-08-23T15:00:00+00:00"},
]


def test_select_active_session_picks_the_sprint_during_the_sprint():
    """A 'first session_type == Race' lookup returns the Sprint all weekend."""
    active = select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 22, 10, 20))
    assert active["session_key"] == 11348
    assert active["session_name"] == "Sprint"


def test_select_active_session_picks_the_grand_prix_on_sunday():
    active = select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 23, 13, 30))
    assert active["session_key"] == 11353
    assert active["session_name"] == "Race"


def test_select_active_session_follows_qualifying():
    active = select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 22, 14, 30))
    assert active["session_name"] == "Qualifying"


def test_select_active_session_is_empty_between_sessions():
    """Saturday 23:28 UTC — the moment in the bug report. Nothing is running."""
    assert select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 22, 23, 28)) is None


def test_select_active_session_is_empty_before_the_weekend():
    assert select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 20, 9, 0)) is None


def test_select_active_session_allows_a_grace_period_for_overruns():
    active = select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 23, 15, 10))
    assert active["session_key"] == 11353


def test_select_active_session_ends_after_the_grace_period():
    assert select_active_session(DUTCH_SESSIONS, _utc(2026, 8, 23, 15, 30)) is None


def test_select_active_session_skips_cancelled_sessions():
    cancelled = [{**s, "is_cancelled": True} for s in DUTCH_SESSIONS]
    assert select_active_session(cancelled, _utc(2026, 8, 23, 13, 30)) is None


def test_select_active_session_skips_sessions_with_unusable_timestamps():
    broken = [{"session_key": 1, "session_name": "Race", "date_start": None, "date_end": None}]
    assert select_active_session(broken, _utc(2026, 8, 23, 13, 30)) is None


# --------------------------------------------------------------------------
# freshness
# --------------------------------------------------------------------------

BELGIAN_ROWS = [
    {"driver_number": 12, "position": 1, "date": "2026-07-19T14:38:00+00:00"},
    {"driver_number": 16, "position": 2, "date": "2026-07-19T14:38:00+00:00"},
]


DUTCH_RACE_START = _utc(2026, 8, 23, 13, 0)


def test_newest_sample_time_takes_the_latest_row():
    rows = [{"date": "2026-08-23T13:00:00+00:00"}, {"date": "2026-08-23T13:04:00+00:00"}]
    assert newest_sample_time(rows) == _utc(2026, 8, 23, 13, 4)


def test_newest_sample_time_is_none_without_usable_dates():
    assert newest_sample_time([{"driver_number": 1}]) is None


def test_newest_feed_sample_spans_feeds_with_different_date_keys():
    """Practice publishes no gap feed, so laps are the only liveness signal."""
    feeds = [
        ([], "date"),
        ([{"date_start": "2026-08-23T13:04:00+00:00"}], "date_start"),
    ]
    assert newest_feed_sample(feeds) == _utc(2026, 8, 23, 13, 4)


def test_newest_feed_sample_takes_the_latest_across_every_feed():
    feeds = [
        ([{"date": "2026-08-23T13:04:00+00:00"}], "date"),
        ([{"date_start": "2026-08-23T13:31:00+00:00"}], "date_start"),
    ]
    assert newest_feed_sample(feeds) == _utc(2026, 8, 23, 13, 31)


def test_newest_feed_sample_is_none_when_every_feed_is_empty():
    assert newest_feed_sample([([], "date"), (None, "date_start")]) is None


def test_feed_belongs_to_session_rejects_a_finished_session_replayed_as_live():
    """The original bug: OpenF1 serves July's last rows forever."""
    newest = newest_sample_time(BELGIAN_ROWS)
    assert feed_belongs_to_session(newest, DUTCH_RACE_START) is False


def test_feed_belongs_to_session_accepts_a_sample_from_after_lights_out():
    newest = DUTCH_RACE_START + timedelta(minutes=4)
    assert feed_belongs_to_session(newest, DUTCH_RACE_START) is True


def test_feed_belongs_to_session_accepts_a_quiet_hour_mid_race():
    """Spain 2026 went 58 minutes without a position change; still a live race.

    This is the regression a wall-clock staleness gate caused: judged on age
    alone, the tower called a processional Grand Prix a dead feed for 39% of
    the race.
    """
    newest = DUTCH_RACE_START + timedelta(minutes=4)
    assert feed_belongs_to_session(newest, DUTCH_RACE_START) is True


def test_feed_belongs_to_session_rejects_the_pre_session_feed():
    """Spain's position feed opened 54 minutes before lights out."""
    newest = DUTCH_RACE_START - timedelta(minutes=54)
    assert feed_belongs_to_session(newest, DUTCH_RACE_START) is False


def test_feed_belongs_to_session_rejects_a_missing_sample():
    assert feed_belongs_to_session(None, DUTCH_RACE_START) is False


# --------------------------------------------------------------------------
# next_session_start
# --------------------------------------------------------------------------


def test_next_session_start_finds_the_window_about_to_open():
    """Two minutes before lights out the socket must know when to look again."""
    assert next_session_start(DUTCH_SESSIONS, _utc(2026, 8, 23, 12, 58)) == DUTCH_RACE_START


def test_next_session_start_ignores_a_session_already_under_way():
    assert next_session_start(DUTCH_SESSIONS, _utc(2026, 8, 22, 10, 20)) == _utc(2026, 8, 22, 14, 0)


def test_next_session_start_is_none_once_the_weekend_is_over():
    assert next_session_start(DUTCH_SESSIONS, _utc(2026, 8, 23, 16, 0)) is None


def test_next_session_start_skips_cancelled_sessions():
    cancelled = [{**s, "is_cancelled": True} for s in DUTCH_SESSIONS]
    assert next_session_start(cancelled, _utc(2026, 8, 20, 9, 0)) is None


def test_next_session_start_ignores_unusable_timestamps():
    assert next_session_start([{"date_start": None}], _utc(2026, 8, 20, 9, 0)) is None


# --------------------------------------------------------------------------
# derive_session_state
# --------------------------------------------------------------------------


def test_derive_session_state_is_standby_without_a_session():
    assert derive_session_state(None, _utc(2026, 8, 22, 23, 28), has_session_data=False) == "standby"


def test_derive_session_state_is_live_once_the_session_feed_opens():
    session = DUTCH_SESSIONS[4]
    assert derive_session_state(session, _utc(2026, 8, 23, 13, 30), has_session_data=True) == "live"


def test_derive_session_state_is_standby_in_window_before_the_feed_opens():
    """Never claim 'live' on the strength of the clock alone."""
    session = DUTCH_SESSIONS[4]
    assert derive_session_state(session, _utc(2026, 8, 23, 13, 30), has_session_data=False) == "standby"


def test_derive_session_state_is_standby_before_lights_out():
    session = DUTCH_SESSIONS[4]
    assert derive_session_state(session, _utc(2026, 8, 23, 12, 0), has_session_data=False) == "standby"


def test_derive_session_state_is_finished_after_the_window():
    session = DUTCH_SESSIONS[4]
    assert derive_session_state(session, _utc(2026, 8, 23, 16, 0), has_session_data=True) == "finished"


# --------------------------------------------------------------------------
# build_positions
# --------------------------------------------------------------------------

DRIVERS = {
    12: {"driver_number": 12, "name_acronym": "ANT", "team_name": "Mercedes"},
    16: {"driver_number": 16, "name_acronym": "LEC", "team_name": "Ferrari"},
}


def test_build_positions_orders_by_position_and_carries_car_numbers():
    rows = [
        {"driver_number": 16, "position": 2, "date": "2026-08-23T13:30:00+00:00"},
        {"driver_number": 12, "position": 1, "date": "2026-08-23T13:30:00+00:00"},
    ]
    intervals = [
        {"driver_number": 12, "gap_to_leader": 0.0},
        {"driver_number": 16, "gap_to_leader": 1.952},
    ]
    built = build_positions(rows, intervals, DRIVERS)
    assert [p["position"] for p in built] == [1, 2]
    assert built[0]["driver"] == "ANT"
    assert built[0]["driver_number"] == 12
    assert built[0]["gap"] == "LEADER"
    assert built[1]["gap"] == "+1.952"


def test_build_positions_uses_the_latest_row_per_driver():
    rows = [
        {"driver_number": 12, "position": 4, "date": "2026-08-23T13:00:00+00:00"},
        {"driver_number": 12, "position": 1, "date": "2026-08-23T13:30:00+00:00"},
    ]
    built = build_positions(rows, [], DRIVERS)
    assert [p["position"] for p in built] == [1]


def test_build_positions_shows_a_dash_when_the_gap_is_unknown():
    rows = [{"driver_number": 16, "position": 2, "date": "2026-08-23T13:30:00+00:00"}]
    built = build_positions(rows, [{"driver_number": 16, "gap_to_leader": None}], DRIVERS)
    assert built[0]["gap"] == "—"


def test_build_positions_survives_an_unmapped_driver_number():
    rows = [{"driver_number": 99, "position": 1, "date": "2026-08-23T13:30:00+00:00"}]
    built = build_positions(rows, [], DRIVERS)
    assert built[0]["driver"] == "99"
    assert built[0]["driver_number"] == 99


def test_build_positions_ignores_rows_without_a_driver_number():
    built = build_positions([{"position": 1}], [], DRIVERS)
    assert built == []


def test_build_positions_treats_a_non_numeric_gap_as_unknown():
    rows = [{"driver_number": 16, "position": 2, "date": "2026-08-23T13:30:00+00:00"}]
    built = build_positions(rows, [{"driver_number": 16, "gap_to_leader": "LAP 1"}], DRIVERS)
    assert built[0]["gap"] == "—"


# --------------------------------------------------------------------------
# scheduled_session_now — schedule-derived, for the shell status pill
# --------------------------------------------------------------------------

SCHEDULE = {
    "Practice 1": "2026-08-21T10:30:00+00:00",
    "Sprint": "2026-08-22T10:00:00+00:00",
    "Qualifying": "2026-08-22T14:00:00+00:00",
    "Race": "2026-08-23T13:00:00+00:00",
}


def test_scheduled_session_now_names_the_running_session():
    assert scheduled_session_now(SCHEDULE, _utc(2026, 8, 23, 13, 30)) == "Race"


def test_scheduled_session_now_is_none_between_sessions():
    """23:28 on Saturday: the weekend is in progress but nothing is running."""
    assert scheduled_session_now(SCHEDULE, _utc(2026, 8, 22, 23, 28)) is None


def test_scheduled_session_now_uses_a_shorter_window_for_practice():
    assert scheduled_session_now(SCHEDULE, _utc(2026, 8, 21, 11, 15)) == "Practice 1"
    assert scheduled_session_now(SCHEDULE, _utc(2026, 8, 21, 12, 30)) is None


def test_scheduled_session_now_handles_an_empty_schedule():
    assert scheduled_session_now({}, _utc(2026, 8, 23, 13, 30)) is None
