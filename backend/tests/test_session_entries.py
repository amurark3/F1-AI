"""Tests for app.data.session_entries — who is actually entered for a weekend.

The entry list decides which drivers a prediction scores, so the risks are all
about believing the right list:

* **Only a session that has run counts.** OpenF1 fills in a weekend's drivers
  days ahead: on 2 Nov every São Paulo session already listed Ocon, the day
  after Hirakawa raced his Haas in Mexico City.
* **FP1 is never the lineup.** Nine Mexico City FP1 cars had a rookie in a race
  driver's seat (Tsolov in Lawson's Racing Bulls among them).
* **The newest session wins**, and a car's blank team (Hirakawa's, in the
  Mexico City race) is filled from the weekend's other sessions.
* **"Not yet known" is not cached like an answer**, so the real list is picked
  up minutes after the cars run, not hours.

OpenF1 is faked over HTTP with the real Mexico City and São Paulo responses.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.data import session_entries as module
from app.data.session_entries import (
    UNAVAILABLE,
    EntryListDriver,
    WeekendEntryList,
    display_name,
    load_weekend_entry_list,
)
from app.utils.ttl_cache import TtlCache
from tests.openf1_support import serve
from tests.roster_support import (
    AFTER_MEXICO,
    MEXICO,
    MEXICO_FP1,
    MEXICO_QUALIFYING,
    MEXICO_RACE,
    SAO_PAULO,
    SAO_PAULO_FP1,
    drivers_route,
    load,
    mexico_drivers,
    requested_sessions,
    weekend,
)

pytestmark = pytest.mark.unit

AFTER_FP1 = datetime(2026, 10, 30, 20, 0, tzinfo=UTC)
AFTER_QUALIFYING = datetime(2026, 10, 31, 23, 0, tzinfo=UTC)


@pytest.fixture
def openf1(monkeypatch):
    """OpenF1 serving the Mexico City weekend, read the morning after the race."""
    state = {
        "now": AFTER_MEXICO,
        "clock": 1000.0,
        "sessions": weekend(MEXICO),
        "drivers": mexico_drivers(),
    }

    def _sessions(client, year, round_num):
        if isinstance(state["sessions"], BaseException):
            raise state["sessions"]
        return state["sessions"]

    monkeypatch.setattr(module, "weekend_sessions", _sessions)
    monkeypatch.setattr(module, "_utc_now", lambda: state["now"])
    monkeypatch.setattr(module, "_cache", TtlCache(clock=lambda: state["clock"]))
    state["fake"] = serve(monkeypatch, module, {"drivers": drivers_route(state["drivers"])})
    return state


def entries_by_code(entry_list: WeekendEntryList) -> dict[str, EntryListDriver]:
    return entry_list.by_code()


class TestWhichSessionIsRead:
    def test_after_the_race_the_race_list_is_the_entry_list(self, openf1):
        entry_list = load_weekend_entry_list(2026, 19)

        assert entry_list.session == "R"
        assert len(entry_list.entries) == 22
        assert "HIR" in entry_list.codes
        assert "OCO" not in entry_list.codes
        assert requested_sessions(openf1["fake"])[0] == MEXICO_RACE

    def test_the_newest_session_that_has_run_wins(self, openf1):
        openf1["now"] = AFTER_QUALIFYING

        entry_list = load_weekend_entry_list(2026, 19)

        assert entry_list.session == "Q"
        assert MEXICO_RACE not in requested_sessions(openf1["fake"]), "the race had not run"

    def test_fp1_is_never_the_entry_list(self, openf1):
        """After FP1 alone the lineup is unknown, not Tsolov in Lawson's car."""
        openf1["now"] = AFTER_FP1

        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE
        assert requested_sessions(openf1["fake"]) == []

    def test_sessions_that_have_not_started_are_never_read(self, openf1):
        """São Paulo's lists already named Ocon on 2 Nov; that was OpenF1's guess."""
        openf1["sessions"] = weekend(SAO_PAULO)
        openf1["drivers"][SAO_PAULO_FP1] = load(SAO_PAULO / "openf1_drivers_practice1.json")

        assert load_weekend_entry_list(2026, 20) is UNAVAILABLE
        assert requested_sessions(openf1["fake"]) == []

    def test_a_session_with_no_drivers_falls_back_to_the_one_before(self, openf1):
        del openf1["drivers"][MEXICO_RACE]

        assert load_weekend_entry_list(2026, 19).session == "Q"


class TestTeams:
    def test_a_blank_team_is_filled_from_the_same_car_in_another_session(self, openf1):
        hirakawa = entries_by_code(load_weekend_entry_list(2026, 19))["HIR"]

        assert hirakawa == EntryListDriver(code="HIR", name="Ryo Hirakawa", team="Haas F1 Team", number=50)
        assert requested_sessions(openf1["fake"]) == [MEXICO_RACE, MEXICO_QUALIFYING]

    def test_the_search_for_a_team_stops_once_every_car_has_one(self, openf1):
        load_weekend_entry_list(2026, 19)

        assert MEXICO_FP1 not in requested_sessions(openf1["fake"])

    def test_a_team_no_session_names_stays_blank(self, openf1):
        del openf1["drivers"][MEXICO_QUALIFYING]
        del openf1["drivers"][MEXICO_FP1]

        assert entries_by_code(load_weekend_entry_list(2026, 19))["HIR"].team == ""

    def test_every_other_car_keeps_its_own_team(self, openf1):
        entries = entries_by_code(load_weekend_entry_list(2026, 19))

        assert entries["BEA"].team == "Haas F1 Team"
        assert entries["LAW"].team == "Racing Bulls"
        assert entries["VER"].team == "Red Bull Racing"


class TestUnavailable:
    def test_a_weekend_openf1_does_not_know_is_unavailable(self, openf1):
        openf1["sessions"] = ()

        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE

    def test_openf1_closed_for_a_live_session_is_unavailable(self, openf1):
        openf1["drivers"][MEXICO_RACE] = httpx.Response(401, json={"detail": "live"})

        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE

    def test_a_calendar_that_will_not_load_is_unavailable(self, openf1):
        openf1["sessions"] = ValueError("no such season")

        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE


class TestCaching:
    def test_a_resolved_list_is_kept_for_half_an_hour(self, openf1):
        first = load_weekend_entry_list(2026, 19)
        openf1["clock"] += module.ENTRY_LIST_TTL_SECONDS - 1

        assert load_weekend_entry_list(2026, 19) is first
        assert len(openf1["fake"].requests) == 2

    def test_a_resolved_list_is_read_again_once_it_expires(self, openf1):
        load_weekend_entry_list(2026, 19)
        openf1["clock"] += module.ENTRY_LIST_TTL_SECONDS

        load_weekend_entry_list(2026, 19)

        assert len(openf1["fake"].requests) == 4

    def test_an_unavailable_list_is_retried_after_five_minutes(self, openf1):
        openf1["now"] = AFTER_FP1
        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE

        openf1["now"] = AFTER_MEXICO
        assert load_weekend_entry_list(2026, 19) is UNAVAILABLE, "still inside the retry window"

        openf1["clock"] += module.ENTRY_LIST_RETRY_SECONDS
        assert load_weekend_entry_list(2026, 19).session == "R"

    def test_each_round_is_cached_on_its_own(self, openf1):
        load_weekend_entry_list(2026, 19)
        openf1["sessions"] = ()

        assert load_weekend_entry_list(2026, 18) is UNAVAILABLE


class TestDisplayName:
    @pytest.mark.parametrize(
        ("full_name", "expected"),
        [("Lando NORRIS", "Lando Norris"), ("Ryo HIRAKAWA", "Ryo Hirakawa"), ("Kimi Antonelli", "Kimi Antonelli")],
    )
    def test_openf1s_capital_surnames_are_not_kept(self, full_name, expected):
        assert display_name(full_name) == expected

    def test_the_driver_number_travels_with_the_entry(self, openf1):
        assert entries_by_code(load_weekend_entry_list(2026, 19))["NOR"].number == 1


def test_sessions_are_judged_against_the_utc_clock():
    """OpenF1 session times are UTC; a naive clock could not be compared with them."""
    assert module._utc_now().tzinfo is UTC
