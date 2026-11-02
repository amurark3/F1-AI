"""Cross-check the computed standings against OpenF1 ``championship_*`` and Jolpica.

Neither feed is trusted as-is (``docs/DATA_SOURCES.md``, "Standings rule"). The
morning after Mexico 2026, OpenF1 had Red Bull on 380, missing Hadjar's two
points for 9th, and Jolpica still had the pre-penalty order. By midday both had
caught up on every total but one: OpenF1's driver table gave Hirakawa no point
for 10th, while its team table credited Haas with it.

The computed table is always the one served. A feed that disagrees is listed
in the payload's ``sources`` and logged at error level, which is what reaches
Sentry (``app/error_tracking.report_to_sentry``; a warning only rides along as
a breadcrumb). The same disagreement is reported once a day per process, not on
every recompute.

A driver or team on no points that a feed leaves out is not a disagreement, and
a feed with no table for the round yet is "unavailable", not "disagrees".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from fastf1.ergast import Ergast
from fastf1.exceptions import ErgastError
import structlog

from app.data.identity import resolve_team_name, season_directory
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.session_entries import load_weekend_entry_list
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from fastf1.ergast.interface import ErgastMultiResponse

    from app.data.standings_rounds import RoundPoints
    from app.data.standings_table import Table

logger = structlog.get_logger()

OPENF1_CHAMPIONSHIP = "openf1-championship"
JOLPICA_STANDINGS = "jolpica-standings"
# How long one disagreement stays reported before it is raised again.
ALERT_REPEAT_SECONDS = 24 * 60 * 60

CheckStatus = Literal["agrees", "disagrees", "unavailable"]
# A feed's points by driver code and by f1db team name.
Reported = tuple[dict[str, float], dict[str, float]]

# A feed's answer can be missing a field or be unreadable; FastF1 raises
# ErgastError for a bad answer and requests' errors are OSErrors.
_FEED_ERRORS = (OpenF1UnavailableError, ErgastError, OSError, KeyError, TypeError, ValueError)


@dataclass(frozen=True)
class Difference:
    """One row on which a feed and the computed table disagree. ``None`` means the side has no row."""

    table: Literal["drivers", "teams"]
    key: str
    computed: float | None
    reported: float | None


@dataclass(frozen=True)
class CrossCheck:
    """How one feed compares with the computed table after ``round``."""

    source: str
    round: int
    status: CheckStatus
    differences: tuple[Difference, ...] = ()

    def as_source(self) -> dict:
        """The entry this check adds to a payload's ``sources``."""
        return {
            "source": self.source,
            "role": "cross_check",
            "round": self.round,
            "status": self.status,
            "differences": [asdict(item) for item in self.differences],
        }


_alerted: TtlCache[tuple, bool] = TtlCache()


def _differences(
    table: Literal["drivers", "teams"], computed: Mapping[str, float], reported: Mapping[str, float]
) -> tuple[Difference, ...]:
    return tuple(
        Difference(table=table, key=key, computed=computed.get(key), reported=reported.get(key))
        for key in sorted(computed.keys() | reported.keys())
        if computed.get(key, 0.0) != reported.get(key, 0.0)
    )


def _compare(source: str, round_num: int, table: Table, reported: Reported) -> CrossCheck:
    drivers, teams = reported
    if not drivers and not teams:
        return CrossCheck(source=source, round=round_num, status="unavailable")
    found = (
        *(_differences("drivers", {row.key: row.points for row in table.drivers}, drivers) if drivers else ()),
        *(_differences("teams", {row.key: row.points for row in table.teams}, teams) if teams else ()),
    )
    return CrossCheck(source=source, round=round_num, status="disagrees" if found else "agrees", differences=found)


def _team_key(year: int, name: str) -> str:
    """f1db's name for a feed's team, or the feed's own spelling when it names no team on the grid."""
    return resolve_team_name(year, name) or name


def _number_codes(year: int, round_num: int) -> dict[int, str]:
    """Car number to driver code: the season's drivers, then the round's own cars on top (stand-ins)."""
    season = {driver.number: driver.code for driver in season_directory(year).drivers if driver.number and driver.code}
    entries = load_weekend_entry_list(year, round_num).entries
    return {**season, **{entry.number: entry.code for entry in entries if entry.number is not None}}


def _openf1_reported(year: int, last: RoundPoints) -> Reported:
    with new_client() as client:
        drivers = get_json(client, "championship_drivers", {"session_key": last.race_session_key})
        teams = get_json(client, "championship_teams", {"session_key": last.race_session_key})
    codes = _number_codes(year, last.round) if drivers else {}
    return (
        {codes.get(row["driver_number"], str(row["driver_number"])): float(row["points_current"]) for row in drivers},
        {_team_key(year, str(row["team_name"])): float(row["points_current"]) for row in teams},
    )


def _records(response: ErgastMultiResponse) -> list[dict]:
    """The rows of the one standings list asked for; empty before Jolpica publishes the round."""
    return response.content[0].to_dict("records") if response.content else []


def _jolpica_reported(year: int, round_num: int) -> Reported:
    ergast = Ergast()
    drivers = _records(ergast.get_driver_standings(season=year, round=round_num))
    teams = _records(ergast.get_constructor_standings(season=year, round=round_num))
    return (
        {str(row["driverCode"]): float(row["points"]) for row in drivers},
        {_team_key(year, str(row["constructorName"])): float(row["points"]) for row in teams},
    )


def _check(source: str, read: Callable[[], Reported], table: Table, round_num: int) -> CrossCheck:
    try:
        reported = read()
    except _FEED_ERRORS as exc:
        logger.warning("standings.cross_check_unavailable", source=source, round=round_num, error=str(exc))
        return CrossCheck(source=source, round=round_num, status="unavailable")
    return _compare(source, round_num, table, reported)


def _alert(year: int, check: CrossCheck) -> None:
    signature = (year, check.source, check.round, check.differences)
    if _alerted.get(signature):
        return
    _alerted.put(signature, True, ALERT_REPEAT_SECONDS)
    logger.error(
        "standings.cross_check_disagrees",
        year=year,
        round=check.round,
        source=check.source,
        differences=[asdict(item) for item in check.differences],
    )


def cross_check(year: int, table: Table, last: RoundPoints) -> tuple[CrossCheck, ...]:
    """Compare ``table``, computed through ``last``, with each feed's table for that round."""
    checks = (
        _check(OPENF1_CHAMPIONSHIP, lambda: _openf1_reported(year, last), table, last.round),
        _check(JOLPICA_STANDINGS, lambda: _jolpica_reported(year, last.round), table, last.round),
    )
    for check in checks:
        if check.status == "disagrees":
            _alert(year, check)
    return checks
