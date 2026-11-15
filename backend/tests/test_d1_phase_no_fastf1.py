"""D1 phase Accept: a fresh process makes zero FastF1 requests, and no cap error reaches a response.

The app boots as a fresh process would (lifespan: warm-up, the grading pass, the f1db refresh), then a
pre- and a post-qualifying compute for R20 (Sao Paulo 2026) run and a Stints request is served. OpenF1
answers from the real captures in ``fixtures/sao_paulo_2026_r20/`` and the network is blocked. FastF1 is
counted at its own request limiter, which every request it sends passes, and at its entry points.
"""

from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import time
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
import fastf1
from fastf1 import req as fastf1_req
from fastf1.exceptions import RateLimitExceededError
import httpx
import pytest
import requests

from app.data import f1db_source, race_stints
from app.data.openf1 import client as openf1_client
from app.data.predictions import history
from app.data.race_stints_store import RaceStintsStore
from app.services import readiness, self_improvement
import main
from tests.calendar_support import CALENDAR, INSERT_RACE, SCHEMA, meetings_2026
from tests.f1db_fixture import build_f1db
from tests.openf1_support import NO_RESULTS, FakeOpenF1
from tests.sao_paulo_2026_support import FIXTURES

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

PRACTICE_3, QUALIFYING, RACE = 11407, 11408, 11412
# endpoint -> session_key -> capture
CAPTURES = {
    "drivers": {11405: "practice1", QUALIFYING: "qualifying", PRACTICE_3: "practice3", RACE: "race"},
    "session_result": {QUALIFYING: "qualifying", RACE: "race"},
    "laps": {PRACTICE_3: "practice3", RACE: "race_first3"},
    "race_control": {PRACTICE_3: "practice3", RACE: "race"},
    "pit": {RACE: "race"},
    "stints": {RACE: "race"},
    "weather": {RACE: "race"},
    "team_radio": {RACE: "race"},
}


def _capture(endpoint: str, session_key: int) -> list[dict] | None:
    name = CAPTURES[endpoint].get(session_key)
    return None if name is None else json.loads((FIXTURES / f"openf1_{endpoint}_{name}.json").read_text())


def _route(endpoint: str):
    def serve(request: httpx.Request) -> httpx.Response:
        rows = _capture(endpoint, int(request.url.params["session_key"]))
        return httpx.Response(404, json=NO_RESULTS) if rows is None else httpx.Response(200, json=rows)

    return serve


def _routes(**overrides) -> dict:
    sessions = json.loads((FIXTURES / "openf1_sessions.json").read_text())
    return {
        "meetings": meetings_2026(),
        "sessions": sessions,
        **{endpoint: _route(endpoint) for endpoint in CAPTURES},
        **overrides,
    }


class FastF1Counter:
    """Every FastF1 request, counted where FastF1 itself would limit it, and every entry-point call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def entry_point(self, name: str):
        def refuse(*_args, **_kwargs):
            self.calls.append(name)
            raise RuntimeError(f"fastf1.{name} called")

        return refuse


@pytest.fixture
def fastf1_counter(monkeypatch) -> FastF1Counter:
    counter = FastF1Counter()
    monkeypatch.setattr(fastf1, "get_session", counter.entry_point("get_session"))
    monkeypatch.setattr(fastf1, "get_event_schedule", counter.entry_point("get_event_schedule"))
    monkeypatch.setattr(fastf1.core.Session, "load", counter.entry_point("Session.load"))
    monkeypatch.setattr(fastf1_req._CallsPerIntervalLimitRaise, "limit", lambda _self: counter.calls.append("limiter"))
    return counter


_RESHAPE = """
    DROP TABLE race; DROP TABLE grand_prix; DROP TABLE circuit; DROP TABLE country;
    ALTER TABLE race_data ADD COLUMN driver_number;
    ALTER TABLE race_data ADD COLUMN pit_stop_stop;
    ALTER TABLE race_data ADD COLUMN pit_stop_lap;
    ALTER TABLE race_data ADD COLUMN pit_stop_time;
    ALTER TABLE race_data ADD COLUMN pit_stop_time_millis;
"""


def _season_f1db(path: Path) -> Path:
    """The shared f1db schema, without results, holding the captured 2026 calendar."""
    build_f1db(path, seed=False)
    data = json.loads(CALENDAR.read_text())
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(_RESHAPE + SCHEMA + "ALTER TABLE grand_prix ADD COLUMN name;")
        conn.executemany(INSERT_RACE, data["races"])
        conn.executemany(
            "INSERT INTO grand_prix (id, full_name, name) VALUES (?, ?, ?)", [(*g, g[1]) for g in data["grands_prix"]]
        )
        conn.executemany("INSERT INTO circuit VALUES (?, ?, ?)", data["circuits"])
        conn.executemany("INSERT INTO country VALUES (?, ?)", data["countries"])
        conn.commit()
    return path


@pytest.fixture
def openf1(monkeypatch, tmp_path) -> FakeOpenF1:
    """OpenF1 served from the captures, to every client any module opens (no pacing, no sleeping)."""
    monkeypatch.setattr(f1db_source, "DB_PATH", _season_f1db(tmp_path / "season.db"))
    fake = FakeOpenF1(_routes())
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda _self, request: fake(request))
    monkeypatch.setattr(openf1_client.PACER, "wait", lambda: None)
    monkeypatch.setattr(openf1_client.time, "sleep", lambda _seconds: None)
    return fake


@pytest.fixture
def fresh_process(monkeypatch, isolated_data_dir):
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "PREFETCH_STARTUP_DELAY", 0)
    monkeypatch.setattr(f1db_source, "sync_to_latest", lambda: None)
    monkeypatch.setattr(readiness, "_state", readiness._INITIAL_STATE)
    monkeypatch.setattr(race_stints, "_cache", {})
    monkeypatch.setattr(race_stints, "_empty_until", {})
    monkeypatch.setattr(race_stints, "stint_store", RaceStintsStore())


@pytest.fixture
def ungraded_r20(fresh_process):
    """R20's stored call as production held it, before anything graded it."""
    stored = json.loads((FIXTURES / "prediction_history_entry.json").read_text())["entry"]
    ungraded = {k: v for k, v in stored.items() if not k.startswith("actual_")}
    history._save_prediction_history({"(2026,20)": ungraded})


@pytest.fixture
def grading_passes(monkeypatch) -> list[dict]:
    """The real self-improvement pass, recording each result."""
    passes: list[dict] = []
    real = self_improvement.run_self_improvement_pass

    def record(year: int) -> dict:
        passes.append(real(year))
        return passes[-1]

    monkeypatch.setattr(self_improvement, "run_self_improvement_pass", record)
    return passes


def _wait_until(done, what: str) -> None:
    deadline = time.monotonic() + 30
    while not done():
        assert time.monotonic() < deadline, f"{what} never finished"
        time.sleep(0.05)


def test_boot_grading_two_computes_and_a_stints_request_make_no_fastf1_request(
    fastf1_counter, openf1, ungraded_r20, grading_passes
):
    with TestClient(main.app) as client:
        _wait_until(lambda: readiness.current_state().ready and grading_passes, "warm-up or the grading pass")
        computed = {
            phase: client.post(f"/api/predictions/2026/20/compute?phase={phase}").json()
            for phase in ("pre_qualifying", "post_qualifying")
        }
        stints = client.get("/api/race-control/stints/2026/20").json()

    assert grading_passes[0]["actuals_recorded"] == 1
    graded = history._load_prediction_history()["(2026,20)"]
    assert graded["actual_source"] == "openf1-session-result"
    for phase, body in computed.items():
        assert body["prediction_phase"] == phase
        assert body["cache"]["status"] == "stored"
        assert len(body["predictions"]) == 22
    assert stints["available"]
    assert stints["has_stints"]
    assert fastf1_counter.calls == []


def test_the_counter_sees_a_request_fastf1_would_send(fastf1_counter):
    session = fastf1_req._SessionWithRateLimiting()
    with pytest.raises(requests.RequestException):
        session.send(requests.Request("GET", "https://api.example.com/x").prepare())
    assert fastf1_counter.calls == ["limiter"]


def test_a_cap_error_from_the_live_stints_fallback_never_reaches_the_response(monkeypatch, openf1, fresh_process):
    """OpenF1 answers 401 during a live session; FastF1, the one path left, is out of requests."""
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "handle_request",
        lambda _self, request: FakeOpenF1(_routes(stints=httpx.Response(401, json={"detail": "live"})))(request),
    )
    asked: list[str] = []

    def capped(*_args, **_kwargs):
        asked.append("get_session")
        raise RateLimitExceededError("any API: 500 calls/h")

    monkeypatch.setattr(fastf1, "get_session", capped)

    with TestClient(main.app) as client:
        response = client.get("/api/race-control/stints/2026/20")

    assert asked == ["get_session"]
    assert response.status_code == 200
    body = response.json()
    assert body["has_stints"] is False
    assert "calls/h" not in response.text
