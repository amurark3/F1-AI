"""Tests for cross-checking the computed standings (app.data.standings_cross_check).

Neither OpenF1's ``championship_*`` tables nor Jolpica's standings are trusted
as-is: the morning after Mexico 2026, OpenF1 had Red Bull on 380 and Jolpica the
pre-penalty order. The computed table is always the one served; a feed that
disagrees is reported once, as an error event Sentry picks up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastf1.exceptions import ErgastError
import pytest
import structlog

from app.data import standings_cross_check as module
from app.data.current_standings import current_standings
from app.data.standings_cross_check import ALERT_REPEAT_SECONDS, cross_check
from app.data.standings_rounds import RoundPoints
from app.data.standings_table import Table
from app.utils.ttl_cache import TtlCache
from tests.roster_support import MEXICO, MEXICO_RACE, load
from tests.standings_support import MEXICO_ROUND, Feeds, mexico_feeds, route_error

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

LAST_ROUND = RoundPoints(round=MEXICO_ROUND, race_session_key=MEXICO_RACE, sessions=("R",), scores=())


@pytest.fixture
def feeds(tmp_path, monkeypatch) -> Iterator[Feeds]:
    yield from mexico_feeds(tmp_path, monkeypatch)


@pytest.fixture
def table(feeds, monkeypatch) -> Table:
    """The computed Mexico table, with the alert its own cross-check raised forgotten."""
    standings = current_standings(2026)
    monkeypatch.setattr(module, "_alerted", TtlCache(clock=lambda: feeds.clock[0]))
    return Table(drivers=standings.drivers, teams=standings.teams)


def checks_by_source(table: Table) -> dict:
    return {check.source: check for check in cross_check(2026, table, LAST_ROUND)}


def differences(check) -> list[tuple[str, str, float | None, float | None]]:
    return [(item.table, item.key, item.computed, item.reported) for item in check.differences]


# --- OpenF1 championship_* -------------------------------------------------------------


def test_openf1_missing_hirakawas_point_is_the_only_difference_on_2_november(feeds, table):
    check = checks_by_source(table)["openf1-championship"]

    assert (check.round, check.status) == (19, "disagrees")
    assert differences(check) == [("drivers", "HIR", 1.0, 0.0)]


def test_openf1_on_the_morning_after_mexico_had_red_bull_two_points_short(feeds, table):
    teams = load(MEXICO / "openf1_championship_teams.json")
    feeds.routes["championship_teams"] = [
        {**row, "points_current": 380.0} if row["team_name"] == "Red Bull Racing" else row for row in teams
    ]

    check = checks_by_source(table)["openf1-championship"]

    assert ("teams", "Red Bull", 382.0, 380.0) in differences(check)


def test_drivers_who_sat_the_round_out_are_matched_by_their_season_number(feeds, table):
    """Ocon (31) and Tsunoda (22) were not in the Mexico race but are in OpenF1's table."""
    check = checks_by_source(table)["openf1-championship"]

    assert not any(key in {"OCO", "TSU", "31", "22"} for _, key, _, _ in differences(check))


def test_a_feed_row_that_cannot_be_named_is_reported_under_its_own_label(feeds, table):
    feeds.routes["championship_drivers"] = [{"driver_number": 98, "points_current": 4.0}]
    feeds.routes["championship_teams"] = [{"team_name": "Brawn GP", "points_current": 172.0}]

    found = differences(checks_by_source(table)["openf1-championship"])

    assert ("drivers", "98", None, 4.0) in found
    assert ("teams", "Brawn GP", None, 172.0) in found


def test_a_driver_on_no_points_missing_from_a_feed_is_not_a_difference(feeds, table):
    feeds.routes["championship_drivers"] = [
        row for row in load(MEXICO / "openf1_championship_drivers.json") if row["driver_number"] not in {18, 50}
    ]

    found = differences(checks_by_source(table)["openf1-championship"])

    assert found == [("drivers", "HIR", 1.0, None)]


def test_openf1_without_a_table_yet_is_unavailable_not_a_disagreement(feeds, table):
    feeds.routes["championship_drivers"] = []
    feeds.routes["championship_teams"] = []

    check = checks_by_source(table)["openf1-championship"]

    assert (check.status, check.differences) == ("unavailable", ())


def test_an_openf1_outage_is_unavailable(feeds, table):
    feeds.routes["championship_drivers"] = route_error(500)

    with structlog.testing.capture_logs() as logs:
        check = checks_by_source(table)["openf1-championship"]

    assert check.status == "unavailable"
    assert "standings.cross_check_unavailable" in [log["event"] for log in logs]


# --- Jolpica -------------------------------------------------------------------------------


def test_jolpica_agrees_once_it_has_applied_the_penalties(feeds, table):
    check = checks_by_source(table)["jolpica-standings"]

    assert (check.round, check.status, check.differences) == (19, "agrees", ())


def test_jolpicas_pre_penalty_table_disagrees(feeds, table):
    """On 2 Nov morning Jolpica had Piastri on 150 (should be 144) and Lawson on 79 (83)."""
    feeds.jolpica_drivers = [
        {**row, "points": {"PIA": 150.0, "LAW": 79.0}.get(row["driverCode"], row["points"])}
        for row in feeds.jolpica_drivers
    ]

    check = checks_by_source(table)["jolpica-standings"]

    assert differences(check) == [("drivers", "LAW", 83.0, 79.0), ("drivers", "PIA", 144.0, 150.0)]


def test_jolpica_before_it_publishes_the_round_is_unavailable(feeds, table):
    feeds.jolpica_drivers = []
    feeds.jolpica_teams = []

    assert checks_by_source(table)["jolpica-standings"].status == "unavailable"


@pytest.mark.parametrize("error", [ErgastError("bad answer"), OSError("down")], ids=["ergast", "network"])
def test_a_jolpica_failure_is_unavailable(feeds, table, error):
    feeds.jolpica_error = error

    assert checks_by_source(table)["jolpica-standings"].status == "unavailable"


# --- alerting --------------------------------------------------------------------------------


def alerts(logs: list[dict]) -> list[str]:
    return [log["source"] for log in logs if log["event"] == "standings.cross_check_disagrees"]


def test_the_same_disagreement_is_reported_once_then_again_a_day_later(feeds, table):
    with structlog.testing.capture_logs() as logs:
        cross_check(2026, table, LAST_ROUND)
        cross_check(2026, table, LAST_ROUND)
        feeds.clock[0] += ALERT_REPEAT_SECONDS
        cross_check(2026, table, LAST_ROUND)

    assert alerts(logs) == ["openf1-championship", "openf1-championship"]


def test_a_new_disagreement_is_reported_straight_away(feeds, table):
    with structlog.testing.capture_logs() as logs:
        cross_check(2026, table, LAST_ROUND)
        feeds.jolpica_teams = [{**row, "points": 0.0} for row in feeds.jolpica_teams]
        cross_check(2026, table, LAST_ROUND)

    assert alerts(logs) == ["openf1-championship", "jolpica-standings"]


def test_the_alert_carries_every_difference_for_the_issue_page(feeds, table):
    with structlog.testing.capture_logs() as logs:
        cross_check(2026, table, LAST_ROUND)

    alert = next(log for log in logs if log["event"] == "standings.cross_check_disagrees")
    assert (alert["log_level"], alert["year"], alert["round"]) == ("error", 2026, 19)
    assert alert["differences"] == [{"table": "drivers", "key": "HIR", "computed": 1.0, "reported": 0.0}]
    assert alert["source"] == module.OPENF1_CHAMPIONSHIP
