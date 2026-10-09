"""Championship standings, from f1db with an Ergast fallback."""

from __future__ import annotations

from fastf1.ergast import Ergast
import structlog

from app.data.f1db_standings import constructor_standings_before_round, driver_standings_before_round

logger = structlog.get_logger()

# (year, round_num) -> constructor standings going into that round
_constructor_cache: dict[tuple[int, int], list[dict]] = {}

# (year, round_num) -> driver_code -> championship position going into that round
_driver_standings_cache: dict[tuple[int, int], dict[str, int]] = {}


def _ergast_constructor_standings(year: int) -> list[dict]:
    """Live Ergast fallback for constructor standings (current or previous season)."""
    for season in (year, year - 1):
        try:
            data = Ergast().get_constructor_standings(season=season)
            if data.content:
                return [
                    {
                        "constructor_name": str(row.get("constructorName", "")),
                        "position": int(row.get("position", 10)),
                    }
                    for _, row in data.content[0].iterrows()
                ]
        except Exception as exc:
            logger.warning("predictions.constructor_standings_error", year=season, error=str(exc))
    return []


def _load_constructor_standings(year: int, round_num: int) -> list[dict]:
    """Constructor standings going into ``round_num`` ([{constructor_name, position}]).

    As of the round, not the latest table: a recomputed past race must not see
    the championship that later rounds produced. Sourced from the local f1db
    dataset first (no rate limits); falls back to the live Ergast API when f1db
    lacks the season (e.g. a brand-new in-progress round).
    """
    cache_key = (year, round_num)
    if cache_key in _constructor_cache:
        return _constructor_cache[cache_key]

    standings = constructor_standings_before_round(year, round_num) or _ergast_constructor_standings(year)
    _constructor_cache[cache_key] = standings
    return standings


def _ergast_driver_standings(year: int) -> dict[str, int]:
    """Live Ergast fallback for driver standings (current or previous season)."""
    for season in (year, year - 1):
        try:
            data = Ergast().get_driver_standings(season=season)
            if data.content:
                result = {
                    str(row.get("driverCode", "")): int(row.get("position", 10))
                    for _, row in data.content[0].iterrows()
                    if str(row.get("driverCode", ""))
                }
                if result:
                    return result
        except Exception as exc:
            logger.warning("predictions.driver_standings_error", year=season, error=str(exc))
    return {}


def _load_driver_standings(year: int, round_num: int) -> dict[str, int]:
    """Driver standings going into ``round_num`` as {driver_code: position}.

    f1db first, Ergast fallback — see :func:`_load_constructor_standings`.
    """
    cache_key = (year, round_num)
    if cache_key in _driver_standings_cache:
        return _driver_standings_cache[cache_key]

    standings = driver_standings_before_round(year, round_num) or _ergast_driver_standings(year)
    _driver_standings_cache[cache_key] = standings
    return standings
