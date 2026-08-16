"""Tests for app.services.race_control.workstreams — the status board.

Every card on this board used to carry a hardcoded status ("Build", "Monitor",
"Standby") that never moved. The board is now derived, so what these tests
guard is that each status actually *tracks* the thing it claims to track:
session state for the brief and live control, telemetry availability for the
race model, and a genuinely close rival for rival watch.

The priorities (P1/P2) stay fixed on purpose — they are operational weightings,
not live data — so they are asserted as constants.
"""

from __future__ import annotations

import pytest

from app.services.race_control import workstreams


def _event(status: str = "upcoming", days_until: int | None = None) -> dict:
    return {"status": status, "days_until": days_until}


# ---------------------------------------------------------------------------
# focus_for_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (None, "Season review"),
        (_event("in_progress"), "Live session control"),
        (_event("upcoming", 10), "Race-week strategy lock"),
        (_event("upcoming", 0), "Race-week strategy lock"),
        (_event("upcoming", 11), "Pre-race simulation build"),
        (_event("upcoming", None), "Pre-race simulation build"),
        (_event("completed", 0), "Race-week strategy lock"),
    ],
    ids=[
        "no-event",
        "session-running",
        "race-week-boundary",
        "race-day",
        "outside-race-week",
        "no-countdown",
        "completed-with-countdown",
    ],
)
def test_focus_tracks_how_close_the_next_session_is(event, expected):
    assert workstreams.focus_for_event(event) == expected


# ---------------------------------------------------------------------------
# individual status helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (None, "Waiting"),
        (_event("in_progress"), "Live"),
        (_event("completed"), "Complete"),
        (_event("upcoming"), "Ready"),
    ],
    ids=["no-event", "running", "finished", "scheduled"],
)
def test_weekend_brief_status_follows_the_session_state(event, expected):
    assert workstreams._weekend_brief_status(event) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (None, "Idle"),
        (_event("in_progress"), "Live"),
        (_event("completed"), "Complete"),
        (_event("upcoming"), "Standby"),
    ],
    ids=["no-event", "running", "finished", "scheduled"],
)
def test_live_control_status_follows_the_session_state(event, expected):
    assert workstreams._live_control_status(event) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("predictions", "data_source", "expected"),
    [
        (None, {"mode": "telemetry"}, "Waiting"),
        ({}, {"mode": "telemetry"}, "Waiting"),
        ({"predictions": []}, {"mode": "telemetry"}, "Waiting"),
        ({"predictions": [{"code": "VER"}]}, {"mode": "telemetry"}, "Ready"),
        ({"predictions": [{"code": "VER"}]}, {"mode": "heuristic"}, "Build"),
        ({"predictions": [{"code": "VER"}]}, {}, "Build"),
    ],
    ids=[
        "no-prediction",
        "empty-payload",
        "empty-prediction-list",
        "telemetry-backed",
        "heuristic-only",
        "unknown-mode",
    ],
)
def test_race_model_status_distinguishes_telemetry_from_heuristic(predictions, data_source, expected):
    """ "Ready" is reserved for a telemetry-backed model — a heuristic one is still "Build"."""
    assert workstreams._race_model_status(predictions, data_source) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("competitors", "expected"),
    [
        ([], "Standby"),
        ([{"rank": 1, "threat": "Primary"}], "Monitor"),
        ([{"rank": 1, "threat": "Primary"}, {"rank": 2, "threat": "Monitor"}], "Monitor"),
        ([{"rank": 1, "threat": "Primary"}, {"rank": 2, "threat": "High"}], "Active"),
        ([{"rank": 2, "threat": "Primary"}], "Active"),
    ],
    ids=["no-standings", "leader-only", "distant-rivals", "close-rival", "rival-flagged-primary"],
)
def test_rival_watch_activates_only_for_a_threatening_non_leader(competitors, expected):
    """The leader's own "Primary" label must not trip the rival alarm."""
    assert workstreams._rival_watch_status(competitors) == expected


# ---------------------------------------------------------------------------
# build_workstreams
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_board_exposes_the_four_streams_with_stable_ids_and_priorities():
    board = workstreams.build_workstreams(None, None, {})

    assert [card["id"] for card in board] == ["weekend-brief", "race-model", "rival-watch", "live-control"]
    assert [card["priority"] for card in board] == ["P1", "P1", "P2", "P1"]
    assert [card["href"] for card in board] == [
        "/race-control",
        "/race-control/predictions",
        "/race-control/teams",
        "/race-control/live",
    ]


@pytest.mark.unit
def test_board_falls_back_to_idle_statuses_with_no_desk_state_at_all():
    board = workstreams.build_workstreams(None, None, {})

    assert [card["status"] for card in board] == ["Waiting", "Waiting", "Standby", "Idle"]


@pytest.mark.unit
def test_board_tolerates_a_null_strategy_context():
    """``build_overview`` can hand through a falsy context; that must not raise."""
    board = workstreams.build_workstreams(_event("in_progress"), None, None)

    assert [card["status"] for card in board] == ["Live", "Waiting", "Standby", "Live"]


@pytest.mark.unit
def test_board_reflects_a_live_telemetry_backed_session_with_a_close_rival():
    board = workstreams.build_workstreams(
        _event("in_progress"),
        {"predictions": [{"code": "VER"}]},
        {
            "data_source": {"mode": "telemetry"},
            "competitors": [{"rank": 1, "threat": "Primary"}, {"rank": 2, "threat": "High"}],
        },
    )

    assert [card["status"] for card in board] == ["Live", "Ready", "Active", "Live"]
