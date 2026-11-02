"""Tests for the current season's standings (app.data.current_standings).

The standings used to come from f1db alone, so between a race and f1db's next
release (about 10 h after Mexico 2026, sometimes days) the site showed the
previous round. Taking Jolpica's or OpenF1's table as-is would also have been
wrong the morning after Mexico. The rule (docs/DATA_SOURCES.md): f1db's last
round, plus each later round's points from OpenF1 ``session_result``, marked
provisional and cross-checked.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

import pytest
import structlog

from app.data import current_standings as module
from app.data.current_standings import CONFIRMED_TTL_SECONDS, PROVISIONAL_TTL_SECONDS, current_standings
from tests.roster_support import AFTER_MEXICO, MEXICO, load
from tests.standings_support import Feeds, mexico_feeds

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.data.standings_table import Standing

pytestmark = pytest.mark.integration

MEXICO_TRUTH = load(MEXICO / "f1db_standings_after_r19.json")


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    yield from mexico_feeds(tmp_path, monkeypatch)


def points(rows: tuple[Standing, ...]) -> dict[str, float]:
    return {row.key: row.points for row in rows}


# --- Accept: f1db at round 18 + OpenF1 round 19 ------------------------------------


def test_mexico_2026_is_computed_from_f1db_round_18_and_openf1_round_19(feeds):
    standings = current_standings(2026)

    drivers, teams = points(standings.drivers), points(standings.teams)
    assert (drivers["ANT"], drivers["VER"]) == (380, 261)
    assert (teams["Red Bull"], teams["McLaren"], teams["Audi"]) == (382, 365, 27)
    assert standings.provisional is True
    assert standings.as_of_round == 19


def test_mexico_2026_matches_the_table_f1db_published_after_round_19(feeds):
    """Every place and total, including Hirakawa's point and the count-back of the tied drivers."""
    standings = current_standings(2026)

    assert [(row.position, row.key, row.points) for row in standings.drivers] == [
        (row["position"], row["code"], row["points"]) for row in MEXICO_TRUTH["drivers"]
    ]
    assert [(row.position, row.key, row.points) for row in standings.teams] == [
        (row["position"], row["team"], row["points"]) for row in MEXICO_TRUTH["constructors"]
    ]


def test_the_sources_name_the_base_the_added_round_and_each_cross_check(feeds):
    sources = current_standings(2026).sources

    assert sources[:2] == (
        {"source": "f1db", "role": "base", "through_round": 18, "version": "v2026.18.0"},
        {"source": "openf1-session-result", "role": "points", "round": 19, "sessions": ["R"]},
    )
    openf1, jolpica = sources[2:]
    assert (openf1["source"], openf1["role"], openf1["round"], openf1["status"]) == (
        "openf1-championship",
        "cross_check",
        19,
        "disagrees",
    )
    assert openf1["differences"] == [{"table": "drivers", "key": "HIR", "computed": 1.0, "reported": 0.0}]
    assert (jolpica["source"], jolpica["status"], jolpica["differences"]) == ("jolpica-standings", "agrees", [])


def test_a_feed_that_disagrees_is_reported_and_the_computed_value_is_served(feeds):
    with structlog.testing.capture_logs() as logs:
        standings = current_standings(2026)

    alerts = [log for log in logs if log["event"] == "standings.cross_check_disagrees"]
    assert [(alert["log_level"], alert["source"], alert["round"]) for alert in alerts] == [
        ("error", "openf1-championship", 19)
    ]
    assert points(standings.drivers)["HIR"] == 1


# --- confirmed tables ---------------------------------------------------------------


def test_once_f1db_holds_the_latest_round_the_table_is_confirmed_and_not_cross_checked(feeds):
    feeds.weekends.clear()

    standings = current_standings(2026)

    assert (standings.as_of_round, standings.provisional) == (18, False)
    assert points(standings.drivers)["ANT"] == 365
    assert standings.sources == ({"source": "f1db", "role": "base", "through_round": 18, "version": "v2026.18.0"},)
    assert feeds.jolpica_calls == 0
    assert "championship_drivers" not in feeds.openf1_paths()


def test_a_finished_season_is_never_looked_up_past_f1db(feeds, monkeypatch):
    monkeypatch.setattr(module, "_utc_now", lambda: AFTER_MEXICO.replace(year=2027))

    standings = current_standings(2026)

    assert (standings.as_of_round, standings.provisional) == (18, False)
    assert feeds.weekend_calls == []


def test_a_season_f1db_does_not_hold_has_no_base_and_no_round(feeds):
    feeds.weekends.clear()

    standings = current_standings(2027)

    assert (standings.drivers, standings.teams, standings.as_of_round, standings.provisional) == ((), (), None, False)
    assert standings.sources == ()


# --- cache ----------------------------------------------------------------------------


def test_a_provisional_table_is_kept_for_its_lifetime_then_read_again(feeds):
    current_standings(2026)
    calls = len(feeds.weekend_calls)

    feeds.clock[0] += PROVISIONAL_TTL_SECONDS - 1
    current_standings(2026)
    assert len(feeds.weekend_calls) == calls

    feeds.clock[0] += 1
    current_standings(2026)
    assert len(feeds.weekend_calls) > calls


def test_a_confirmed_table_is_read_again_sooner_so_a_new_result_is_picked_up(feeds):
    feeds.weekends.clear()
    current_standings(2026)
    calls = len(feeds.weekend_calls)

    feeds.clock[0] += CONFIRMED_TTL_SECONDS
    current_standings(2026)

    assert len(feeds.weekend_calls) > calls


# --- payload shapes -------------------------------------------------------------------


def test_rows_and_meta_are_the_api_shape(feeds):
    standings = current_standings(2026)

    assert standings.driver_rows()[0] == {
        "position": 1,
        "code": "ANT",
        "driver": "Kimi Antonelli",
        "team": "Mercedes",
        "points": 380.0,
        "wins": 9,
    }
    assert standings.team_rows()[2] == {"position": 3, "team": "Red Bull", "points": 382.0, "wins": 3}
    meta = standings.meta()
    assert (meta["as_of_round"], meta["provisional"]) == (19, True)
    assert meta["sources"] == list(standings.sources)


def test_the_season_clock_is_timezone_aware_utc():
    assert module._utc_now().tzinfo is UTC
