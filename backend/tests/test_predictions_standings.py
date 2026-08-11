"""Tests for championship standings loading (app.data.predictions.standings).

Standings feed the team-strength weight and the model's ``driver_standing``
feature, so an empty result silently flattens every prediction toward the
midfield default. The risk this file covers is the fallback chain that exists to
stop that happening: local f1db first (no rate limits), then live Ergast for the
current season, then the previous season, then — and only then — empty.

Ergast is mocked at the class boundary; f1db is a real seeded SQLite file, so
the SQL underneath is exercised rather than stubbed.
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd
import pytest

from app.data.predictions import standings as standings_module
from app.data.predictions.standings import _load_constructor_standings, _load_driver_standings


class _FakeErgastResponse:
    def __init__(self, frames: list[pd.DataFrame]) -> None:
        self.content = frames


class _FakeErgast:
    """Stands in for ``fastf1.ergast.Ergast``; scripted per season."""

    constructor_seasons: ClassVar[dict[int, object]] = {}
    driver_seasons: ClassVar[dict[int, object]] = {}
    calls: ClassVar[list[tuple[str, int]]] = []

    def get_constructor_standings(self, season: int):
        type(self).calls.append(("constructor", season))
        return self._resolve(type(self).constructor_seasons, season)

    def get_driver_standings(self, season: int):
        type(self).calls.append(("driver", season))
        return self._resolve(type(self).driver_seasons, season)

    @staticmethod
    def _resolve(table: dict[int, object], season: int):
        value = table.get(season, _FakeErgastResponse([]))
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture(autouse=True)
def _clear_caches():
    """Standings are memoised per season for the process lifetime."""
    standings_module._constructor_cache.clear()
    standings_module._driver_standings_cache.clear()
    yield
    standings_module._constructor_cache.clear()
    standings_module._driver_standings_cache.clear()


@pytest.fixture
def ergast(monkeypatch):
    _FakeErgast.constructor_seasons = {}
    _FakeErgast.driver_seasons = {}
    _FakeErgast.calls = []
    monkeypatch.setattr(standings_module, "Ergast", _FakeErgast)
    return _FakeErgast


def _constructor_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"constructorName": "McLaren", "position": 1},
            {"constructorName": "Ferrari", "position": 2},
        ]
    )


def _driver_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"driverCode": "NOR", "position": 1},
            {"driverCode": "LEC", "position": 2},
            {"driverCode": "", "position": 3},  # a driver with no code at all
        ]
    )


# ---------------------------------------------------------------------------
# f1db is the primary source
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_standings_come_from_local_f1db_without_touching_ergast(fake_f1db, ergast):
    result = _load_constructor_standings(2026)

    assert [row["constructor_name"] for row in result] == ["Red Bull", "Ferrari"]
    assert [row["position"] for row in result] == [1, 2]
    assert ergast.calls == []  # no rate-limited call when the local data answers


@pytest.mark.integration
def test_driver_standings_come_from_local_f1db_without_touching_ergast(fake_f1db, ergast):
    result = _load_driver_standings(2026)

    assert result["VER"] == 1
    assert result["LEC"] == 2
    assert ergast.calls == []


@pytest.mark.integration
def test_standings_for_a_season_are_loaded_once_and_reused(fake_f1db, ergast, monkeypatch):
    first = _load_constructor_standings(2026)

    # A second call must not re-run the query: blow up if it reaches f1db again.
    def _explode(year):
        raise AssertionError("standings were re-queried instead of served from cache")

    monkeypatch.setattr(standings_module, "current_constructor_standings", _explode)

    assert _load_constructor_standings(2026) is first


@pytest.mark.integration
def test_driver_standings_for_a_season_are_loaded_once_and_reused(fake_f1db, ergast, monkeypatch):
    first = _load_driver_standings(2026)

    def _explode(year):
        raise AssertionError("driver standings were re-queried instead of served from cache")

    monkeypatch.setattr(standings_module, "current_driver_standings", _explode)

    # Twenty drivers are scored per race off this one mapping, so re-querying it
    # would multiply the cost of every prediction.
    assert _load_driver_standings(2026) is first


# ---------------------------------------------------------------------------
# Ergast fallback
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_constructor_standings_fall_back_to_live_ergast_when_f1db_lacks_the_season(empty_f1db, ergast):
    ergast.constructor_seasons = {2026: _FakeErgastResponse([_constructor_frame()])}

    result = _load_constructor_standings(2026)

    assert result == [
        {"constructor_name": "McLaren", "position": 1},
        {"constructor_name": "Ferrari", "position": 2},
    ]


@pytest.mark.integration
def test_driver_standings_fall_back_to_live_ergast_and_drop_rows_without_a_code(empty_f1db, ergast):
    ergast.driver_seasons = {2026: _FakeErgastResponse([_driver_frame()])}

    result = _load_driver_standings(2026)

    # A blank driver code would collide with every other blank row, so those
    # rows are dropped rather than folded into one bogus entry.
    assert result == {"NOR": 1, "LEC": 2}


@pytest.mark.integration
def test_a_brand_new_season_with_no_results_yet_falls_back_to_last_year(empty_f1db, ergast):
    # Round 1 of a new season has no standings at all; last year's order is a
    # better team-strength prior than "everyone is P10".
    ergast.constructor_seasons = {
        2026: _FakeErgastResponse([]),  # season exists but is empty
        2025: _FakeErgastResponse([_constructor_frame()]),
    }
    ergast.driver_seasons = {2026: _FakeErgastResponse([]), 2025: _FakeErgastResponse([_driver_frame()])}

    assert _load_constructor_standings(2026)[0]["constructor_name"] == "McLaren"
    assert _load_driver_standings(2026) == {"NOR": 1, "LEC": 2}
    assert ("constructor", 2025) in ergast.calls
    assert ("driver", 2025) in ergast.calls


@pytest.mark.integration
def test_a_season_whose_rows_carry_no_driver_codes_falls_through_to_the_previous_one(empty_f1db, ergast):
    codeless = pd.DataFrame([{"driverCode": "", "position": 1}])
    ergast.driver_seasons = {
        2026: _FakeErgastResponse([codeless]),
        2025: _FakeErgastResponse([_driver_frame()]),
    }

    # A frame that yields zero usable codes is as useless as no frame at all.
    assert _load_driver_standings(2026) == {"NOR": 1, "LEC": 2}


@pytest.mark.integration
def test_an_ergast_outage_for_one_season_does_not_stop_the_previous_one_being_tried(empty_f1db, ergast):
    ergast.constructor_seasons = {
        2026: RuntimeError("ergast 503"),
        2025: _FakeErgastResponse([_constructor_frame()]),
    }
    ergast.driver_seasons = {2026: RuntimeError("ergast 503"), 2025: _FakeErgastResponse([_driver_frame()])}

    assert _load_constructor_standings(2026)[0]["position"] == 1
    assert _load_driver_standings(2026)["NOR"] == 1


@pytest.mark.integration
def test_a_total_outage_degrades_to_empty_standings_rather_than_raising(empty_f1db, ergast):
    ergast.constructor_seasons = {2026: RuntimeError("down"), 2025: RuntimeError("down")}
    ergast.driver_seasons = {2026: RuntimeError("down"), 2025: RuntimeError("down")}

    # Predictions must still be computable with the midfield defaults.
    assert _load_constructor_standings(2026) == []
    assert _load_driver_standings(2026) == {}


@pytest.mark.integration
def test_missing_ergast_columns_fall_back_to_a_midfield_position(empty_f1db, ergast):
    ergast.constructor_seasons = {2026: _FakeErgastResponse([pd.DataFrame([{"unexpected": 1}])])}

    assert _load_constructor_standings(2026) == [{"constructor_name": "", "position": 10}]
