"""The R20 São Paulo roster, rebuilt from the data that once made it 23 drivers.

The snapshot computed on 1 Nov listed Racing Bulls three times (with Tsunoda),
Haas with Ocon and Bearman, and no Hirakawa: both entry-list sources had gone
dark, so the grid fell back to the championship table. These tests run the
real pieces end to end on captured data: the OpenF1 entry-list loader against
the Mexico City responses, f1db's race starts through R18, the championship
table after R18, and the grid resolver.

* Read before the São Paulo weekend, the roster is Mexico City's race lineup:
  22 cars, two per team, Hirakawa in the Haas with his seat marked TBC.
* Tsunoda (R12–R14, standing in while Hadjar was injured) never comes back,
  through either path.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from app.data import session_entries
from app.data.driver_availability import WeekendAvailability
from app.data.season_seats import season_seats, team_key
from app.data.session_entries import UNAVAILABLE, load_weekend_entry_list
from app.data.weekend_grid import (
    SOURCE_CHAMPIONSHIP,
    SOURCE_PREVIOUS_ENTRY_LIST,
    EntryLists,
    resolve_grid,
    roster_violation,
)
from app.utils.ttl_cache import TtlCache
from tests.openf1_support import serve
from tests.roster_support import (
    AFTER_MEXICO,
    MEXICO,
    championship_2026,
    drivers_route,
    install_f1db_2026,
    mexico_drivers,
    weekend,
)

pytestmark = pytest.mark.integration

MEXICO_CITY = "Mexico City Grand Prix"


@pytest.fixture
def season_2026(tmp_path, monkeypatch):
    install_f1db_2026(tmp_path, monkeypatch)
    monkeypatch.setattr(session_entries, "weekend_sessions", lambda client, year, rnd: weekend(MEXICO))
    monkeypatch.setattr(session_entries, "_utc_now", lambda: AFTER_MEXICO)
    monkeypatch.setattr(session_entries, "_cache", TtlCache())
    serve(monkeypatch, session_entries, {"drivers": drivers_route(mexico_drivers())})


def r20_roster(previous):
    """The São Paulo roster as it is resolved before the weekend's first session."""
    return resolve_grid(
        [],
        championship_2026(),
        EntryLists(current=UNAVAILABLE, previous=previous, seats=season_seats(2026, 20)),
        WeekendAvailability(),
    )


def mexico_city_lineup():
    return replace(load_weekend_entry_list(2026, 19), event=MEXICO_CITY)


def cars_per_team(grid) -> Counter:
    return Counter(team_key(driver["team"]) for driver in grid.drivers)


def driver(grid, code: str) -> dict:
    return next(row for row in grid.drivers if row["driver_code"] == code)


class TestCarriedOverFromMexicoCity:
    def test_the_r20_roster_is_22_cars_with_at_most_two_per_team(self, season_2026):
        grid = r20_roster(mexico_city_lineup())

        assert len(grid.drivers) == 22
        assert max(cars_per_team(grid).values()) == 2
        assert len(cars_per_team(grid)) == 11
        assert roster_violation(grid.drivers) is None
        assert grid.data_sources == (SOURCE_PREVIOUS_ENTRY_LIST,)

    def test_hirakawa_holds_the_haas_seat_and_it_is_marked_tbc(self, season_2026):
        grid = r20_roster(mexico_city_lineup())

        hirakawa = driver(grid, "HIR")
        assert hirakawa["team"] == "Haas F1 Team"
        assert hirakawa["seat_tbc"] is True
        assert "in place of Esteban Ocon" in hirakawa["seat_tbc_reason"]
        assert "at the Mexico City Grand Prix" in hirakawa["seat_tbc_reason"]
        assert "OCO" not in {row["driver_code"] for row in grid.drivers}

    def test_the_haas_seat_is_the_only_one_in_doubt(self, season_2026):
        grid = r20_roster(mexico_city_lineup())

        assert [row["driver_code"] for row in grid.drivers if row["seat_tbc"]] == ["HIR"]

    def test_tsunoda_is_not_predicted(self, season_2026):
        grid = r20_roster(mexico_city_lineup())

        assert "TSU" not in {row["driver_code"] for row in grid.drivers}
        assert {driver(grid, code)["team"] for code in ("LAW", "LIN")} == {"Racing Bulls"}


class TestChampionshipFallback:
    """OpenF1 unreachable: the championship table after R18, cut to the cars' holders."""

    def test_the_fallback_is_22_cars_with_at_most_two_per_team(self, season_2026):
        grid = r20_roster(UNAVAILABLE)

        assert len(grid.drivers) == 22
        assert max(cars_per_team(grid).values()) == 2
        assert roster_violation(grid.drivers) is None
        assert grid.data_sources == (SOURCE_CHAMPIONSHIP,)

    def test_the_championship_table_alone_still_lists_tsunoda(self, season_2026):
        """The bug's raw material: 23 drivers, three of them Racing Bulls."""
        table = championship_2026()

        assert len(table) == 23
        assert sum(row["team"] == "Racing Bulls" for row in table) == 3

    def test_tsunoda_is_dropped_once_hadjar_is_back(self, season_2026):
        assert "TSU" not in {row["driver_code"] for row in r20_roster(UNAVAILABLE).drivers}

    @pytest.mark.parametrize("round_num", [16, 17, 18, 19, 20])
    def test_tsunoda_never_returns_after_hadjars_comeback(self, season_2026, round_num):
        grid = resolve_grid(
            [], championship_2026(), EntryLists(seats=season_seats(2026, round_num)), WeekendAvailability()
        )

        assert "TSU" not in {row["driver_code"] for row in grid.drivers}
        assert roster_violation(grid.drivers) is None
