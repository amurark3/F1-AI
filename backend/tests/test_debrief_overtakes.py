"""The debrief's position changes on Mexico City 2026's real /overtakes rows."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from app.services import debrief_overtakes as module
from tests.debrief_r19_support import entries, race_session, rows
from tests.openf1_support import fresh_cache, make_session

pytestmark = pytest.mark.unit


class Served:
    def __init__(self, overtakes: list[dict], session) -> None:
        self.overtakes = overtakes
        self.requests: list[str] = []
        self.session = session

    def get_json(self, _client, path: str, _params: dict) -> list[dict]:
        self.requests.append(path)
        return self.overtakes


@pytest.fixture
def serve(monkeypatch):
    fresh_cache(monkeypatch, module)

    def start(overtakes: list[dict], session=None, *, no_session: bool = False) -> Served:
        served = Served(overtakes, session or race_session())
        monkeypatch.setattr(module, "new_client", nullcontext)
        monkeypatch.setattr(module, "find_session", lambda *_args: None if no_session else served.session)
        monkeypatch.setattr(module, "get_json", served.get_json)
        monkeypatch.setattr(module, "entry_list", lambda *_args: entries())
        return served

    return start


def test_mexico_counts_every_row_and_ranks_the_overtakers(serve):
    serve(rows("openf1_overtakes.json"))

    result = module.build_debrief_overtakes(2026, 19)

    made = [row["made"] for row in result["drivers"]]
    assert result["available"] is True
    assert result["total"] == 273 == len(rows("openf1_overtakes.json"))
    assert result["drivers"][0]["driver_code"] == "HAD"
    assert made[0] == 28
    assert made == sorted(made, reverse=True)
    assert sum(made) == 273
    assert set(result["drivers"][0]) == {"driver_code", "driver_name", "team", "made"}


def test_a_tie_is_ordered_by_code(serve):
    serve([{"overtaking_driver_number": 44}, {"overtaking_driver_number": 3}])

    assert [row["driver_code"] for row in module.build_debrief_overtakes(2026, 19)["drivers"]] == ["HAM", "VER"]


def test_a_row_without_an_overtaker_is_counted_in_the_total_but_credited_to_nobody(serve):
    serve([{"overtaking_driver_number": None}, {"overtaking_driver_number": 3}, {"overtaking_driver_number": 999}])

    result = module.build_debrief_overtakes(2026, 19)

    assert result["total"] == 3
    assert [(row["driver_code"], row["made"]) for row in result["drivers"]] == [("VER", 1)]


def test_a_settled_race_keeps_its_rows_and_is_not_asked_again(serve):
    served = serve(rows("openf1_overtakes.json"), make_session("R", ended=True))

    module.build_debrief_overtakes(2026, 19)
    module.build_debrief_overtakes(2026, 19)

    assert served.requests == ["overtakes"]


def test_a_race_still_running_is_asked_every_time(serve):
    served = serve([{"overtaking_driver_number": 3}], make_session("R", ended=False))

    module.build_debrief_overtakes(2026, 19)
    module.build_debrief_overtakes(2026, 19)

    assert served.requests == ["overtakes", "overtakes"]


@pytest.mark.parametrize(("overtakes", "no_session"), [([], False), ([{"overtaking_driver_number": 3}], True)])
def test_no_session_or_no_rows_is_unavailable(serve, overtakes, no_session):
    serve(overtakes, no_session=no_session)

    assert module.build_debrief_overtakes(2026, 19) == {"available": False, "total": 0, "drivers": []}
