"""Tests for app.api.race_detail — the one endpoint that does heavy FastF1 work.

Three design decisions carry the risk here, and each is asserted rather than
assumed:

* **Sessions load independently.** A weekend where qualifying is missing must
  still return the race classification; one failed load leaves its own key
  ``None`` instead of emptying the response. That is the difference between a
  partly-populated page and a blank one.
* **A race is only "complete" three hours after its start.** Loading results
  earlier gets a partial or empty classification from FastF1 and would cache it,
  so the buffer is what stops a red-flagged race being frozen mid-race.
* **Only successful-enough responses are cached.** The cache is never evicted,
  so caching an error would pin it for the life of the process.

FastF1 is mocked at the boundary throughout; the network is blocked.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app.api import race_detail as rd
from app.api.race_detail import (
    _classification_rows,
    _classification_time,
    _event_date,
    _fmt_td,
    _full_name,
    _qualifying_phases,
    _race_gap,
    _race_start,
    _session_names,
    _session_schedule,
    build_race_detail,
)

RACE_START = datetime(2026, 3, 8, 12, 0)


@pytest.fixture(autouse=True)
def _clear_cache():
    """The detail cache is module-global and is never evicted."""
    rd.race_detail_cache.clear()
    yield
    rd.race_detail_cache.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rd.router)
    return TestClient(app)


def _event_row(**overrides) -> pd.Series:
    data = {
        "RoundNumber": 1,
        "EventName": "Bahrain Grand Prix",
        "Location": "Sakhir",
        "Country": "Bahrain",
        "EventDate": pd.Timestamp("2026-03-08"),
        "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp(RACE_START - timedelta(days=2)),
        "Session2": "Qualifying",
        "Session2DateUtc": pd.Timestamp(RACE_START - timedelta(days=1)),
        "Session3": "Race",
        "Session3DateUtc": pd.Timestamp(RACE_START),
        "Session4": None,
        "Session4DateUtc": pd.NaT,
        "Session5": None,
        "Session5DateUtc": pd.NaT,
    }
    data.update(overrides)
    return pd.Series(data)


def _results_frame(**overrides) -> pd.DataFrame:
    rows = [
        {
            "Position": 1.0,
            "Abbreviation": "VER",
            "FirstName": "Max",
            "LastName": "Verstappen",
            "TeamName": "Red Bull",
            "GridPosition": 1.0,
            "Time": pd.Timedelta(hours=1, minutes=31, seconds=44, milliseconds=742),
            "Points": 25.0,
            "Status": "Finished",
            "Q1": pd.Timedelta(seconds=89.1),
            "Q2": pd.Timedelta(seconds=88.5),
            "Q3": pd.Timedelta(seconds=87.9),
        },
        {
            "Position": 2.0,
            "Abbreviation": "LEC",
            "FirstName": "Charles",
            "LastName": "Leclerc",
            "TeamName": "Ferrari",
            "GridPosition": 3.0,
            "Time": pd.Timedelta(seconds=12, milliseconds=345),
            "Points": 18.0,
            "Status": "Finished",
            "Q1": pd.Timedelta(seconds=89.6),
            "Q2": pd.Timedelta(seconds=88.9),
            "Q3": pd.Timedelta(seconds=88.3),
        },
        {
            "Position": float("nan"),
            "Abbreviation": "NOR",
            "FirstName": "Lando",
            "LastName": "Norris",
            "TeamName": "McLaren",
            "GridPosition": 0.0,
            "Time": pd.NaT,
            "Points": float("nan"),
            "Status": "Engine",
            "Q1": pd.Timedelta(seconds=90.0),
            "Q2": pd.NaT,
            "Q3": pd.NaT,
        },
    ]
    frame = pd.DataFrame(rows)
    for key, value in overrides.items():
        frame[key] = value
    return frame


def _install_fastf1(monkeypatch, *, schedule=None, sessions=None, now=None):
    """Point the module at a scripted schedule and per-identifier results."""
    frame = schedule if schedule is not None else pd.DataFrame([_event_row()])
    monkeypatch.setattr(rd.fastf1, "get_event_schedule", lambda year, include_testing: frame)

    table = sessions if sessions is not None else {}

    def load(year, round_num, identifier):
        outcome = table.get(identifier)
        if outcome is None:
            raise ValueError(f"no {identifier} session")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(rd, "_load_session_results", load)

    if now is not None:
        _freeze_now(monkeypatch, now)


def _freeze_now(monkeypatch, when: datetime) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz) if tz else when

    monkeypatch.setattr(rd, "datetime", _FrozenDatetime)


AFTER_RACE = RACE_START + timedelta(hours=4)
BEFORE_RACE = RACE_START - timedelta(days=3)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_lap_time_renders_as_a_dash():
    assert _fmt_td(pd.NaT) == "-"


@pytest.mark.unit
def test_lap_time_drops_the_leading_hour_component():
    assert _fmt_td(pd.Timedelta(minutes=1, seconds=27, milliseconds=900)) == "01:27.900"


@pytest.mark.unit
def test_a_long_lap_time_is_truncated_to_millisecond_precision():
    # pandas renders nanoseconds; the UI only ever shows thousandths.
    assert len(_fmt_td(pd.Timedelta(hours=1, minutes=27, seconds=9, microseconds=123456))) <= 10


@pytest.mark.unit
def test_race_gap_is_trimmed_to_milliseconds():
    # Only the leading "00:" hour group is stripped, so a sub-minute gap keeps
    # its minutes field: "0 days 00:00:12.345678" -> "00:12.345".
    assert _race_gap(pd.Timedelta(seconds=12, microseconds=345678)) == "00:12.345"


@pytest.mark.unit
def test_race_gap_without_a_fraction_is_left_alone():
    assert _race_gap(pd.Timedelta(minutes=1)) == "01:00"


@pytest.mark.unit
def test_full_name_joins_both_halves():
    assert _full_name(pd.Series({"FirstName": "Max", "LastName": "Verstappen"})) == "Max Verstappen"


@pytest.mark.unit
@pytest.mark.parametrize(
    "entry",
    [{"FirstName": "Max"}, {"LastName": "Verstappen"}, {}],
    ids=["first-only", "last-only", "neither"],
)
def test_full_name_tolerates_a_missing_half(entry):
    assert "  " not in _full_name(pd.Series(entry, dtype=object))


@pytest.mark.unit
def test_event_date_gains_a_utc_designator():
    assert _event_date(_event_row()) == "2026-03-08T00:00:00Z"


@pytest.mark.unit
def test_an_offset_event_date_is_left_alone():
    row = _event_row(EventDate=pd.Timestamp("2026-03-08T00:00:00+02:00"))

    assert _event_date(row) == "2026-03-08T00:00:00+02:00"


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_session_schedule_reports_every_dated_session_in_utc():
    sessions = _session_schedule(_event_row())

    assert sessions == {
        "Practice 1": "2026-03-06T12:00:00Z",
        "Qualifying": "2026-03-07T12:00:00Z",
        "Race": "2026-03-08T12:00:00Z",
    }


@pytest.mark.unit
def test_session_schedule_skips_an_undated_session():
    assert "Race" not in _session_schedule(_event_row(Session3DateUtc=pd.NaT))


@pytest.mark.unit
def test_session_names_lists_only_named_slots():
    assert _session_names(_event_row()) == ["Practice 1", "Qualifying", "Race"]


@pytest.mark.unit
def test_race_start_finds_the_race_session():
    assert _race_start(_event_row()) == RACE_START


@pytest.mark.unit
def test_race_start_is_none_when_the_race_has_no_date():
    assert _race_start(_event_row(Session3DateUtc=pd.NaT)) is None


@pytest.mark.unit
def test_race_start_is_none_when_there_is_no_race_session():
    assert _race_start(_event_row(Session3="Sprint")) is None


# ---------------------------------------------------------------------------
# Classification building
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classification_reports_position_grid_and_points():
    rows = _classification_rows(_results_frame(), _race_gap)

    assert rows[0]["position"] == 1
    assert rows[0]["driver"] == "VER"
    assert rows[0]["grid"] == 1
    assert rows[0]["points"] == 25.0


@pytest.mark.unit
def test_an_unclassified_car_has_a_null_position_and_zero_points():
    rows = _classification_rows(_results_frame(), _race_gap)

    assert rows[2]["position"] is None
    assert rows[2]["points"] == 0


@pytest.mark.unit
def test_a_pit_lane_start_is_reported_as_no_grid_slot():
    """FastF1 encodes a pit-lane start as grid 0, which is not position zero."""
    rows = _classification_rows(_results_frame(), _race_gap)

    assert rows[2]["grid"] is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Finished", "00:12.345"),
        ("+1 Lap", "+1 Lap"),
        ("Engine", "DNF - Engine"),
        ("Collision", "DNF - Collision"),
    ],
    ids=["finished", "lapped", "mechanical", "incident"],
)
def test_classification_time_distinguishes_finish_lap_and_retirement(status, expected):
    value = pd.Timedelta(seconds=12, microseconds=345678)

    assert _classification_time(status, value, _race_gap) == expected


@pytest.mark.unit
def test_a_finisher_without_a_time_renders_empty():
    assert _classification_time("Finished", pd.NaT, _race_gap) == ""


@pytest.mark.unit
def test_qualifying_orders_each_phase_by_lap_time():
    phases = _qualifying_phases(_results_frame())

    assert [row["driver"] for row in phases["Q1"]] == ["VER", "LEC", "NOR"]
    assert phases["Q1"][0]["position"] == 1


@pytest.mark.unit
def test_a_phase_nobody_set_a_time_in_is_omitted():
    frame = _results_frame()
    frame["Q3"] = pd.NaT

    assert "Q3" not in _qualifying_phases(frame)


@pytest.mark.unit
def test_a_phase_column_that_is_absent_entirely_is_skipped():
    frame = _results_frame().drop(columns=["Q2", "Q3"])

    assert set(_qualifying_phases(frame)) == {"Q1"}


@pytest.mark.unit
def test_qualifying_is_none_when_no_phase_produced_times():
    frame = _results_frame()
    for phase in ("Q1", "Q2", "Q3"):
        frame[phase] = pd.NaT

    assert _qualifying_phases(frame) is None


# ---------------------------------------------------------------------------
# build_race_detail
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_unknown_round_is_reported(monkeypatch):
    _install_fastf1(monkeypatch, now=AFTER_RACE)

    assert build_race_detail(2026, 99) == {"error": "Round 99 not found for 2026"}


@pytest.mark.unit
def test_a_future_race_returns_metadata_without_loading_any_session(monkeypatch):
    """Loading before the race would cache an empty classification."""
    _install_fastf1(
        monkeypatch,
        sessions={"R": AssertionError("no session may be loaded before the race")},
        now=BEFORE_RACE,
    )

    detail = build_race_detail(2026, 1)

    assert detail["race_results"] is None
    assert detail["circuit"]["circuit_name"] == "Bahrain International Circuit"
    assert detail["sessions"]["Race"] == "2026-03-08T12:00:00Z"


@pytest.mark.unit
def test_a_race_still_running_is_not_treated_as_complete(monkeypatch):
    _install_fastf1(
        monkeypatch,
        sessions={"R": AssertionError("a race in progress must not be loaded")},
        now=RACE_START + timedelta(hours=1),
    )

    assert build_race_detail(2026, 1)["race_results"] is None


@pytest.mark.unit
def test_an_event_without_a_dated_race_never_loads_results(monkeypatch):
    _install_fastf1(
        monkeypatch,
        schedule=pd.DataFrame([_event_row(Session3DateUtc=pd.NaT)]),
        sessions={"R": AssertionError("must not load without a race time")},
        now=AFTER_RACE,
    )

    assert build_race_detail(2026, 1)["race_results"] is None


@pytest.mark.unit
def test_a_completed_race_returns_classification_podium_and_qualifying(monkeypatch):
    _install_fastf1(monkeypatch, sessions={"R": _results_frame(), "Q": _results_frame()}, now=AFTER_RACE)

    detail = build_race_detail(2026, 1)

    assert [row["driver"] for row in detail["race_results"]] == ["VER", "LEC", "NOR"]
    assert [row["driver"] for row in detail["podium"]] == ["VER", "LEC"]
    assert detail["qualifying"]["Q3"][0]["driver"] == "VER"


@pytest.mark.unit
def test_the_podium_excludes_unclassified_cars(monkeypatch):
    _install_fastf1(monkeypatch, sessions={"R": _results_frame(), "Q": _results_frame()}, now=AFTER_RACE)

    podium = build_race_detail(2026, 1)["podium"]

    assert all(row["position"] is not None for row in podium)


@pytest.mark.unit
def test_a_failed_race_load_leaves_only_that_key_null(monkeypatch):
    """One missing session must not empty the whole response."""
    _install_fastf1(monkeypatch, sessions={"Q": _results_frame()}, now=AFTER_RACE)

    detail = build_race_detail(2026, 1)

    assert detail["race_results"] is None
    assert detail["podium"] is None
    assert detail["qualifying"] is not None, "qualifying must survive a failed race load"


@pytest.mark.unit
def test_a_failed_qualifying_load_leaves_the_race_intact(monkeypatch):
    _install_fastf1(monkeypatch, sessions={"R": _results_frame()}, now=AFTER_RACE)

    detail = build_race_detail(2026, 1)

    assert detail["race_results"] is not None
    assert detail["qualifying"] is None


@pytest.mark.unit
def test_a_normal_weekend_carries_no_sprint_keys(monkeypatch):
    _install_fastf1(monkeypatch, sessions={"R": _results_frame(), "Q": _results_frame()}, now=AFTER_RACE)

    detail = build_race_detail(2026, 1)

    assert detail["is_sprint"] is False
    assert detail["sprint_results"] is None
    assert detail["sprint_qualifying"] is None


@pytest.mark.unit
def test_a_sprint_weekend_loads_both_sprint_sessions(monkeypatch):
    _install_fastf1(
        monkeypatch,
        schedule=pd.DataFrame([_event_row(Session4="Sprint", Session4DateUtc=pd.Timestamp(RACE_START))]),
        sessions={"R": _results_frame(), "Q": _results_frame(), "S": _results_frame(), "SQ": _results_frame()},
        now=AFTER_RACE,
    )

    detail = build_race_detail(2026, 1)

    assert detail["is_sprint"] is True
    assert [row["driver"] for row in detail["sprint_results"]] == ["VER", "LEC", "NOR"]
    assert detail["sprint_qualifying"]["Q1"][0]["driver"] == "VER"


@pytest.mark.unit
def test_a_failed_sprint_load_leaves_the_race_intact(monkeypatch):
    _install_fastf1(
        monkeypatch,
        schedule=pd.DataFrame([_event_row(Session4="Sprint", Session4DateUtc=pd.Timestamp(RACE_START))]),
        sessions={"R": _results_frame(), "Q": _results_frame()},
        now=AFTER_RACE,
    )

    detail = build_race_detail(2026, 1)

    assert detail["sprint_results"] is None
    assert detail["sprint_qualifying"] is None
    assert detail["race_results"] is not None


@pytest.mark.unit
def test_an_empty_sprint_classification_is_reported_as_none(monkeypatch):
    _install_fastf1(
        monkeypatch,
        schedule=pd.DataFrame([_event_row(Session4="Sprint", Session4DateUtc=pd.Timestamp(RACE_START))]),
        sessions={
            "R": _results_frame(),
            "Q": _results_frame(),
            "S": _results_frame().iloc[0:0],
            "SQ": _results_frame(),
        },
        now=AFTER_RACE,
    )

    assert build_race_detail(2026, 1)["sprint_results"] is None


@pytest.mark.unit
def test_the_session_loader_serialises_fastf1_work(monkeypatch):
    """FastF1 is not thread-safe for concurrent session loads."""
    loaded: list[tuple] = []

    class _FakeSession:
        results = "results-frame"

        def load(self, **kwargs):
            loaded.append(kwargs)

    monkeypatch.setattr(rd.fastf1, "get_session", lambda *args: _FakeSession())

    assert rd._load_session_results(2026, 1, "R") == "results-frame"
    # Telemetry is the expensive part and is never needed for a classification.
    assert loaded == [{"telemetry": False, "laps": False, "weather": False}]
    assert not rd._fastf1_lock.locked(), "the lock must be released after the load"


# ---------------------------------------------------------------------------
# The HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_endpoint_returns_and_caches_a_built_detail(client, monkeypatch):
    calls: list[int] = []

    def build(year, round_num):
        calls.append(round_num)
        return {"round": round_num, "circuit": {"circuit_name": "Bahrain International Circuit"}}

    monkeypatch.setattr(rd, "build_race_detail", build)

    first = client.get("/race/2026/1").json()
    second = client.get("/race/2026/1").json()

    assert first == second
    assert calls == [1], "a cached weekend must not be rebuilt"


@pytest.mark.unit
def test_a_detail_without_circuit_metadata_is_not_cached(client, monkeypatch):
    """Caching a half-built response would pin it for the process lifetime."""
    calls: list[int] = []

    def build(year, round_num):
        calls.append(round_num)
        return {"round": round_num, "circuit": None}

    monkeypatch.setattr(rd, "build_race_detail", build)

    client.get("/race/2026/1")
    client.get("/race/2026/1")

    assert calls == [1, 1]
    assert rd.race_detail_cache == {}


@pytest.mark.unit
def test_an_error_response_is_not_cached(client, monkeypatch):
    monkeypatch.setattr(rd, "build_race_detail", lambda year, round_num: {"error": "Round 99 not found for 2026"})

    client.get("/race/2026/99")

    assert rd.race_detail_cache == {}


@pytest.mark.unit
def test_a_timeout_is_reported_as_retryable(client, monkeypatch):
    def slow(year, round_num):
        raise asyncio.TimeoutError

    monkeypatch.setattr(rd, "build_race_detail", slow)

    body = client.get("/race/2026/1").json()

    assert body["timeout"] is True
    # A timeout is retry-able, not a server fault, so it mints no error id.
    assert "error_id" not in body


@pytest.mark.unit
def test_a_load_failure_returns_a_client_safe_error(client, monkeypatch):
    def explode(year, round_num):
        raise ValueError("/opt/render/project/src/backend/f1_cache/2026/qual.ff1 missing")

    monkeypatch.setattr(rd, "build_race_detail", explode)

    body = client.get("/race/2026/1").json()

    assert "error_id" in body
    assert "/opt/render" not in str(body)


@pytest.mark.unit
def test_race_detail_shares_the_fastf1_timeout_budget():
    assert rd.FASTF1_TIMEOUT == rd.FASTF1_TIMEOUT_SECONDS
