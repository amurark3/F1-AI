"""The last current-table readers serve the computed table too: the chat tools, the drivers list and compare.

The morning after Mexico 2026 f1db still held round 18, so a reader of f1db's
table would have had the assistant quote Antonelli on 365. Each reader below is
read on that morning's data (``tests/standings_support.mexico_feeds``) and must
serve the table after round 19 (ANT 380, VER 261, Red Bull 382, McLaren 365),
marked provisional.

The chat tools also state each title's state from the shared rule
(``title_rule`` through ``table_reach``), so the assistant never works out
"can still catch" itself: four Grands Prix are left (100 points for a driver,
172 for a team), so the drivers' title is decided for Antonelli and the
constructors' title is open between Mercedes (630) and Ferrari (504).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.api.compare import _build_comparison_sync
from app.api.tools.standings import get_constructor_standings, get_driver_standings
from app.services.race_control import table_reach
from app.services.race_control_battles import build_driver_battle
from app.services.race_control_common import get_driver_options
from tests.standings_support import AFTER_ROUND_19, BASE_AND_ROUND_19, SEASON, Feeds, mexico_feeds

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    monkeypatch.setattr(table_reach, "season_events", lambda _year: SEASON)
    yield from mexico_feeds(tmp_path, monkeypatch)


def freshness(payload: dict) -> dict:
    return {"as_of_round": payload["as_of_round"], "provisional": payload["provisional"]}


# --- the chat tools -------------------------------------------------------------------


def test_the_chat_driver_table_is_the_one_after_round_19_marked_provisional(feeds):
    answer = get_driver_standings.invoke({"year": 2026})

    assert "| 1 | ANT | Mercedes | 380 |" in answer
    assert "| 2 | VER | Red Bull | 261 |" in answer
    assert "365" not in answer, "Antonelli's round-18 total must not reach the assistant"
    assert (
        "After round 19 · provisional: f1db's table through round 18 plus OpenF1's results for round 19. "
        "f1db has not confirmed round 19 yet, so post-race penalties can still change it."
    ) in answer


def test_the_chat_driver_table_says_the_title_is_decided_for_antonelli(feeds):
    answer = get_driver_standings.invoke({"year": 2026})

    assert answer.splitlines()[-1] == (
        "**Drivers' title:** decided for Kimi Antonelli (ANT). Leader: 380 points, 119 ahead of Max Verstappen (VER), "
        "with at most 100 points left for one entrant (4 Grands Prix, 0 sprints): no rival can still finish ahead."
    )


def test_the_chat_constructor_table_is_the_one_after_round_19_marked_provisional(feeds):
    answer = get_constructor_standings.invoke({"year": 2026})

    assert "| 1 | Mercedes | 630 |" in answer
    assert "| 3 | Red Bull | 382 |" in answer
    assert "| 4 | McLaren | 365 |" in answer
    assert "After round 19 · provisional: " in answer


def test_the_chat_constructor_table_says_the_title_is_open_between_mercedes_and_ferrari(feeds):
    answer = get_constructor_standings.invoke({"year": 2026})

    assert answer.splitlines()[-1] == (
        "**Constructors' title:** still open. Leader: Mercedes, 630 points, "
        "with at most 172 points left for one entrant (4 Grands Prix, 0 sprints). "
        "Only these can still finish ahead of Mercedes: Ferrari (504 points, 126 behind)."
    )


def test_without_a_calendar_the_chat_tool_states_no_title_claim(feeds, monkeypatch):
    def unreadable(_year: int) -> list[dict]:
        raise RuntimeError("schedule unavailable")

    monkeypatch.setattr(table_reach, "season_events", unreadable)

    answer = get_driver_standings.invoke({"year": 2026})

    assert "| 1 | ANT | Mercedes | 380 |" in answer
    assert answer.splitlines()[-1] == (
        "**Drivers' title:** not stated. The season calendar could not be read, so the points still on offer "
        "are unknown: do not say whether the title is decided."
    )


def test_once_f1db_holds_the_round_the_chat_tool_says_confirmed(feeds):
    feeds.weekends.clear()

    answer = get_driver_standings.invoke({"year": 2026})

    assert "| 1 | ANT | Mercedes | 365 |" in answer
    assert "After round 18 · confirmed: f1db's published table." in answer


# --- /api/race-control/drivers/{year} -----------------------------------------------


def test_the_drivers_list_is_the_table_after_round_19(feeds):
    payload = get_driver_options(2026)

    assert payload["error"] is None
    assert payload["source"] == "computed-standings"
    assert payload["drivers"][:2] == [
        {"code": "ANT", "name": "Kimi Antonelli", "team": "Mercedes", "position": 1, "points": 380, "wins": 9},
        {"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 2, "points": 261, "wins": 3},
    ]
    assert freshness(payload) == AFTER_ROUND_19
    assert payload["sources"][:2] == BASE_AND_ROUND_19


# --- compare and the driver battle ----------------------------------------------------


def test_compare_reads_antonelli_380_and_verstappen_261_after_round_19(feeds):
    result = _build_comparison_sync(2026, "ANT", "VER")

    assert (result["driver1"]["points"], result["driver1"]["position"]) == (380, 1)
    assert (result["driver2"]["points"], result["driver2"]["position"]) == (261, 2)
    assert freshness(result) == AFTER_ROUND_19
    assert result["sources"][:2] == BASE_AND_ROUND_19


def test_the_driver_battle_reads_the_table_after_round_19(feeds):
    result = build_driver_battle(2026, "ANT", "VER")

    points = next(fact for fact in result["facts"] if fact["key"] == "points")
    assert points["values"] == {"ANT": "380", "VER": "261"}
    # Points per Grand Prix over the 19 rounds the table holds, not the clock's count.
    rate = next(fact for fact in result["facts"] if fact["key"] == "points_per_race")
    assert rate["values"] == {"ANT": "20.0", "VER": "13.7"}
    assert freshness(result) == AFTER_ROUND_19
    assert result["sources"][:2] == BASE_AND_ROUND_19
