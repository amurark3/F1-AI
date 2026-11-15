"""Tests for app.data.jolpica: the direct Jolpica client and its pacer.

The rows are Jolpica's real answers, captured under ``tests/fixtures/`` (Mexico
2026 pit sheet, results and standings; the Sao Paulo 2026 qualifying table). The
HTTP boundary is a fake that wraps them the way Jolpica does, paging at 30 rows
as it does when not asked for more. Nothing sleeps: the pacer runs on a fake clock.
"""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import httpx
import pytest

from app.data import jolpica
from app.data.jolpica import JolpicaUnavailableError, Pacer

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
MEXICO = FIXTURES / "mexico_2026_r19"
PAGE = 30


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def served(monkeypatch):
    """``httpx.get`` answering from ``state["answers"]`` (path suffix -> MRData, status or exception)."""
    state: dict = {"answers": {}, "requests": []}
    monkeypatch.setattr(jolpica, "PACER", Pacer(clock=lambda: 0.0, sleep=lambda _s: None))

    def get(url: str, params: dict | None = None, timeout: float = 0) -> httpx.Response:
        state["requests"].append((url, params))
        answer = next(value for key, value in state["answers"].items() if url.endswith(f"{key}.json"))
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx.Response(answer, json={})
        if isinstance(answer, str):
            return httpx.Response(200, text=answer)
        return httpx.Response(200, json={"MRData": answer})

    monkeypatch.setattr(jolpica.httpx, "get", get)
    return state


def race_table(key: str, rows: list[dict], params_of: dict | None = None) -> dict:
    """The answer for a race table, paged at 30 rows from the offset asked for."""
    return {"RaceTable": {"Races": [{key: rows}]}, "total": str(len(rows))}


def paged(key: str, rows: list[dict]):
    def answer(params: dict) -> dict:
        offset = int(params["offset"])
        return {"RaceTable": {"Races": [{key: rows[offset : offset + PAGE]}]}, "total": str(len(rows))}

    return answer


@pytest.fixture
def paging(served, monkeypatch):
    """Like ``served`` but each answer may be a function of the request's params."""
    real = jolpica.httpx.get

    def get(url: str, params: dict | None = None, timeout: float = 0) -> httpx.Response:
        answer = next(value for key, value in served["paged"].items() if url.endswith(f"{key}.json"))
        served["requests"].append((url, params))
        return httpx.Response(200, json={"MRData": answer(params)})

    served["paged"] = {}
    monkeypatch.setattr(jolpica.httpx, "get", get)
    yield served
    monkeypatch.setattr(jolpica.httpx, "get", real)


# --- the pacer ---------------------------------------------------------------------------


def test_a_burst_of_five_requests_waits_for_the_one_second_window():
    clock = FakeClock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)

    for _ in range(5):
        pacer.wait()

    # Four start at once; the fifth is a full second after the first.
    assert clock.slept == [1.0]


def test_requests_a_second_apart_never_sleep():
    clock = FakeClock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)

    for _ in range(12):
        pacer.wait()
        clock.now += 0.3

    assert clock.slept == []


def test_the_five_hundred_and_first_request_in_an_hour_is_refused_not_slept_on():
    clock = FakeClock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)
    for _ in range(jolpica.HOURLY_REQUESTS):
        pacer.wait()
        clock.now += 1.0  # 1/s keeps the burst window quiet

    # 500 starts in the last 500 s: the next is over budget.
    with pytest.raises(JolpicaUnavailableError, match="500 requests an hour"):
        pacer.wait()


def test_the_hourly_budget_comes_back_as_old_requests_age_out():
    clock = FakeClock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)
    for _ in range(jolpica.HOURLY_REQUESTS):
        pacer.wait()
        clock.now += 1.0
    clock.now += jolpica.HOUR_SECONDS

    pacer.wait()


# --- pit stops ---------------------------------------------------------------------------


def test_the_mexico_pit_sheet_is_read_across_pages(paging):
    rows = load(MEXICO / "jolpica_pitstops.json")["PitStops"]
    paging["paged"]["2026/19/pitstops"] = paged("PitStops", rows)

    stops = jolpica.pit_stops(2026, 19)

    assert len(stops) == 58
    assert [params["offset"] for _url, params in paging["requests"]] == [0, 30]
    assert paging["requests"][0][1]["limit"] == jolpica.PAGE_LIMIT
    assert stops[0] == {"driverId": "alonso", "lap": 3, "stop": 1, "duration": timedelta(seconds=23.958)}


def test_a_red_flag_suspension_entry_keeps_its_minutes(paging):
    rows = load(MEXICO / "jolpica_pitstops.json")["PitStops"]
    paging["paged"]["2026/19/pitstops"] = paged("PitStops", rows)

    verstappen = next(
        row for row in jolpica.pit_stops(2026, 19) if row["driverId"] == "max_verstappen" and row["lap"] == 45
    )

    assert verstappen["duration"] == timedelta(minutes=38, seconds=34.937)


def test_an_untimed_entry_has_no_duration(served):
    served["answers"]["2026/19/pitstops"] = race_table("PitStops", [{"driverId": "alonso", "lap": "3", "stop": "1"}])

    assert jolpica.pit_stops(2026, 19)[0]["duration"] is None


def test_a_race_with_no_table_yet_is_empty(served):
    served["answers"]["2026/21/pitstops"] = {"RaceTable": {"Races": []}, "total": "0"}

    assert jolpica.pit_stops(2026, 21) == []


def test_a_row_missing_its_lap_is_an_error_not_a_gap(served):
    served["answers"]["2026/19/pitstops"] = race_table("PitStops", [{"driverId": "alonso"}])

    with pytest.raises(JolpicaUnavailableError, match="pitstops: unreadable row"):
        jolpica.pit_stops(2026, 19)


# --- results and the provisional grid --------------------------------------------------------


def test_mexico_results_read_flat(served):
    served["answers"]["2026/19/results"] = race_table("Results", load(MEXICO / "jolpica_results.json")["Results"])

    rows = jolpica.race_results(2026, 19)

    assert len(rows) == 22
    assert rows[0] == {
        "driverId": "max_verstappen",
        "driverCode": "VER",
        "position": 1,
        "positionText": "1",
        "grid": 5,
        "laps": 71,
        "status": "Finished",
    }


def test_a_result_row_without_a_grid_is_an_error(served):
    served["answers"]["2026/19/results"] = race_table("Results", [{"position": "1"}])

    with pytest.raises(JolpicaUnavailableError, match="results: unreadable row"):
        jolpica.race_results(2026, 19)


def test_the_provisional_grid_is_qualifying_order_labelled_with_its_source(served):
    qualifying = load(FIXTURES / "sao_paulo_2026_r20" / "jolpica_qualifying.json")["QualifyingResults"]
    served["answers"]["2026/20/qualifying"] = race_table("QualifyingResults", qualifying)

    grid = jolpica.provisional_grid(2026, 20)

    assert grid[0] == {"position": 1, "driverCode": "NOR", "provisional": True, "source": jolpica.QUALIFYING_SOURCE}
    assert [row["position"] for row in grid] == list(range(1, len(qualifying) + 1))
    assert all(row["provisional"] for row in grid)


def test_a_qualifying_row_without_a_driver_is_an_error(served):
    served["answers"]["2026/20/qualifying"] = race_table("QualifyingResults", [{"position": "1"}])

    with pytest.raises(JolpicaUnavailableError, match="qualifying: unreadable row"):
        jolpica.provisional_grid(2026, 20)


# --- standings ---------------------------------------------------------------------------


def responses() -> dict:
    return load(MEXICO / "jolpica_ergast_responses.json")["responses"]


def test_mexico_driver_standings_read_code_and_points(served):
    served["answers"]["2026/19/driverstandings"] = responses()["2026/driverStandings"]["MRData"]

    rows = jolpica.driver_standings(2026, 19)

    assert len(rows) == 24
    assert rows[0] == {"driverCode": "ANT", "points": 380.0}


def test_mexico_constructor_standings_read_name_and_points(served):
    served["answers"]["2026/19/constructorstandings"] = responses()["2026/constructorStandings"]["MRData"]

    rows = jolpica.constructor_standings(2026, 19)

    assert len(rows) == 11
    assert rows[0] == {"constructorName": "Mercedes", "points": 630.0}


def test_standings_before_jolpica_publishes_the_round_are_empty(served):
    served["answers"]["2026/20/driverstandings"] = {"StandingsTable": {"StandingsLists": []}, "total": "0"}
    served["answers"]["2026/20/constructorstandings"] = {"StandingsTable": {"StandingsLists": []}, "total": "0"}

    assert jolpica.driver_standings(2026, 20) == []
    assert jolpica.constructor_standings(2026, 20) == []


def test_a_standings_row_with_no_points_is_an_error(served):
    served["answers"]["2026/19/driverstandings"] = {
        "StandingsTable": {"StandingsLists": [{"DriverStandings": [{"Driver": {"code": "VER"}}]}]}
    }
    served["answers"]["2026/19/constructorstandings"] = {
        "StandingsTable": {"StandingsLists": [{"ConstructorStandings": [{"Constructor": {"name": "X"}}]}]}
    }

    with pytest.raises(JolpicaUnavailableError, match="driverstandings: unreadable row"):
        jolpica.driver_standings(2026, 19)
    with pytest.raises(JolpicaUnavailableError, match="constructorstandings: unreadable row"):
        jolpica.constructor_standings(2026, 19)


def test_an_answer_that_is_not_a_standings_table_is_an_error(served):
    served["answers"]["2026/19/driverstandings"] = {"unexpected": 1}

    with pytest.raises(JolpicaUnavailableError, match="not a standings table"):
        jolpica.driver_standings(2026, 19)


# --- failures are errors, never empty answers --------------------------------------------------


def test_a_rate_limited_answer_is_an_error(served):
    served["answers"]["2026/19/results"] = 429

    with pytest.raises(JolpicaUnavailableError, match="HTTP 429"):
        jolpica.race_results(2026, 19)


def test_an_unreachable_jolpica_is_an_error(served):
    served["answers"]["2026/19/results"] = httpx.ConnectError("down")

    with pytest.raises(JolpicaUnavailableError, match="down"):
        jolpica.race_results(2026, 19)


def test_an_answer_that_is_not_json_is_an_error(served):
    served["answers"]["2026/19/results"] = "<html>bad gateway</html>"

    with pytest.raises(JolpicaUnavailableError, match="not a Jolpica answer"):
        jolpica.race_results(2026, 19)


def test_a_table_that_is_not_a_race_table_is_an_error(served):
    served["answers"]["2026/19/results"] = {"total": "1"}

    with pytest.raises(JolpicaUnavailableError, match="not a race table"):
        jolpica.race_results(2026, 19)


def test_every_request_goes_through_the_pacer(served, monkeypatch):
    waits: list[int] = []
    monkeypatch.setattr(jolpica, "PACER", Pacer(clock=lambda: 0.0, sleep=lambda _s: None))
    monkeypatch.setattr(jolpica.PACER, "wait", lambda: waits.append(1))
    served["answers"]["2026/19/results"] = race_table("Results", [])

    jolpica.race_results(2026, 19)

    assert waits == [1]
