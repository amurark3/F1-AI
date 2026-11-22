"""Measured weather beside the forecast, read through the OpenF1 store with a fake OpenF1 (R19, Mexico City)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import httpx
import pytest

from app.data.openf1 import client as client_module
from app.services.race_control import measured_weather as mw
from tests.calendar_support import meetings_2026
from tests.openf1_support import serve

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parent / "fixtures" / "mexico_2026_r19"
SESSIONS = json.loads((FIXTURE / "openf1_sessions.json").read_text())
KEYS = {row["session_name"]: row["session_key"] for row in SESSIONS}
NOW = datetime(2026, 11, 2, tzinfo=UTC)
RACE = {"round": 19}
# Hand-built readings at each session's start and end: the second is wet.
READINGS = {
    row["session_key"]: [
        {"date": row["date_start"], "track_temperature": 30.0, "air_temperature": 20.0, "rainfall": 0},
        {"date": row["date_end"], "track_temperature": 32.0, "air_temperature": 21.0, "rainfall": 1},
    ]
    for row in SESSIONS
}


@pytest.fixture(autouse=True)
def pacer(monkeypatch):
    monkeypatch.setattr(client_module.PACER, "wait", lambda: None)
    monkeypatch.setattr(client_module.time, "sleep", lambda _seconds: None)


@pytest.fixture
def fake(monkeypatch, calendar_f1db):
    def install(**overrides):
        def weather(request):
            return httpx.Response(200, json=READINGS.get(int(request.url.params["session_key"]), []))

        routes = {"meetings": meetings_2026(), "sessions": SESSIONS, "weather": weather, **overrides}
        return serve(monkeypatch, mw, routes)

    return install


def _payload(*phases):
    names = ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"]
    return {"status": "ready", "sessions": [{"name": n, "phase": p} for n, p in zip(names, phases, strict=False)]}


def test_nothing_done_makes_no_request(fake):
    service = fake()
    payload = _payload("upcoming", "live")
    before = deepcopy(payload)

    out = mw.with_measured(payload, 2026, RACE, NOW)

    assert [(r["measured"], r["measured_note"]) for r in out["sessions"]] == [(None, None), (None, mw.NOTE_AFTER_FLAG)]
    assert service.requests == []
    assert payload == before


def test_no_race_round_makes_no_request(fake):
    service = fake()
    out = mw.with_measured(_payload("done"), 2026, None, NOW)

    assert out["sessions"][0]["measured"] is None
    assert service.requests == []


def test_done_sessions_are_fetched_and_summarised(fake):
    service = fake()
    out = mw.with_measured(_payload("done", "done", "upcoming"), 2026, RACE, NOW)

    first = out["sessions"][0]
    assert first["measured"] == {
        "track_temp_c": 31.0,
        "track_temp_min_c": 30.0,
        "track_temp_max_c": 32.0,
        "air_temp_c": 20.5,
        "rainfall": [False, True],
    }
    assert first["measured_note"] is None
    assert out["sessions"][2]["measured"] is None
    assert service.paths().count("weather") == 2
    assert service.paths().count("sessions") == 1


def test_kept_sessions_need_no_sessions_request(fake):
    service = fake()
    mw.with_measured(_payload("done", "done", "done", "done"), 2026, RACE, NOW)
    service.requests.clear()

    # The live Race locks the list out, yet the kept sessions still answer.
    service.routes["sessions"] = httpx.Response(401)
    out = mw.with_measured(_payload("done", "done", "done", "done", "live"), 2026, RACE, NOW)

    assert "sessions" not in service.paths()
    assert out["sessions"][0]["measured"] is not None
    assert out["sessions"][4]["measured_note"] == mw.NOTE_AFTER_FLAG


def test_a_session_not_yet_settled_waits_for_the_flag(fake):
    fake()
    early = datetime(2026, 10, 30, 19, 31, tzinfo=UTC)
    out = mw.with_measured(_payload("done"), 2026, RACE, early)

    assert out["sessions"][0]["measured_note"] == mw.NOTE_AFTER_FLAG


def test_a_code_openf1_does_not_list_or_has_no_readings(fake):
    fake(weather=[], sessions=[row for row in SESSIONS if row["session_name"] != "Practice 2"])
    out = mw.with_measured(_payload("done", "done"), 2026, RACE, NOW)

    assert [r["measured_note"] for r in out["sessions"]] == [mw.NOTE_NO_READINGS, mw.NOTE_NO_READINGS]


def test_an_unmapped_session_name_is_not_fetched_for(fake):
    fake()
    payload = {"sessions": [{"name": "Testing", "phase": "done"}]}

    assert mw.with_measured(payload, 2026, RACE, NOW)["sessions"][0]["measured_note"] == mw.NOTE_NO_READINGS


def test_a_locked_out_session_list_marks_unresolved_rows_offline(fake):
    fake(sessions=httpx.Response(401))
    out = mw.with_measured(_payload("done", "upcoming"), 2026, RACE, NOW)

    assert out["sessions"][0]["measured_note"] == mw.NOTE_OFFLINE
    assert out["sessions"][1]["measured_note"] is None


def test_one_failing_weather_call_marks_only_its_row(fake):
    def weather(request):
        key = int(request.url.params["session_key"])
        return httpx.Response(401) if key == KEYS["Practice 1"] else httpx.Response(200, json=READINGS[key])

    fake(weather=weather)
    out = mw.with_measured(_payload("done", "done"), 2026, RACE, NOW)

    assert out["sessions"][0]["measured_note"] == mw.NOTE_OFFLINE
    assert out["sessions"][1]["measured"] is not None
