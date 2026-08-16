"""Championship standings, from f1db with an Ergast fallback."""

from __future__ import annotations

from fastf1.ergast import Ergast
import structlog

from app.data.f1db_standings import current_constructor_standings, current_driver_standings

logger = structlog.get_logger()

# (year,) -> list of constructor standings dicts
_constructor_cache: dict[tuple[int,], list[dict]] = {}

# (year,) -> driver_code -> championship position
_driver_standings_cache: dict[tuple[int,], dict[str, int]] = {}


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


def _load_constructor_standings(year: int) -> list[dict]:
    """Constructor standings ([{constructor_name, position}]).

    Sourced from the local f1db dataset first (no rate limits); falls back to the
    live Ergast API when f1db lacks the season (e.g. a brand-new in-progress round).
    """
    cache_key = (year,)
    if cache_key in _constructor_cache:
        return _constructor_cache[cache_key]

    standings = current_constructor_standings(year) or _ergast_constructor_standings(year)
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


def _load_driver_standings(year: int) -> dict[str, int]:
    """Driver standings as {driver_code: position} — f1db first, Ergast fallback."""
    cache_key = (year,)
    if cache_key in _driver_standings_cache:
        return _driver_standings_cache[cache_key]

    standings = current_driver_standings(year) or _ergast_driver_standings(year)
    _driver_standings_cache[cache_key] = standings
    return standings
