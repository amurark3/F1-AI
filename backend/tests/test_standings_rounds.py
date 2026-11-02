"""Tests for reading each round's points past f1db (app.data.standings_rounds).

A round counts only as a whole (its sprint with its race), only once its race
has ended, and only when every scoring car can be named and placed in a team.
Anything less stops the table at the round before: a table never skips a round
or credits a point to the wrong team.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest
import structlog

from app.data.current_standings import current_standings
from app.data.openf1.sessions import OpenF1Session
from tests.roster_support import MEXICO, MEXICO_QUALIFYING, MEXICO_RACE, drivers_route, load, mexico_drivers, weekend
from tests.standings_support import MEXICO_ROUND, Feeds, mexico_feeds, route_error

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

SPRINT_KEY = 11401
FAILING_KEY = 99999


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    yield from mexico_feeds(tmp_path, monkeypatch)


def sprint_session() -> OpenF1Session:
    start = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
    return OpenF1Session(
        session_key=SPRINT_KEY,
        meeting_key=1298,
        circuit_key=None,
        code="S",
        name="Sprint",
        date_start=start,
        date_end=start.replace(hour=16),
    )


def results_by_session(answers: dict[int, list | httpx.Response]):
    def route(request: httpx.Request) -> httpx.Response:
        answer = answers.get(int(request.url.params["session_key"]), [])
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    return route


def race_rows() -> list[dict]:
    return load(MEXICO / "openf1_session_result.json")


def as_of() -> tuple[int | None, bool]:
    standings = current_standings(2026)
    return standings.as_of_round, standings.provisional


# --- what counts ----------------------------------------------------------------------


def test_a_sprint_scores_with_its_race_but_not_in_the_count_back(feeds):
    feeds.weekends[MEXICO_ROUND] = (*weekend(MEXICO), sprint_session())
    sprint = [
        {"driver_number": 12, "position": 1, "points": 8.0},
        {"driver_number": 3, "position": 2, "points": 7.0},
    ]
    feeds.routes["session_result"] = results_by_session({SPRINT_KEY: sprint, MEXICO_RACE: race_rows()})

    standings = current_standings(2026)

    by_code = {row.key: row for row in standings.drivers}
    assert (by_code["ANT"].points, by_code["VER"].points) == (388, 268)
    assert (by_code["ANT"].wins, by_code["VER"].wins) == (9, 3)
    assert {row.key: row.points for row in standings.teams}["Mercedes"] == 638
    assert standings.sources[1]["sessions"] == ["S", "R"]


def test_every_round_past_f1db_counts_in_order_until_one_has_not_run(feeds):
    feeds.weekends[20] = weekend(MEXICO)

    standings = current_standings(2026)

    assert standings.as_of_round == 20
    assert {row.key: row.points for row in standings.drivers}["VER"] == 286
    assert [source["round"] for source in standings.sources if source["role"] == "points"] == [19, 20]


def test_a_round_whose_race_has_not_ended_is_not_counted(feeds):
    race = next(session for session in weekend(MEXICO) if session.code == "R")
    feeds.weekends[MEXICO_ROUND] = (replace(race, date_end=datetime(2999, 1, 1, tzinfo=UTC)),)

    assert as_of() == (18, False)


def test_a_round_whose_result_is_not_published_is_not_counted(feeds):
    feeds.routes["session_result"] = []

    assert as_of() == (18, False)


def test_a_sprint_weekend_waits_for_both_results(feeds):
    feeds.weekends[MEXICO_ROUND] = (*weekend(MEXICO), sprint_session())
    feeds.routes["session_result"] = results_by_session({MEXICO_RACE: race_rows()})

    assert as_of() == (18, False)


def test_a_round_without_an_entry_list_is_not_counted(feeds):
    feeds.routes["drivers"] = drivers_route({})

    assert as_of() == (18, False)


# --- what makes a round unusable ------------------------------------------------------------


def unusable(feeds: Feeds) -> list[dict]:
    with structlog.testing.capture_logs() as logs:
        assert as_of() == (18, False)
    return [log for log in logs if log["event"] == "standings.round_unusable"]


def test_a_row_without_points_makes_the_round_unusable(feeds):
    rows = race_rows()
    rows[0] = {**rows[0], "points": None}
    feeds.routes["session_result"] = rows

    assert [log["round"] for log in unusable(feeds)] == [19]


def test_a_scoring_car_missing_from_the_entry_list_makes_the_round_unusable(feeds):
    rows = race_rows()
    rows[0] = {**rows[0], "driver_number": 99}
    feeds.routes["session_result"] = rows

    assert len(unusable(feeds)) == 1


def test_a_scoring_car_whose_team_cannot_be_placed_makes_the_round_unusable(feeds):
    race_list = [
        {**row, "team_name": "Brawn GP"} if row["driver_number"] == 3 else row for row in mexico_drivers()[MEXICO_RACE]
    ]
    feeds.routes["drivers"] = drivers_route({MEXICO_RACE: race_list, MEXICO_QUALIFYING: race_list})

    assert len(unusable(feeds)) == 1


def test_a_car_that_scored_nothing_and_cannot_be_named_is_left_out(feeds):
    rows = race_rows()
    last = next(index for index, row in enumerate(rows) if row["driver_number"] == 14)
    rows[last] = {**rows[last], "driver_number": 99}
    feeds.routes["session_result"] = rows

    standings = current_standings(2026)

    assert standings.as_of_round == 19
    assert "99" not in {row.key for row in standings.drivers}


# --- outages ------------------------------------------------------------------------------------


def test_an_openf1_outage_keeps_the_rounds_already_read(feeds):
    failing = replace(next(session for session in weekend(MEXICO) if session.code == "R"), session_key=FAILING_KEY)
    feeds.weekends[20] = (failing,)
    feeds.routes["session_result"] = results_by_session({MEXICO_RACE: race_rows(), FAILING_KEY: route_error(500)})

    with structlog.testing.capture_logs() as logs:
        standings = current_standings(2026)

    assert standings.as_of_round == 19
    assert [log["event"] for log in logs if log["event"].startswith("standings.openf1")] == [
        "standings.openf1_unavailable"
    ]
