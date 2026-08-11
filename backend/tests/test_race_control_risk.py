"""Tests for app.services.race_control.risk — the pit-wall risk register.

The risk cards are the most quotable thing on the command center: a strategist
reads "High — elevated rain risk" and primes a wet branch. So the thing worth
guarding is that every card is *earned* by real state, and that the absence of
state degrades into a card that says so.

Two behaviours matter here:

* an offline weather feed produces a card explicitly labelled "Weather feed
  offline" rather than a fabricated dry/wet grading, and
* no rival card at all is emitted when the standings snapshot has nobody
  trailing the leader — an empty panel beats an invented rival.
"""

from __future__ import annotations

import pytest

from app.services.race_control import risk


def _event(*, is_sprint: bool = False, circuit_type: str | None = None) -> dict:
    return {
        "is_sprint": is_sprint,
        "circuit": {"circuit_type": circuit_type} if circuit_type else None,
    }


# ---------------------------------------------------------------------------
# _weather_risk
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "weather",
    [None, {}, {"rain_risk": None}, {"rain_risk": "40%"}],
    ids=["no-block", "empty-block", "null-rain", "non-numeric-rain"],
)
def test_weather_risk_declares_the_feed_offline_when_no_rain_number_exists(weather):
    """The offline card must be distinguishable from a graded one, not a fake Low."""
    card = risk._weather_risk(weather)

    assert card == {
        "level": "Medium",
        "title": "Weather feed offline",
        "detail": "Live forecast unavailable — confirm dry/wet branches manually before lock.",
    }
    assert "%" not in card["detail"], "an offline card must never quote a rain probability"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rain", "level", "title"),
    [
        (95, "High", "Elevated rain risk"),
        (40, "High", "Elevated rain risk"),
        (39.6, "High", "Elevated rain risk"),
        (39.4, "Medium", "Mixed conditions possible"),
        (20, "Medium", "Mixed conditions possible"),
        (19, "Low", "Dry conditions expected"),
        (0, "Low", "Dry conditions expected"),
    ],
    ids=[
        "downpour",
        "at-high-cutoff",
        "rounds-up-to-high",
        "rounds-down-to-medium",
        "at-moderate-cutoff",
        "below",
        "dry",
    ],
)
def test_weather_risk_grades_the_live_rain_probability(rain, level, title):
    card = risk._weather_risk({"rain_risk": rain})

    assert (card["level"], card["title"]) == (level, title)
    # Every graded card quotes the (rounded) figure it was graded from, so the
    # number on screen can be traced back to the forecast.
    assert f"{round(rain)}% rain probability" in card["detail"]


# ---------------------------------------------------------------------------
# _rival_risk
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "competitors",
    [None, [], [{"rank": 1, "team": "McLaren", "gap_to_leader": 0}]],
    ids=["no-standings", "empty-standings", "leader-only"],
)
def test_rival_risk_is_omitted_when_nobody_trails_the_leader(competitors):
    assert risk._rival_risk(competitors) is None


@pytest.mark.unit
def test_rival_risk_is_omitted_when_the_gap_is_not_a_number():
    """A malformed standings row must not produce a card quoting a bogus gap."""
    assert risk._rival_risk([{"rank": 2, "team": "Ferrari", "gap_to_leader": None}]) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("gap", "level"),
    [(0, "High"), (25, "High"), (26, "Medium"), (60, "Medium"), (61, "Low"), (300, "Low")],
    ids=["dead-heat", "at-high-cutoff", "just-over", "at-moderate-cutoff", "just-over-moderate", "runaway"],
)
def test_rival_risk_grades_the_real_constructor_gap(gap, level):
    card = risk._rival_risk([{"rank": 2, "team": "Ferrari", "gap_to_leader": gap}])

    assert card["level"] == level
    assert card["title"] == "Rival offset plans"
    assert f"{gap} pts" in card["detail"]
    assert "Ferrari" in card["detail"]


@pytest.mark.unit
def test_rival_risk_picks_the_closest_rival_not_the_first_listed():
    card = risk._rival_risk(
        [
            {"rank": 1, "team": "McLaren", "gap_to_leader": 0},
            {"rank": 2, "team": "Ferrari", "gap_to_leader": 80},
            {"rank": 3, "team": "Red Bull", "gap_to_leader": 12},
        ]
    )

    assert card["level"] == "High", "the 12-point car is the one to plan against"
    assert "Red Bull" in card["detail"]


@pytest.mark.unit
def test_rival_risk_names_a_placeholder_when_the_row_has_no_team():
    card = risk._rival_risk([{"rank": 2, "gap_to_leader": 5}])

    assert "the nearest rival" in card["detail"]


# ---------------------------------------------------------------------------
# build_risk_register
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_is_empty_without_an_event():
    assert risk.build_risk_register(None, {"rain_risk": 90}, [{"rank": 2, "gap_to_leader": 1}]) == []


@pytest.mark.unit
def test_register_adds_the_sprint_compression_risk_for_sprint_weekends():
    register = risk.build_risk_register(_event(is_sprint=True), None, [])

    assert [card["title"] for card in register] == ["Sprint format compression", "Weather feed offline"]


@pytest.mark.unit
def test_register_adds_safety_car_exposure_only_for_street_circuits():
    street = risk.build_risk_register(_event(circuit_type="Street"), None, [])
    permanent = risk.build_risk_register(_event(circuit_type="Purpose-built"), None, [])

    assert "Safety car exposure" in [card["title"] for card in street]
    assert "Safety car exposure" not in [card["title"] for card in permanent]


@pytest.mark.unit
def test_register_skips_the_street_risk_when_the_event_has_no_circuit_metadata():
    register = risk.build_risk_register(_event(circuit_type=None), None, [])

    assert [card["title"] for card in register] == ["Weather feed offline"]


@pytest.mark.unit
def test_register_stacks_every_earned_card_in_reading_order():
    register = risk.build_risk_register(
        _event(is_sprint=True, circuit_type="Street"),
        {"rain_risk": 55},
        [{"rank": 1, "team": "McLaren", "gap_to_leader": 0}, {"rank": 2, "team": "Ferrari", "gap_to_leader": 10}],
    )

    assert [card["title"] for card in register] == [
        "Sprint format compression",
        "Safety car exposure",
        "Elevated rain risk",
        "Rival offset plans",
    ]
    assert [card["level"] for card in register] == ["High", "High", "High", "High"]
