"""Tests for app.api.live.events — notable-event detection in the live feed.

Detection is a pure function of two successive polls, and it is the thing that
decides whether the LLM is asked for commentary at all. A false positive burns
a 30-second cooldown window on a non-event; a false negative means the safety
car never reaches the client. Both failure modes are silent in production, so
the boundaries — first snapshot, unchanged snapshot, unknown driver — are
asserted here rather than observed live.
"""

from __future__ import annotations

import pytest

from app.api.live.events import (
    INTERRUPTION_STATUSES,
    Snapshot,
    _by_driver,
    _detect_event,
    _pit_stop_event,
    _position_change_event,
    _safety_car_event,
)


def _rows(*pairs: tuple[str, int]) -> list[dict]:
    """Position rows from ``(driver, position)`` pairs, in the given order."""
    return [{"driver": driver, "position": position} for driver, position in pairs]


# ---------------------------------------------------------------------------
# Snapshot / _by_driver
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_snapshot_defaults_to_an_empty_poll():
    snapshot = Snapshot()

    assert snapshot.positions == []
    assert snapshot.session_status == ""
    assert snapshot.stints == {}


@pytest.mark.unit
def test_snapshot_defaults_are_not_shared_between_instances():
    """A mutable default shared across snapshots would leak one poll into the next."""
    first = Snapshot()
    first.positions.append({"driver": "VER", "position": 1})

    assert Snapshot().positions == []


@pytest.mark.unit
def test_by_driver_keeps_the_last_row_for_a_repeated_driver():
    indexed = _by_driver(_rows(("VER", 1), ("VER", 3)))

    assert indexed["VER"]["position"] == 3


# ---------------------------------------------------------------------------
# _safety_car_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("status", sorted(INTERRUPTION_STATUSES))
def test_safety_car_fires_for_every_interruption_status(status):
    event = _safety_car_event(Snapshot(), Snapshot(session_status=status))

    assert event == {"type": "safety_car", "status": status}


@pytest.mark.unit
def test_safety_car_matches_case_insensitively_but_reports_the_raw_status():
    event = _safety_car_event(Snapshot(), Snapshot(session_status="Safety Car"))

    # The client renders the feed's own casing; only the comparison is normalised.
    assert event == {"type": "safety_car", "status": "Safety Car"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("previous_status", "current_status"),
    [
        ("safety car", "safety car"),
        ("", ""),
        ("", "green"),
        ("safety car", ""),
    ],
    ids=["unchanged", "both-empty", "not-an-interruption", "cleared"],
)
def test_safety_car_stays_silent_without_a_new_interruption(previous_status, current_status):
    previous = Snapshot(session_status=previous_status)
    current = Snapshot(session_status=current_status)

    assert _safety_car_event(previous, current) is None


# ---------------------------------------------------------------------------
# _position_change_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_position_change_reports_the_move_and_the_new_top_five():
    previous = Snapshot(positions=_rows(("VER", 1), ("NOR", 2)))
    current = Snapshot(positions=_rows(("NOR", 1), ("VER", 2), ("LEC", 3), ("HAM", 4), ("RUS", 5), ("PIA", 6)))

    event = _position_change_event(previous, current)

    assert event["type"] == "position_change"
    assert (event["driver"], event["from_pos"], event["to_pos"]) == ("NOR", 2, 1)
    assert [row["driver"] for row in event["positions"]] == ["NOR", "VER", "LEC", "HAM", "RUS"]


@pytest.mark.unit
def test_position_change_ignores_a_driver_absent_from_the_previous_poll():
    """A driver appearing mid-session has no prior position to have changed from."""
    current = Snapshot(positions=_rows(("VER", 1)))

    assert _position_change_event(Snapshot(), current) is None


@pytest.mark.unit
def test_position_change_stays_silent_when_the_order_holds():
    order = _rows(("VER", 1), ("NOR", 2))

    assert _position_change_event(Snapshot(positions=order), Snapshot(positions=order)) is None


# ---------------------------------------------------------------------------
# _pit_stop_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pit_stop_converts_the_stint_number_into_a_stop_count():
    previous = Snapshot(stints={"1": 1})
    current = Snapshot(positions=_rows(("VER", 4)), stints={"1": 2})

    # Only the stint map is keyed by driver number; the position rows are keyed
    # by acronym, so the position lookup misses and falls back to "?".
    assert _pit_stop_event(previous, current) == {
        "type": "pit_stop",
        "driver": "1",
        "pit_count": 1,
        "position": "?",
    }


@pytest.mark.unit
def test_pit_stop_reports_the_position_when_the_driver_key_matches():
    current = Snapshot(positions=_rows(("VER", 4)), stints={"VER": 3})

    event = _pit_stop_event(Snapshot(stints={"VER": 2}), current)

    assert (event["pit_count"], event["position"]) == (2, 4)


@pytest.mark.unit
def test_pit_stop_treats_an_unseen_driver_as_being_on_their_first_stint():
    """Stint 1 for a driver missing from the previous poll is not a pit stop."""
    assert _pit_stop_event(Snapshot(), Snapshot(stints={"VER": 1})) is None


@pytest.mark.unit
def test_pit_stop_stays_silent_when_no_stint_count_rose():
    previous = Snapshot(stints={"VER": 2, "NOR": 3})
    current = Snapshot(stints={"VER": 2, "NOR": 3})

    assert _pit_stop_event(previous, current) is None


# ---------------------------------------------------------------------------
# _detect_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_detect_event_prefers_the_safety_car_over_a_simultaneous_position_change():
    previous = Snapshot(positions=_rows(("VER", 1), ("NOR", 2)), stints={"VER": 1})
    current = Snapshot(
        positions=_rows(("NOR", 1), ("VER", 2)),
        session_status="red flag",
        stints={"VER": 2},
    )

    assert _detect_event(previous, current)["type"] == "safety_car"


@pytest.mark.unit
def test_detect_event_prefers_a_position_change_over_a_pit_stop():
    previous = Snapshot(positions=_rows(("VER", 1), ("NOR", 2)), stints={"VER": 1})
    current = Snapshot(positions=_rows(("NOR", 1), ("VER", 2)), stints={"VER": 2})

    assert _detect_event(previous, current)["type"] == "position_change"


@pytest.mark.unit
def test_detect_event_falls_through_to_the_pit_stop_detector():
    previous = Snapshot(positions=_rows(("VER", 1)), stints={"VER": 1})
    current = Snapshot(positions=_rows(("VER", 1)), stints={"VER": 2})

    assert _detect_event(previous, current)["type"] == "pit_stop"


@pytest.mark.unit
def test_detect_event_returns_none_for_a_quiet_pair_of_polls():
    steady = Snapshot(positions=_rows(("VER", 1)), session_status="green", stints={"VER": 1})

    assert _detect_event(steady, steady) is None
