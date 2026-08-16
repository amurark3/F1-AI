"""Tests for the session loaders (app.data.predictions.sessions).

Qualifying, practice and sprint results are the strongest inputs a race
prediction has, and all three arrive from FastF1 — a network source that is
absent for an upcoming weekend, partial during one, and occasionally broken.
FastF1 is mocked at the ``get_session`` boundary here; the parsing, ranking,
caching and fallback logic underneath is the real thing.

What the assertions guard:

* **Session probing is gated on the calendar.** ``_qualifying_has_occurred`` is
  what stops a prediction for a future race spending its whole timeout on
  failing FastF1 loads, so its clock arithmetic is pinned in both directions.
* **A missing lap is not a missing driver.** A NaN position (no time set,
  crashed in Q1) is dropped from the ordering rather than coerced to P0, which
  would put that driver on pole.
* **Practice degrades session by session.** FP3 → FP2 → FP1, and a session that
  loads but has no usable laps must fall through rather than return an empty
  grid that outranks the next session's real data.
* **A non-sprint weekend is not an error.** The absent sprint session must cache
  an empty result, not retry per driver.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.data.predictions import sessions as sessions_module
from app.data.predictions.sessions import (
    _load_practice,
    _load_qualifying,
    _load_sprint_result,
    _qualifying_has_occurred,
)

YEAR = 2026
ROUND = 4

QUALIFYING_ROWS = [
    {"Position": 2.0, "Abbreviation": "LEC", "FirstName": "Charles", "LastName": "Leclerc", "TeamName": "Ferrari"},
    {"Position": 1.0, "Abbreviation": "VER", "FirstName": "Max", "LastName": "Verstappen", "TeamName": "Red Bull"},
    {"Position": 3.0, "Abbreviation": "NOR", "FirstName": "Lando", "LastName": "Norris", "TeamName": "McLaren"},
]


class _FakeSession:
    """Stands in for a loaded ``fastf1`` session; results and laps are scripted."""

    def __init__(self, results: pd.DataFrame | None = None, laps: pd.DataFrame | None = None) -> None:
        self.results = results
        self.laps = laps
        self.load_kwargs: dict | None = None

    def load(self, **kwargs: object) -> None:
        self.load_kwargs = kwargs


@pytest.fixture(autouse=True)
def _clear_caches():
    """All three loaders memoise per (year, round) for the process lifetime."""
    for cache in (sessions_module._qualifying_cache, sessions_module._practice_cache, sessions_module._sprint_cache):
        cache.clear()
    yield
    for cache in (sessions_module._qualifying_cache, sessions_module._practice_cache, sessions_module._sprint_cache):
        cache.clear()


@pytest.fixture
def fastf1_sessions(monkeypatch):
    """Serve a scripted session per session identifier and record every request."""
    scripted: dict[str, object] = {}
    requested: list[tuple[int, int, str]] = []

    def _get_session(year: int, round_num: int, name: str):
        requested.append((year, round_num, name))
        value = scripted.get(name)
        if value is None:
            raise ValueError(f"no {name} session for {year} round {round_num}")
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(sessions_module.fastf1, "get_session", _get_session)
    scripted["requested"] = requested  # type: ignore[assignment]
    return scripted


def _requested(scripted: dict) -> list[tuple[int, int, str]]:
    return scripted["requested"]  # type: ignore[return-value]


def _laps(**best_by_driver: str | None) -> pd.DataFrame:
    """A laps frame where each driver sets one lap (None meaning no valid time)."""
    return pd.DataFrame(
        [{"Driver": code, "LapTime": pd.to_timedelta(lap) if lap else pd.NaT} for code, lap in best_by_driver.items()]
    )


# ---------------------------------------------------------------------------
# Qualifying
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_qualifying_is_returned_in_grid_order_regardless_of_row_order(fastf1_sessions):
    fastf1_sessions["Q"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS))

    result = _load_qualifying(YEAR, ROUND)

    assert [row["driver_code"] for row in result] == ["VER", "LEC", "NOR"]
    assert result[0] == {
        "driver_code": "VER",
        "driver_name": "Max Verstappen",
        "team": "Red Bull",
        "position": 1,
    }


@pytest.mark.unit
def test_qualifying_is_loaded_without_telemetry_laps_or_weather(fastf1_sessions):
    session = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS))
    fastf1_sessions["Q"] = session

    _load_qualifying(YEAR, ROUND)

    # Telemetry for a full field is orders of magnitude more data than a grid
    # order needs, and would blow the prediction's time budget.
    assert session.load_kwargs == {"telemetry": False, "laps": False, "weather": False}


@pytest.mark.unit
def test_a_driver_who_set_no_qualifying_time_is_dropped_from_the_order(fastf1_sessions):
    rows = [*QUALIFYING_ROWS, {"Position": float("nan"), "Abbreviation": "HUL", "TeamName": "Sauber"}]
    fastf1_sessions["Q"] = _FakeSession(results=pd.DataFrame(rows))

    result = _load_qualifying(YEAR, ROUND)

    # A NaN position coerced to an int would put this driver on pole; the roster
    # builder re-adds him at the back instead.
    assert [row["driver_code"] for row in result] == ["VER", "LEC", "NOR"]


@pytest.mark.unit
def test_qualifying_is_loaded_from_fastf1_only_once_per_round(fastf1_sessions):
    fastf1_sessions["Q"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS))

    first = _load_qualifying(YEAR, ROUND)

    assert _load_qualifying(YEAR, ROUND) is first
    assert _requested(fastf1_sessions) == [(YEAR, ROUND, "Q")]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("results", "case"),
    [
        pytest.param(None, "session_carries_no_results", id="none"),
        pytest.param(pd.DataFrame(), "session_exists_but_is_empty", id="empty"),
    ],
)
def test_a_qualifying_session_with_no_classification_yields_no_data(fastf1_sessions, results, case):
    fastf1_sessions["Q"] = _FakeSession(results=results)

    # None, not [] — the caller distinguishes "no qualifying" (fall back to
    # practice) from "qualifying ran and nobody set a time".
    assert _load_qualifying(YEAR, ROUND) is None, case


@pytest.mark.unit
def test_a_fastf1_outage_costs_the_qualifying_signal_not_the_prediction(fastf1_sessions):
    fastf1_sessions["Q"] = ConnectionError("ergast/fastf1 unreachable")

    assert _load_qualifying(YEAR, ROUND) is None


# ---------------------------------------------------------------------------
# Practice fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_practice_ranks_drivers_by_their_fastest_lap(fastf1_sessions):
    fastf1_sessions["FP3"] = _FakeSession(
        results=pd.DataFrame(QUALIFYING_ROWS),
        laps=_laps(NOR="0 days 00:01:28.100", VER="0 days 00:01:27.500", LEC="0 days 00:01:29.000"),
    )

    result = _load_practice(YEAR, ROUND)

    assert [row["position"] for row in result] == [1, 2, 3]
    assert [row["driver_code"] for row in result] == ["VER", "NOR", "LEC"]
    # Identity is joined from the session results so the UI shows real names.
    assert result[0]["driver_name"] == "Max Verstappen"
    assert result[0]["team"] == "Red Bull"


@pytest.mark.unit
def test_a_driver_absent_from_the_practice_results_still_gets_a_row(fastf1_sessions):
    fastf1_sessions["FP3"] = _FakeSession(
        results=pd.DataFrame(QUALIFYING_ROWS),
        laps=_laps(VER="0 days 00:01:27.500", RES="0 days 00:01:31.000"),
    )

    result = _load_practice(YEAR, ROUND)

    # A Friday test driver runs laps without appearing in the classification;
    # dropping him would hand his car's pace to nobody.
    reserve = next(row for row in result if row["driver_code"] == "RES")
    assert reserve["driver_name"] == "RES"
    assert reserve["team"] == ""


@pytest.mark.unit
def test_practice_falls_back_from_fp3_to_fp2_to_fp1(fastf1_sessions):
    fastf1_sessions["FP3"] = RuntimeError("FP3 was cancelled")
    fastf1_sessions["FP2"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS), laps=pd.DataFrame())
    fastf1_sessions["FP1"] = _FakeSession(
        results=pd.DataFrame(QUALIFYING_ROWS),
        laps=_laps(LEC="0 days 00:01:30.000"),
    )

    result = _load_practice(YEAR, ROUND)

    assert [row["driver_code"] for row in result] == ["LEC"]
    assert _requested(fastf1_sessions) == [(YEAR, ROUND, "FP3"), (YEAR, ROUND, "FP2"), (YEAR, ROUND, "FP1")]


@pytest.mark.unit
def test_a_session_where_nobody_set_a_valid_lap_falls_through_to_the_next_one(fastf1_sessions):
    # A washed-out session produces lap rows with no timed lap among them.
    fastf1_sessions["FP3"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS), laps=_laps(VER=None, LEC=None))
    fastf1_sessions["FP2"] = _FakeSession(
        results=pd.DataFrame(QUALIFYING_ROWS),
        laps=_laps(NOR="0 days 00:01:29.500"),
    )

    assert [row["driver_code"] for row in _load_practice(YEAR, ROUND)] == ["NOR"]


@pytest.mark.unit
def test_a_weekend_with_no_practice_data_at_all_yields_no_proxy(fastf1_sessions):
    for name in ("FP3", "FP2", "FP1"):
        fastf1_sessions[name] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS), laps=None)

    assert _load_practice(YEAR, ROUND) is None


@pytest.mark.unit
def test_practice_pace_is_computed_once_per_round(fastf1_sessions):
    fastf1_sessions["FP3"] = _FakeSession(
        results=pd.DataFrame(QUALIFYING_ROWS),
        laps=_laps(VER="0 days 00:01:27.500"),
    )

    first = _load_practice(YEAR, ROUND)

    assert _load_practice(YEAR, ROUND) is first
    assert _requested(fastf1_sessions) == [(YEAR, ROUND, "FP3")]


# ---------------------------------------------------------------------------
# Sprint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_sprint_result_is_returned_in_finishing_order(fastf1_sessions):
    fastf1_sessions["S"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS))

    result = _load_sprint_result(YEAR, ROUND)

    assert [row["driver_code"] for row in result] == ["VER", "LEC", "NOR"]
    assert result[1]["driver_name"] == "Charles Leclerc"


@pytest.mark.unit
def test_a_sprint_retirement_is_left_out_of_the_finishing_order(fastf1_sessions):
    rows = [*QUALIFYING_ROWS, {"Position": float("nan"), "Abbreviation": "PIA", "TeamName": "McLaren"}]
    fastf1_sessions["S"] = _FakeSession(results=pd.DataFrame(rows))

    result = _load_sprint_result(YEAR, ROUND)

    # The scorer applies its own back-of-grid penalty for a missing sprint
    # result, so an unclassified driver must not appear with a real position.
    assert "PIA" not in {row["driver_code"] for row in result}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scripted", "case"),
    [
        pytest.param(_FakeSession(results=pd.DataFrame()), "sprint_session_object_but_no_classification", id="empty"),
        pytest.param(ValueError("no sprint at this round"), "conventional_weekend", id="absent"),
    ],
)
def test_a_weekend_without_a_sprint_result_is_an_empty_list_not_a_failure(fastf1_sessions, scripted, case):
    fastf1_sessions["S"] = scripted

    assert _load_sprint_result(YEAR, ROUND) == [], case


@pytest.mark.unit
def test_a_missing_sprint_is_remembered_so_every_round_is_probed_once(fastf1_sessions):
    fastf1_sessions["S"] = ValueError("no sprint at this round")

    _load_sprint_result(YEAR, ROUND)
    _load_sprint_result(YEAR, ROUND)

    # Most rounds have no sprint, so this is the common path: probing FastF1 per
    # request for a session that will never exist is pure latency.
    assert _requested(fastf1_sessions) == [(YEAR, ROUND, "S")]


@pytest.mark.unit
def test_a_loaded_sprint_result_is_reused_from_cache(fastf1_sessions):
    fastf1_sessions["S"] = _FakeSession(results=pd.DataFrame(QUALIFYING_ROWS))

    first = _load_sprint_result(YEAR, ROUND)

    assert _load_sprint_result(YEAR, ROUND) is first
    assert _requested(fastf1_sessions) == [(YEAR, ROUND, "S")]


# ---------------------------------------------------------------------------
# Has qualifying run yet?
# ---------------------------------------------------------------------------


def _event(**fields: object) -> pd.Series:
    return pd.Series(fields)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("offset_hours", "expected"),
    [(-2, True), (2, False)],
)
def test_the_explicit_qualifying_slot_decides_whether_sessions_are_probed(offset_hours, expected):
    quali_at = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    event = _event(
        Session1="Practice 1",
        Session4="Qualifying",
        Session4DateUtc=pd.Timestamp(quali_at.replace(tzinfo=None)),
        EventDate=pd.Timestamp(quali_at + timedelta(days=1)),
    )

    assert _qualifying_has_occurred(event) is expected


@pytest.mark.unit
def test_a_timezone_aware_schedule_entry_is_compared_in_utc():
    # FastF1 sometimes hands back tz-aware timestamps; naive comparison against
    # a UTC "now" would raise rather than answer.
    quali_at = datetime.now(timezone.utc) - timedelta(hours=3)
    event = _event(Session4="Qualifying", Session4DateUtc=pd.Timestamp(quali_at).tz_convert("Europe/Rome"))

    assert _qualifying_has_occurred(event) is True


@pytest.mark.unit
def test_a_plain_datetime_in_the_schedule_is_handled_like_a_timestamp():
    event = _event(Session4="Qualifying", Session4DateUtc=datetime.now(timezone.utc) - timedelta(hours=1))

    assert _qualifying_has_occurred(event) is True


@pytest.mark.unit
def test_a_qualifying_row_with_no_datetime_falls_back_to_the_race_date():
    # Named session, unknown time: the race date minus a day is the estimate.
    past = _event(Session4="Qualifying", Session4DateUtc=pd.NaT, EventDate=pd.Timestamp("2020-08-30"))
    future = _event(
        Session4="Qualifying",
        Session4DateUtc=pd.NaT,
        EventDate=pd.Timestamp(datetime.now(timezone.utc) + timedelta(days=10)),
    )

    assert _qualifying_has_occurred(past) is True
    assert _qualifying_has_occurred(future) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("days_to_race", "expected"),
    [(3, False), (2, False), (0, True), (-1, True)],
)
def test_without_a_named_qualifying_session_the_race_date_minus_a_day_is_used(days_to_race, expected):
    # Qualifying is the day before the race on a conventional weekend, so a race
    # more than a day away means the weekend has not run.
    event = _event(
        Session1="Practice 1",
        EventDate=pd.Timestamp(datetime.now(timezone.utc) + timedelta(days=days_to_race)),
    )

    assert _qualifying_has_occurred(event) is expected


@pytest.mark.unit
def test_an_unknown_schedule_attempts_the_load_rather_than_assuming_the_weekend_is_future():
    # Better to pay one failing load than to silently serve a historical-only
    # prediction for a race that has already been qualified for.
    assert _qualifying_has_occurred(_event(EventName="Unknown Grand Prix")) is True
    assert _qualifying_has_occurred(_event(Session4=None, EventDate=pd.NaT)) is True
