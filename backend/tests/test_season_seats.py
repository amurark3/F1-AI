"""Tests for app.data.season_seats — who holds each team's cars, and who is standing in.

Runs on the real 2026 race starts through round 18 (see ``roster_support``), so
the SQL is exercised as well as the rules. The season holds both cases that
broke the R20 roster:

* **R12–R14:** Hadjar was injured. Lawson stepped up to Red Bull and Tsunoda
  took Lawson's Racing Bulls car. Hadjar returned at R15, and the championship
  table still lists Tsunoda for Racing Bulls.
* **R19:** Hirakawa raced Ocon's Haas. That round is not in this f1db release,
  so the lineup comes from OpenF1's Mexico City race list.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.data.season_seats import (
    SeasonSeat,
    current_holders,
    regulars,
    season_seats,
    stand_ins,
    team_key,
)
from tests.roster_support import install_f1db_2026

pytestmark = pytest.mark.unit


@pytest.fixture
def season_2026(tmp_path, monkeypatch):
    return install_f1db_2026(tmp_path, monkeypatch)


def seat(seats, code: str, team: str) -> SeasonSeat:
    return next(item for item in seats if item.code == code and item.team == team)


class TestSeasonSeats:
    def test_counts_each_drivers_starts_for_each_team(self, season_2026):
        seats = season_seats(2026, 20)

        assert seat(seats, "LAW", "Racing Bulls") == SeasonSeat(
            code="LAW", name="Liam Lawson", team="Racing Bulls", starts=15, last_round=18
        )
        assert seat(seats, "LAW", "Red Bull") == SeasonSeat(
            code="LAW", name="Liam Lawson", team="Red Bull", starts=3, last_round=14
        )
        assert seat(seats, "TSU", "Racing Bulls").starts == 3
        assert seat(seats, "TSU", "Racing Bulls").last_round == 14

    def test_only_rounds_before_the_predicted_one_count(self, season_2026):
        """A recompute of a past race must see the season as it stood then."""
        seats = season_seats(2026, 13)

        assert seat(seats, "TSU", "Racing Bulls") == SeasonSeat(
            code="TSU", name="Yuki Tsunoda", team="Racing Bulls", starts=1, last_round=12
        )
        assert seat(seats, "HAD", "Red Bull").last_round == 11
        assert max(item.last_round for item in seats) == 12

    def test_a_season_with_no_starts_has_no_seats(self, season_2026):
        assert season_seats(2026, 1) == ()
        assert season_seats(2027, 5) == ()


class TestCurrentHolders:
    def test_after_hadjar_returned_tsunoda_holds_no_car(self, season_2026):
        holders = current_holders(season_seats(2026, 20))

        assert "TSU" not in holders
        assert {"VER", "HAD", "LAW", "LIN", "OCO", "BEA"} <= holders
        assert len(holders) == 22

    def test_while_hadjar_was_out_the_stand_ins_held_the_cars(self, season_2026):
        holders = current_holders(season_seats(2026, 14))

        assert {"VER", "LAW", "LIN", "TSU"} <= holders
        assert "HAD" not in holders

    def test_no_team_holds_more_than_two_cars(self, season_2026):
        seats = season_seats(2026, 20)
        holders = current_holders(seats)
        teams = Counter(team_key(item.team) for item in seats if item.code in holders and item.last_round == 18)

        assert max(teams.values()) == 2


class TestRegulars:
    def test_a_teams_regulars_are_its_two_most_used_drivers(self, season_2026):
        seats = season_seats(2026, 20)

        assert [item.code for item in regulars(seats, "Haas F1 Team")] == ["BEA", "OCO"]
        assert [item.code for item in regulars(seats, "Red Bull Racing")] == ["VER", "HAD"]
        assert [item.code for item in regulars(seats, "Racing Bulls")] == ["LIN", "LAW"]

    def test_a_tie_on_starts_goes_to_the_more_recent_driver(self):
        seats = (
            SeasonSeat(code="LAW", name="Liam Lawson", team="Red Bull", starts=2, last_round=2),
            SeasonSeat(code="TSU", name="Yuki Tsunoda", team="Red Bull", starts=2, last_round=4),
            SeasonSeat(code="VER", name="Max Verstappen", team="Red Bull", starts=4, last_round=4),
        )

        assert [item.code for item in regulars(seats, "Red Bull")] == ["VER", "TSU"]

    def test_a_team_with_no_starts_has_no_regulars(self, season_2026):
        assert regulars(season_seats(2026, 20), "Andretti") == ()


class TestStandIns:
    def test_hirakawa_stood_in_for_ocon(self, season_2026):
        lineup = [
            ("BEA", "Haas F1 Team"),
            ("HIR", "Haas F1 Team"),
            ("VER", "Red Bull Racing"),
            ("HAD", "Red Bull Racing"),
        ]

        replaced = stand_ins(lineup, season_seats(2026, 20))

        assert set(replaced) == {"HIR"}
        assert replaced["HIR"].name == "Esteban Ocon"

    def test_a_chain_of_stand_ins_is_followed_seat_by_seat(self, season_2026):
        """R12's lineup, read before R13: each car's driver against its team's regulars."""
        lineup = [
            ("VER", "Red Bull Racing"),
            ("LAW", "Red Bull Racing"),
            ("LIN", "Racing Bulls"),
            ("TSU", "Racing Bulls"),
        ]

        replaced = stand_ins(lineup, season_seats(2026, 13))

        assert {code: item.code for code, item in replaced.items()} == {"LAW": "HAD", "TSU": "LAW"}

    def test_a_full_lineup_of_regulars_has_no_stand_ins(self, season_2026):
        lineup = [("BEA", "Haas"), ("OCO", "Haas"), ("LIN", "Racing Bulls"), ("LAW", "Racing Bulls")]

        assert stand_ins(lineup, season_seats(2026, 20)) == {}

    def test_a_team_with_no_history_cannot_have_a_stand_in(self):
        assert stand_ins([("DUN", "Red Bull")], ()) == {}

    def test_a_third_driver_beside_both_regulars_replaced_nobody(self, season_2026):
        """That is a broken lineup, which the grid's own check rejects; it is not a substitution."""
        lineup = [("BEA", "Haas"), ("OCO", "Haas"), ("HIR", "Haas")]

        assert stand_ins(lineup, season_seats(2026, 20)) == {}


class TestTeamKey:
    @pytest.mark.parametrize(
        ("feed_name", "f1db_name"),
        [("Haas F1 Team", "Haas"), ("Red Bull Racing", "Red Bull"), ("Racing Bulls", "Racing Bulls")],
    )
    def test_each_feeds_spelling_is_one_team(self, feed_name, f1db_name):
        assert team_key(feed_name) == team_key(f1db_name)

    def test_red_bull_and_racing_bulls_stay_apart(self):
        assert team_key("Red Bull Racing") != team_key("Racing Bulls")

    def test_no_name_is_no_team(self):
        assert team_key("") == ""
