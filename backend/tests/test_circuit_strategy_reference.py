"""Tests for the baseline plan's edition search and its cache (app.data.strategy.reference).

The behaviour under test:

* the planning season's own edition is read once its race has been run, else
  the season before, back to 2023 (OpenF1's first season), never earlier: R20
  2026 was planned from 2022 because the old search kept the first edition
  FastF1 could load;
* an edition that cannot be read now is retried, never passed over for good: an
  older edition may answer meanwhile, labelled, but nothing is persisted;
* a search that read every edition it reached is persisted, misses included.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.data.circuit_reference_cache import (
    CachedReference,
    CircuitReferenceCacheUnavailableError,
)
from app.data.strategy import circuit_strategy_reference, reference as module
from app.utils.ttl_cache import TtlCache

pytestmark = pytest.mark.unit

CITY = "São Paulo"
LOCATION = "São Paulo, Brazil"
PLANNING_YEAR = 2026

# The clock every test runs against: the 2026 São Paulo race is still two days away.
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)

RACE_DAYS = {
    2026: "2026-11-08 17:00:00",
    2025: "2025-11-09 17:00:00",
    2024: "2024-11-03 15:30:00",
    2023: "2023-11-05 17:00:00",
}


def schedule_for(year: int, race_day: str, location: str = CITY) -> pd.DataFrame:
    """One-event season schedule shaped like FastF1's."""
    race = pd.Timestamp(race_day)
    return pd.DataFrame(
        [
            {
                "RoundNumber": 21 if year == 2025 else 20,
                "Location": location,
                "Country": "Brazil",
                "EventName": "São Paulo Grand Prix",
                "EventDate": race,
                "Session1": "Practice 1",
                "Session1DateUtc": race - timedelta(days=2),
                "Session2": "Qualifying",
                "Session2DateUtc": race - timedelta(days=1),
                "Session3": "Race",
                "Session3DateUtc": race,
                "Session4": None,
                "Session4DateUtc": pd.NaT,
                "Session5": None,
                "Session5DateUtc": pd.NaT,
            }
        ]
    )


class FakeCache:
    """Stands in for the durable circuit reference cache."""

    def __init__(self) -> None:
        self.hit: CachedReference | None = None
        self.available = True
        self.writes: list[tuple[str, int, dict | None]] = []

    def get(self, city: str, year: int) -> CachedReference | None:
        return self.hit

    def set(self, city: str, year: int, reference: dict | None) -> None:
        if not self.available:
            raise CircuitReferenceCacheUnavailableError("store unreachable")
        self.writes.append((city, year, reference))


class _Clock(datetime):
    moment = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.moment.astimezone(tz) if tz else cls.moment


@pytest.fixture
def world(monkeypatch):
    """Schedules per season, an edition reader that answers per year, and a frozen clock."""
    state: dict = {
        "schedules": {year: schedule_for(year, day) for year, day in RACE_DAYS.items()},
        "readable": {2025, 2024, 2023, 2026},
        "asked": [],
        "listed": [],
        "now": 0.0,
    }

    def get_event_schedule(year, include_testing=False):
        state["listed"].append(year)
        schedule = state["schedules"].get(year)
        if isinstance(schedule, BaseException):
            raise schedule
        return schedule if schedule is not None else pd.DataFrame(columns=["RoundNumber", "Location"])

    def edition_reference(edition):
        state["asked"].append((edition.year, edition.round, edition.name))
        return {"source_year": edition.year, "finishers": 17} if edition.year in state["readable"] else None

    _Clock.moment = NOW
    monkeypatch.setattr(module.fastf1, "get_event_schedule", get_event_schedule)
    monkeypatch.setattr(module, "edition_reference", edition_reference)
    monkeypatch.setattr(module, "datetime", _Clock)
    monkeypatch.setattr(module, "_unread", TtlCache(clock=lambda: state["now"]))
    return state


@pytest.fixture
def cache(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(module, "circuit_reference_cache", fake)
    return fake


# --- which edition ------------------------------------------------------------------------


def test_r20_2026_is_planned_from_the_2025_edition_not_the_unraced_2026_one(world, cache):
    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference == {"source_year": 2025, "finishers": 17, "unread_years": []}
    assert world["asked"] == [(2025, 21, "São Paulo Grand Prix")]


def test_the_planning_seasons_edition_is_read_once_its_race_is_run(world, cache):
    _Clock.moment = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR)["source_year"] == 2026
    assert [asked[0] for asked in world["asked"]] == [2026]


def test_the_search_never_reaches_before_openf1s_first_season(world, cache):
    world["readable"] = set()
    world["schedules"] = {}

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) is None
    assert world["listed"] == [2026, 2025, 2024, 2023]


def test_a_season_the_circuit_is_absent_from_is_skipped(world, cache):
    world["schedules"][2025] = schedule_for(2025, RACE_DAYS[2025], location="Las Vegas")

    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference["source_year"] == 2024
    assert reference["unread_years"] == []
    assert cache.writes == [(CITY, PLANNING_YEAR, reference)]


def test_a_renamed_location_is_matched_by_substring(world, cache):
    world["schedules"][2025] = schedule_for(2025, RACE_DAYS[2025], location="São Paulo (Interlagos)")

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR)["source_year"] == 2025


def test_a_location_without_a_city_is_not_searched(world, cache):
    assert circuit_strategy_reference("", PLANNING_YEAR) is None
    assert circuit_strategy_reference("  ,  ", PLANNING_YEAR) is None
    assert world["listed"] == []


# --- persisting ---------------------------------------------------------------------------


def test_a_fully_read_search_is_persisted(world, cache):
    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert cache.writes == [(CITY, PLANNING_YEAR, reference)]


def test_a_cached_reference_skips_the_search(world, cache):
    cache.hit = CachedReference(reference={"source_year": 2025}, source_year=2025, stored_at=None)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) == {"source_year": 2025}
    assert world["listed"] == []


def test_a_remembered_miss_skips_the_search(world, cache):
    cache.hit = CachedReference(reference=None, source_year=None, stored_at=None)

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) is None
    assert world["listed"] == []


def test_a_circuit_with_no_edition_is_remembered_as_a_miss(world, cache):
    world["schedules"] = {}

    assert circuit_strategy_reference("Madrid", PLANNING_YEAR) is None
    assert cache.writes == [("Madrid", PLANNING_YEAR, None)]


def test_an_unusable_store_still_returns_the_reference(world, cache):
    """Losing durability must not lose the answer this request already has."""
    cache.available = False

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR)["source_year"] == 2025


# --- editions that cannot be read now -----------------------------------------------------


def test_an_unread_edition_lets_an_older_one_answer_labelled_and_unpersisted(world, cache):
    world["readable"] = {2024}

    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference == {"source_year": 2024, "finishers": 17, "unread_years": [2025]}
    assert cache.writes == []


def test_with_no_edition_readable_the_years_are_named_and_nothing_is_persisted(world, cache):
    world["readable"] = set()

    assert circuit_strategy_reference(LOCATION, PLANNING_YEAR) == {
        "source_year": None,
        "unread_years": [2025, 2024, 2023],
    }
    assert cache.writes == []


def test_a_season_whose_schedule_fails_to_load_is_unread(world, cache):
    world["schedules"][2025] = RuntimeError("schedule backend down")

    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert (reference["source_year"], reference["unread_years"]) == (2024, [2025])
    assert cache.writes == []


def test_an_unread_answer_is_held_for_a_while_then_the_sources_are_asked_again(world, cache):
    world["readable"] = {2024}
    circuit_strategy_reference(LOCATION, PLANNING_YEAR)
    asked = len(world["asked"])

    circuit_strategy_reference(LOCATION, PLANNING_YEAR)
    assert len(world["asked"]) == asked

    world["now"] = module.UNREAD_RETRY_SECONDS + 1
    world["readable"] = {2025, 2024}
    reference = circuit_strategy_reference(LOCATION, PLANNING_YEAR)

    assert reference["source_year"] == 2025
    assert cache.writes == [(CITY, PLANNING_YEAR, reference)]


# --- has an edition been raced? -----------------------------------------------------------


def test_the_scheduled_race_session_decides_whether_an_edition_has_run():
    race_at = pd.Timestamp("2025-11-09 17:00:00")
    event = pd.Series({"Session1": "Practice 1", "Session5": "Race", "Session5DateUtc": race_at})

    assert module._edition_race_finished(event, race_at.to_pydatetime() + timedelta(hours=4)) is True
    assert module._edition_race_finished(event, race_at.to_pydatetime() + timedelta(hours=1)) is False


def test_the_event_date_stands_in_when_no_race_session_is_listed():
    event = pd.Series({"Session1": "Practice 1", "EventDate": pd.Timestamp("2025-11-09")})

    assert module._edition_race_finished(event, datetime(2025, 11, 10)) is True


def test_an_edition_with_no_date_at_all_is_never_treated_as_raced():
    event = pd.Series({"RoundNumber": 21, "Location": CITY, "EventDate": pd.NaT})

    assert module._edition_race_finished(event, datetime(2030, 1, 1)) is False


def test_an_event_without_a_name_is_read_with_an_empty_one():
    event = pd.Series({"RoundNumber": 21, "Location": CITY, "EventName": None})

    assert module._edition(event, 2025).name == ""
