"""Team and driver pages: an f1db season profile for each.

Power-unit usage belongs to the car, not the driver (FIA B8.2.7), and it is the
slowest and least certain input, so neither profile carries it: the pages read
it from the power-units endpoint. :func:`load_power_units` stays for the race
glance, where a failure leaves a plain reason in place of the decisions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.identity import season_directory
from app.data.profiles import driver_season, team_season, teams_index
from app.data.profiles.standings import season_standings
from app.services.power_units import build_power_units

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.data.profiles.standings import Standing

logger = structlog.get_logger()

POWER_UNITS_FAILED = "Power-unit usage could not be loaded right now."


def load_power_units(year: int) -> tuple[dict | None, str | None]:
    """The season's power-unit payload, or ``None`` and the reason it is missing."""
    try:
        payload = build_power_units(year)
    except Exception as exc:
        logger.warning("profiles.power_units_failed", year=year, error=str(exc), error_type=type(exc).__name__)
        return None, POWER_UNITS_FAILED
    if not payload.get("available"):
        return None, payload.get("reason")
    return payload, None


def _placed(team: dict, standing: Standing | None) -> dict:
    return {
        **team,
        "position": standing.position if standing else None,
        "points": standing.points if standing else 0.0,
    }


def _in_table_order(teams: list[dict], table: Mapping[str, Standing]) -> list[dict]:
    """Each team with its place and points in ``table``, in championship order, unranked teams last."""
    placed = [_placed(team, table.get(team["id"])) for team in teams]
    return sorted(placed, key=lambda team: (team["position"] is None, team["position"] or 0, team["name"]))


def build_directory(year: int) -> dict:
    """Every driver and team of ``year``, for links and the team dropdown.

    Teams are ordered by the same table the team pages show (``season_standings``),
    so the dropdown and the "open the leader" redirect agree with them.
    """
    directory = season_directory(year).as_dict()
    standings = season_standings(year)
    return {
        **directory,
        "teams": _in_table_order(directory["teams"], standings.teams),
        **standings.meta,
        "status": "ok",
    }


def build_team_profile(year: int, team_id: str) -> dict:
    season = team_season(year, team_id)
    if season is None:
        return {"year": year, "status": "not_found", "team": None}
    return {**season, "status": "ok"}


def build_driver_profile(year: int, driver_id: str) -> dict:
    season = driver_season(year, driver_id)
    if season is None:
        return {"year": year, "status": "not_found", "driver": None}
    return {**season, "status": "ok"}


def build_teams_index(year: int) -> dict:
    return {**teams_index(year), "status": "ok"}
