"""OpenF1 reads go through the session store: a finished session is asked for once.

Real R19 (Mexico City) and R20 (Sao Paulo) answers are served by a fake OpenF1. The
store itself is the conftest's private file store, so each test starts empty.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import httpx
import pytest

from app.data import openf1_stints, pit_sheet
from app.data.openf1 import client as client_module, session_store, sessions as sessions_module
from app.data.openf1.client import OpenF1LiveLockoutError, OpenF1UnavailableError, get_json
from app.data.openf1.laps import laps_from_openf1
from app.data.openf1.race_control import deleted_laps, standing_deletions
from tests.calendar_support import meetings_2026
from tests.openf1_support import NO_RESULTS, serve

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
RACE = {19: 11404, 20: 11412}
FOLDER = {19: "mexico_2026_r19", 20: "sao_paulo_2026_r20"}
SUFFIX = {19: "", 20: "_race"}
ENDPOINT_FILE = {
    "drivers": "openf1_drivers",
    "session_result": "openf1_session_result",
    "pit": "openf1_pit",
    "stints": "openf1_stints",
    "race_control": "openf1_race_control",
    "weather": "openf1_weather",
    "team_radio": "openf1_team_radio",
    "laps": "openf1_laps_first3",
}
R19_RACE_END = datetime(2026, 11, 1, 22, 0, tzinfo=UTC)


def _json(path: Path):
    return json.loads(path.read_text())


def _answer(round_num: int, endpoint: str) -> list[dict]:
    stem = ENDPOINT_FILE[endpoint]
    if round_num == 20:
        stem = "openf1_laps_race_first3" if endpoint == "laps" else f"{stem}_race"
    return _json(FIXTURES / FOLDER[round_num] / f"{stem}.json")


def _sessions_by_meeting(race_end: datetime | None = None) -> dict[str, list[dict]]:
    by_meeting = {}
    for round_num in (19, 20):
        rows = _json(FIXTURES / FOLDER[round_num] / "openf1_sessions.json")
        if race_end is not None and round_num == 19:
            rows = [{**r, "date_end": race_end.isoformat()} if r["session_key"] == RACE[19] else r for r in rows]
        by_meeting[str(rows[0]["meeting_key"])] = rows
    return by_meeting


def _routes(*, race_end: datetime | None = None, **overrides) -> dict:
    by_meeting = _sessions_by_meeting(race_end)
    by_key = {RACE[n]: n for n in RACE}

    def per_session(endpoint: str):
        def route(request: httpx.Request) -> httpx.Response:
            round_num = by_key.get(int(request.url.params["session_key"]))
            if round_num is None:
                return httpx.Response(404, json=NO_RESULTS)
            return httpx.Response(200, json=_answer(round_num, endpoint))

        return route

    routes = {
        "meetings": meetings_2026(),
        "sessions": lambda request: httpx.Response(200, json=by_meeting[request.url.params["meeting_key"]]),
        **{endpoint: per_session(endpoint) for endpoint in ENDPOINT_FILE},
    }
    return {**routes, **overrides}


@pytest.fixture(autouse=True)
def pacer_waits(monkeypatch):
    waits: list[None] = []
    monkeypatch.setattr(client_module.PACER, "wait", lambda: waits.append(None))
    monkeypatch.setattr(client_module.time, "sleep", lambda _seconds: None)
    return waits


@pytest.fixture
def fake(monkeypatch, calendar_f1db):
    """A fake OpenF1 serving R19 and R20, on every module that opens a client."""

    def install(**kwargs):
        service = serve(monkeypatch, client_module, _routes(**kwargs))
        for module in (openf1_stints, pit_sheet):
            monkeypatch.setattr(module, "new_client", client_module.new_client)
        return service

    return install


def _race_key(client, round_num: int) -> int:
    session = sessions_module.find_session(client, 2026, round_num, "R")
    assert session is not None
    return session.session_key


def _kept(endpoint: str, round_num: int = 19):
    return session_store.lookup(endpoint, RACE[round_num])[1]


def _clock(monkeypatch, at: datetime) -> None:
    monkeypatch.setattr(session_store, "now", lambda: at)


@pytest.mark.parametrize("round_num", [19, 20])
def test_r19_and_r20_fetched_twice_store_each_answer_once(fake, round_num):
    service = fake()
    with client_module.new_client() as client:
        key = _race_key(client, round_num)
        for endpoint in ENDPOINT_FILE:
            first = get_json(client, endpoint, {"session_key": key})
            second = get_json(client, endpoint, {"session_key": key})
            assert first == second == _answer(round_num, endpoint)
            assert _kept(endpoint, round_num).rows == _answer(round_num, endpoint)
            assert service.paths().count(endpoint) == 1


def test_a_second_read_of_a_finished_race_makes_no_openf1_request(fake, pacer_waits):
    service = fake()
    first = openf1_stints.openf1_race_stints(2026, 19)
    requests, waits = len(service.requests), len(pacer_waits)

    assert openf1_stints.openf1_race_stints(2026, 19) == first
    assert (len(service.requests), len(pacer_waits)) == (requests, waits)


def test_a_failed_fetch_midway_stores_only_the_complete_answers(fake):
    service = fake(drivers=httpx.Response(500))
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        get_json(client, "stints", {"session_key": key})
        with pytest.raises(OpenF1UnavailableError):
            get_json(client, "drivers", {"session_key": key})
        assert _kept("stints") is not None
        assert _kept("drivers") is None

        service.routes["drivers"] = _routes()["drivers"]
        before = len(service.requests)
        for endpoint in ("stints", "drivers", "race_control", "laps"):
            get_json(client, endpoint, {"session_key": key})
        assert service.paths()[before:] == ["drivers", "race_control", "laps"]


def test_a_session_not_yet_settled_is_never_stored(fake):
    service = fake(race_end=datetime.now(UTC) - timedelta(minutes=10))
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        get_json(client, "stints", {"session_key": key})
        get_json(client, "stints", {"session_key": key})

    assert session_store.lookup("stints", key) == (None, None)
    assert service.paths().count("stints") == 2


def test_a_query_narrower_than_the_session_passes_through(fake):
    service = fake()
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        get_json(client, "laps", {"session_key": key, "driver_number": 12})
        get_json(client, "laps", {"session_key": key, "driver_number": 12})

    assert service.paths().count("laps") == 2
    assert _kept("laps") is None


@pytest.mark.parametrize("endpoint", ["position", "intervals", "overtakes"])
def test_held_back_endpoints_are_never_stored(fake, endpoint):
    service = fake(**{endpoint: [{"driver_number": 1}]})
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        get_json(client, endpoint, {"session_key": key})
        get_json(client, endpoint, {"session_key": key})

    assert service.paths().count(endpoint) == 2
    assert _kept(endpoint) is None


def test_provisional_rows_are_refreshed_after_the_ttl_and_final_rows_never(fake, monkeypatch):
    service = fake()
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        asked = lambda: service.paths().count("stints")  # noqa: E731
        for hours, minutes, expected, provisional in [
            (1, 0, 1, True),
            (1, 10, 1, True),
            (1, 40, 2, True),
            (25, 0, 3, False),
            (80, 0, 3, False),
        ]:
            _clock(monkeypatch, R19_RACE_END + timedelta(hours=hours, minutes=minutes))
            get_json(client, "stints", {"session_key": key})
            assert asked() == expected
            assert _kept("stints").provisional is provisional


def test_a_provisional_copy_is_served_when_the_refresh_fails(fake, monkeypatch):
    service = fake()
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        _clock(monkeypatch, R19_RACE_END + timedelta(hours=1))
        rows = get_json(client, "stints", {"session_key": key})
        service.routes["stints"] = httpx.Response(401, json={"detail": "live"})
        _clock(monkeypatch, R19_RACE_END + timedelta(hours=2))

        assert get_json(client, "stints", {"session_key": key}) == rows


def test_an_empty_refresh_keeps_the_provisional_copy(fake, monkeypatch):
    service = fake()
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        _clock(monkeypatch, R19_RACE_END + timedelta(hours=1))
        rows = get_json(client, "stints", {"session_key": key})
        service.routes["stints"] = httpx.Response(404, json=NO_RESULTS)
        _clock(monkeypatch, R19_RACE_END + timedelta(hours=2))

        assert get_json(client, "stints", {"session_key": key}) == rows
        assert _kept("stints").rows == rows


def test_a_complete_weekend_is_served_without_openf1(fake):
    service = fake()
    with client_module.new_client() as client:
        first = sessions_module.weekend_sessions(client, 2026, 19)
        requests = len(service.requests)

        assert sessions_module.weekend_sessions(client, 2026, 19) == first
    assert len(service.requests) == requests
    assert [s.code for s in first] == ["FP1", "FP2", "FP3", "Q", "R"]


def test_a_weekend_with_an_unfinished_session_is_fetched_again(fake):
    service = fake(race_end=datetime.now(UTC) + timedelta(days=1))
    with client_module.new_client() as client:
        sessions_module.weekend_sessions(client, 2026, 19)
        sessions_module.weekend_sessions(client, 2026, 19)

    assert service.paths().count("sessions") == 2


def test_a_weekend_f1db_has_no_sessions_for_is_always_fetched(fake, monkeypatch):
    service = fake()
    monkeypatch.setattr(sessions_module, "weekend_schedule", lambda _year, _round: ())
    with client_module.new_client() as client:
        sessions_module.weekend_sessions(client, 2026, 19)
        sessions_module.weekend_sessions(client, 2026, 19)

    assert service.paths().count("sessions") == 2


def test_quirk_lap_rows_without_date_start_survive_the_store(fake):
    rows = _answer(19, "laps")
    undated = [{**rows[0], "date_start": None}, *rows[1:]]
    fake(laps=undated)
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        fetched = get_json(client, "laps", {"session_key": key})

    assert fetched == _kept("laps").rows == undated
    assert laps_from_openf1(_kept("laps").rows) == laps_from_openf1(undated)


def test_quirk_starting_grid_404_is_never_stored(fake):
    body = _json(FIXTURES / FOLDER[19] / "openf1_starting_grid_404.json")
    service = fake(starting_grid=httpx.Response(404, json=body))
    with client_module.new_client() as client:
        key = _race_key(client, 19)
        assert get_json(client, "starting_grid", {"session_key": key}) == []
        assert get_json(client, "starting_grid", {"session_key": key}) == []

    assert service.paths().count("starting_grid") == 2
    assert _kept("starting_grid") is None


def test_quirk_empty_stop_duration_rows_are_kept_and_skipped(fake):
    service = fake()

    assert pit_sheet._openf1_stationary(2026, 19) == {}
    assert pit_sheet._openf1_stationary(2026, 19) == {}
    assert len(_kept("pit").rows) == 67
    assert service.paths().count("pit") == 1


def test_quirk_a_live_lockout_serves_stored_sessions_and_stores_nothing(fake):
    service = fake()
    openf1_stints.openf1_race_stints(2026, 19)
    for route in list(service.routes):
        service.routes[route] = httpx.Response(401, json={"detail": "live"})
    before = len(service.requests)

    assert openf1_stints.openf1_race_stints(2026, 19)
    assert len(service.requests) == before
    with client_module.new_client() as client, pytest.raises(OpenF1LiveLockoutError):
        sessions_module.weekend_sessions(client, 2026, 20)
    assert session_store.lookup("stints", RACE[20]) == (None, None)


def test_quirk_stints_split_on_pit_lane_passes_still_merge(fake):
    fake()
    assert len(_answer(19, "stints")) == 80
    openf1_stints.openf1_race_stints(2026, 19)

    assert len(openf1_stints.openf1_race_stints(2026, 19)) == 72


def test_quirk_a_deleted_lap_is_matched_by_its_time_through_the_store(fake):
    folder = FIXTURES / "sao_paulo_2025_r21"
    sessions = _json(folder / "openf1_sessions.json")
    race = next(s for s in map(sessions_module._session, sessions) if s and s.code == "R")
    session_store.save_sessions(2025, 21, [asdict(race)])
    service = fake(race_control=_json(folder / "openf1_race_control.json"), laps=_json(folder / "openf1_laps_ant.json"))
    with client_module.new_client() as client:
        control = get_json(client, "race_control", {"session_key": race.session_key})
        laps = get_json(client, "laps", {"session_key": race.session_key})
        assert get_json(client, "laps", {"session_key": race.session_key}) == laps

    deleted = deleted_laps(standing_deletions(control), laps_from_openf1(laps), "R")
    # The message names LAP 6 and the 1:16.547 lap is lap 6 in this capture; the time, not the number, is the key.
    assert any("TIME 1:16.547 DELETED" in m["message"] and "LAP 6" in m["message"] for m in control)
    assert deleted == {(12, 6)}
    assert service.paths().count("laps") == 1
