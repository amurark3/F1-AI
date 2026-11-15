"""Championship standings going into a round, from f1db."""

from __future__ import annotations

from app.data.f1db_standings import constructor_standings_before_round, driver_standings_before_round

# (year, round_num) -> constructor standings going into that round
_constructor_cache: dict[tuple[int, int], list[dict]] = {}

# (year, round_num) -> driver_code -> championship position going into that round
_driver_standings_cache: dict[tuple[int, int], dict[str, int]] = {}


def _load_constructor_standings(year: int, round_num: int) -> list[dict]:
    """Constructor standings going into ``round_num`` ([{constructor_name, position}]).

    As of the round, not the latest table: a recomputed past race must not see
    the championship that later rounds produced. Sourced from the local f1db
    dataset (no rate limits). The season opener takes the previous season's final
    table. An empty answer is not cached, so f1db's next release is picked up.
    """
    cache_key = (year, round_num)
    if cache_key in _constructor_cache:
        return _constructor_cache[cache_key]

    standings = constructor_standings_before_round(year, round_num)
    if standings:
        _constructor_cache[cache_key] = standings
    return standings


def _load_driver_standings(year: int, round_num: int) -> dict[str, int]:
    """Driver standings going into ``round_num`` as {driver_code: position}.

    See :func:`_load_constructor_standings`.
    """
    cache_key = (year, round_num)
    if cache_key in _driver_standings_cache:
        return _driver_standings_cache[cache_key]

    standings = driver_standings_before_round(year, round_num)
    if standings:
        _driver_standings_cache[cache_key] = standings
    return standings
