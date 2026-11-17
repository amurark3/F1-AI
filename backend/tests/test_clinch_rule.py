"""Tests for what the leader must do at one event to settle a title (title_rule's event rule)."""

from __future__ import annotations

import pytest

from app.data.standings_table import Standing
from app.data.title_rule import (
    CONSTRUCTORS,
    DRIVERS,
    Need,
    Remaining,
    can_settle_at,
    decided,
    earliest,
    needs_at,
    total,
)

pytestmark = pytest.mark.unit


def row(key: str, points: float, places: tuple[int, int, int] = (0, 0, 0), team: str = "") -> Standing:
    wins, seconds, thirds = places
    finishes = (1,) * wins + (2,) * seconds + (3,) * thirds
    return Standing(key=key, name=key, team=team or key, points=points, finishes=finishes)


def margins(rows, at, after, scoring=DRIVERS) -> list[tuple[str, float, bool]]:
    return [(n.rival.key, n.margin, n.countback) for n in needs_at(rows, Remaining(*at), Remaining(*after), scoring)]


def test_mercedes_settle_at_sao_paulo_by_outscoring_ferrari_by_3():
    rows = (row("Mercedes", 630, (12, 7, 5)), row("Ferrari", 504, (2, 6, 5)), row("Red Bull", 382, (3, 4, 6)))

    needs = needs_at(rows, Remaining(1, 0), Remaining(3, 0), CONSTRUCTORS)

    assert needs == (Need(rows[1], 3, False),)
    assert can_settle_at(rows, Remaining(1, 0), Remaining(3, 0), CONSTRUCTORS)


def test_antonelli_settles_at_mexico_city_unless_russell_or_hamilton_outscore_him():
    rows = (
        row("ANT", 365, (9, 3, 3)),
        row("RUS", 242, (3, 4, 1)),
        row("HAM", 241, (1, 2, 3)),
        row("VER", 236, (2, 4, 4)),
    )

    assert margins(rows, (1, 0), (4, 0)) == [("RUS", -23, False), ("HAM", -24, False)]


def test_every_rival_still_alive_gets_a_need_binding_first():
    rows = (
        row("ANT", 340, (8, 3, 3)),
        row("RUS", 238, (3, 4, 1)),
        row("HAM", 229, (1, 2, 3)),
        row("VER", 221, (2, 4, 3)),
        row("LEC", 215, (1, 2, 2)),
        row("NOR", 201, (2, 1, 2)),
        row("PIA", 152),
    )

    assert margins(rows, (1, 0), (5, 0)) == [
        ("RUS", 24, True),
        ("HAM", 14, False),
        ("VER", 7, True),
        ("LEC", 0, False),
        ("NOR", -14, False),
    ]
    assert can_settle_at(rows, Remaining(1, 0), Remaining(5, 0), DRIVERS)


def test_a_sprint_weekend_counts_both_sessions():
    rows = (row("NOR", 390, (7, 8, 2)), row("PIA", 366, (7, 3, 4)), row("VER", 366, (6, 5, 2)))

    assert margins(rows, (1, 1), (1, 0)) == [("PIA", 2, True), ("VER", 2, True)]
    assert can_settle_at(rows, Remaining(1, 1), Remaining(1, 0), DRIVERS)


def test_the_last_round_settles_on_the_day():
    rows = (row("NOR", 408, (7, 8, 2)), row("VER", 396, (7, 5, 2)), row("PIA", 392, (7, 4, 4)))

    assert margins(rows, (1, 0), (0, 0)) == [("VER", -11, True), ("PIA", -15, True)]


def test_a_rival_who_wins_any_count_back_needs_one_point_more():
    rows = (row("Norris", 400), row("Piastri", 342))

    assert margins(rows, (1, 1), (2, 1)) == [("Piastri", 1, False)]


def test_a_lead_a_perfect_weekend_cannot_protect_is_not_possible():
    rows = (row("Norris", 400), row("Piastri", 380))

    assert margins(rows, (1, 1), (2, 1)) == [("Piastri", 39, False)]
    assert not can_settle_at(rows, Remaining(1, 1), Remaining(2, 1), DRIVERS)


def test_the_earliest_event_the_leader_can_clinch_at():
    rows = (
        row("ANT", 320),
        row("RUS", 236),
        row("HAM", 214),
        row("LEC", 191),
        row("NOR", 188),
        row("VER", 188),
    )
    upcoming = (Remaining(1, 1), *[Remaining(1, 0)] * 6)

    assert earliest(rows, upcoming, DRIVERS) == 1
    assert earliest(rows, (), DRIVERS) is None


def test_decided_titles_have_no_needs():
    rows = (row("ANT", 380), row("VER", 261, (3, 4, 4)))

    assert decided(rows, Remaining(4, 0), DRIVERS)
    assert needs_at(rows, Remaining(1, 0), Remaining(3, 0), DRIVERS) == ()
    assert not decided(rows[:1], Remaining(4, 0), DRIVERS)
    assert total([Remaining(1, 1), Remaining(2, 0)]) == Remaining(3, 1)
