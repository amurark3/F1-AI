"""Tests for the pre-race circuit strategy reference search.

The behaviour under test: the search never tries to load an edition that has
not been raced yet (loading the in-progress weekend cost seconds on every cold
start before failing), and the result it does find is persisted so the next
process reads it instead of re-loading the telemetry.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.data import strategy as strategy_module
from app.data.circuit_reference_cache import (
    CachedReference,
    CircuitReferenceCacheUnavailable,
)
from app.data.strategy import circuit_strategy_reference

pytestmark = pytest.mark.unit

CITY = "Zandvoort"
LOCATION = "Zandvoort, Netherlands"
PLANNING_YEAR = 2026

# The clock every test runs against: the 2026 Dutch GP is still two days away.
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def schedule_for(year: int, race_day: str) -> pd.DataFrame:
    """One-event season schedule shaped like FastF1's."""
    return pd.DataFrame([{
        "RoundNumber": 15,
        "Location": CITY,
        "Country": "Netherlands",
        "EventName": "Dutch Grand Prix",
        "EventDate": pd.Timestamp(race_day),
        "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp(race_day) - pd.Timedelta(days=2),
        "Session2": "Qualifying",
        "Session2DateUtc": pd.Timestamp(race_day) - pd.Timedelta(days=1),
        "Session3": "Race",
        "Session3DateUtc": pd.Timestamp(race_day),
        "Session4": None,
        "Session4DateUtc": pd.NaT,
        "Session5": None,
        "Session5DateUtc": pd.NaT,
    }])


RACE_DAYS = {
    2026: "2026-08-23 13:00:00",
    2025: "2025-08-31 13:00:00",
}


class FakeCache:
    """Stands in for the durable circuit reference cache."""

    def __init__(self, hit: CachedReference | None = None, available: bool = True):
        self.hit = hit
        self.available = available
        self.writes: list[tuple[str, int, dict | None]] = []

    def get(self, city, year):
        return self.hit

    def set(self, city, year, reference):
        if not self.available:
            raise CircuitReferenceCacheUnavailable("store unreachable")
        self.writes.append((city, year, reference))


@pytest.fixture
def loaded(monkeypatch):
    """Wire the search onto fake schedules, telemetry, and a frozen clock."""
    calls: list[int] = []

    def fake_schedule(year, include_testing=False):
        if year not in RACE_DAYS:
            raise ValueError(f"no schedule for {year}")
        return schedule_for(year, RACE_DAYS[year])

    def fake_load_race_data(year, round_num):
        calls.append(year)
        return {"laps": pd.DataFrame([{"LapNumber": 1}]), "year": year}

    def fake_summary(race_data, edition_year):
        return {"source_year": edition_year, "sample_size": 20}

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(strategy_module.fastf1, "get_event_schedule", fake_schedule)
    monkeypatch.setattr(strategy_module, "_load_race_data", fake_load_race_data)
    monkeypatch.setattr(strategy_module, "_summarize_circuit_edition", fake_summary)
    monkeypatch.setattr(strategy_module, "datetime", _Clock)
    return calls


@pytest.fixture
def cache(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(strategy_module, "circuit_reference_cache", fake)
    return fake


def test_an_unraced_edition_is_never_loaded(loaded, cache):
    """The planning season's own race is still ahead — loading it would fail."""
    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference == {"source_year": 2025, "sample_size": 20}
    assert loaded == [2025]
    assert PLANNING_YEAR not in loaded


def test_the_planning_season_edition_is_used_once_its_race_is_run(loaded, cache, monkeypatch):
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(strategy_module, "datetime", _Clock)

    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference == {"source_year": 2026, "sample_size": 20}
    assert loaded == [2026]


def test_the_result_is_persisted_for_the_next_process(loaded, cache):
    circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert cache.writes == [(CITY, PLANNING_YEAR, {"source_year": 2025, "sample_size": 20})]


def test_a_cached_reference_skips_the_telemetry_load(loaded, cache):
    cache.hit = CachedReference(reference={"source_year": 2024}, source_year=2024, stored_at=None)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) == {"source_year": 2024}
    assert loaded == []


def test_a_remembered_miss_skips_the_search(loaded, cache):
    cache.hit = CachedReference(reference=None, source_year=None, stored_at=None)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) is None
    assert loaded == []


def test_a_miss_is_remembered_so_the_search_is_not_repeated(loaded, cache, monkeypatch):
    monkeypatch.setattr(strategy_module, "_load_race_data", lambda year, round_num: None)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) is None
    assert cache.writes == [(CITY, PLANNING_YEAR, None)]


def test_an_unusable_store_still_returns_the_reference(loaded, cache):
    """Losing durability must not lose the answer this request already has."""
    cache.available = False

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) == {"source_year": 2025, "sample_size": 20}


def test_a_location_without_a_city_is_not_searched(loaded, cache):
    assert circuit_strategy_reference("", PLANNING_YEAR) is None
    assert loaded == []
    assert cache.writes == []


def test_a_summary_failure_falls_through_to_an_older_edition(loaded, cache, monkeypatch):
    def failing_summary(race_data, edition_year):
        if edition_year == 2025:
            raise ValueError("corrupt lap frame")
        return {"source_year": edition_year, "sample_size": 20}

    monkeypatch.setattr(strategy_module, "_summarize_circuit_edition", failing_summary)
    monkeypatch.setattr(
        strategy_module.fastf1,
        "get_event_schedule",
        lambda year, include_testing=False: schedule_for(year, f"{year}-08-23 13:00:00"),
    )

    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference == {"source_year": 2024, "sample_size": 20}
