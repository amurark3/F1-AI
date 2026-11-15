"""Tests for championship standings loading (app.data.predictions.standings).

Standings feed the team-strength weight and the model's ``driver_standing``
feature, so an empty result silently flattens every prediction toward the
midfield default. The risk this file covers is the fallback chain that exists to
stop that happening: f1db only (no rate limits; the season opener takes the
previous season's final table), and an empty answer is never cached.

f1db is a real seeded SQLite file, so the SQL underneath is exercised.
"""

from __future__ import annotations

import pytest

from app.data.predictions import standings as standings_module
from app.data.predictions.standings import _load_constructor_standings, _load_driver_standings

# The round being predicted. The seeded 2026 season has run rounds 1-2, so the
# table going into round 3 is the latest one f1db holds.
ROUND = 3


@pytest.fixture(autouse=True)
def _clear_caches():
    """Standings are memoised per (season, round) for the process lifetime."""
    standings_module._constructor_cache.clear()
    standings_module._driver_standings_cache.clear()
    yield
    standings_module._constructor_cache.clear()
    standings_module._driver_standings_cache.clear()


# ---------------------------------------------------------------------------
# f1db is the primary source
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_standings_come_from_local_f1db(fake_f1db):
    result = _load_constructor_standings(2026, ROUND)

    assert [row["constructor_name"] for row in result] == ["Red Bull", "Ferrari"]
    assert [row["position"] for row in result] == [1, 2]


@pytest.mark.integration
def test_driver_standings_come_from_local_f1db(fake_f1db):
    result = _load_driver_standings(2026, ROUND)

    assert result["VER"] == 1
    assert result["LEC"] == 2


@pytest.mark.integration
def test_standings_for_a_season_are_loaded_once_and_reused(fake_f1db, monkeypatch):
    first = _load_constructor_standings(2026, ROUND)

    # A second call must not re-run the query: blow up if it reaches f1db again.
    def _explode(year, round_num):
        raise AssertionError("standings were re-queried instead of served from cache")

    monkeypatch.setattr(standings_module, "constructor_standings_before_round", _explode)

    assert _load_constructor_standings(2026, ROUND) is first


@pytest.mark.integration
def test_driver_standings_for_a_season_are_loaded_once_and_reused(fake_f1db, monkeypatch):
    first = _load_driver_standings(2026, ROUND)

    def _explode(year, round_num):
        raise AssertionError("driver standings were re-queried instead of served from cache")

    monkeypatch.setattr(standings_module, "driver_standings_before_round", _explode)

    # Twenty drivers are scored per race off this one mapping, so re-querying it
    # would multiply the cost of every prediction.
    assert _load_driver_standings(2026, ROUND) is first


# ---------------------------------------------------------------------------
# An empty answer is not cached
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_season_f1db_does_not_hold_is_empty_and_asked_again_next_time(empty_f1db):
    assert _load_constructor_standings(2026, ROUND) == []
    assert _load_driver_standings(2026, ROUND) == {}
    assert not standings_module._constructor_cache
    assert not standings_module._driver_standings_cache


@pytest.mark.integration
def test_each_round_is_cached_separately(fake_f1db):
    """A recomputed past race must not be served a later round's cached table.

    Which table each round reads is covered in ``test_point_in_time_inputs.py``;
    this guards the cache key that keeps them apart.
    """
    _load_driver_standings(2026, 3)
    _load_driver_standings(2026, 4)
    _load_constructor_standings(2026, 3)
    _load_constructor_standings(2026, 4)

    assert set(standings_module._driver_standings_cache) == {(2026, 3), (2026, 4)}
    assert set(standings_module._constructor_cache) == {(2026, 3), (2026, 4)}
