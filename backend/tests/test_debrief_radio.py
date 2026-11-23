"""The debrief's team radio on Mexico City 2026's real rows, plus hand-built edge cases."""

from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.data.openf1.laps import Lap
from app.services import debrief_radio as module
from tests.debrief_r19_support import entries, race_session, radio_inputs

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
ARCHIVE = "https://livetiming.formula1.com/static/x/TeamRadio/"


def _at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


def _lap(car: int, number: int, seconds: float) -> Lap:
    return Lap(car, number, T0 + timedelta(seconds=seconds), 90.0, (None, None, None), (None, None, None), False)


def _clip(car: int, seconds: float, name: str = "a") -> dict:
    return {"driver_number": car, "date": _at(seconds), "recording_url": f"{ARCHIVE}{name}.mp3"}


def _inputs(*, radio=(), pit=(), messages=(), dnf=(), laps=None, gmt="-06:00:00") -> module.RadioInputs:
    """Hand-built: VER (3) and NOR (1) with a lap every 100 s from the start."""
    base = radio_inputs()
    cars = laps or tuple(_lap(car, n, (n - 1) * 100) for car in (3, 1) for n in range(1, 11))
    return replace(
        base,
        laps=replace(base.laps, laps=cars),
        radio=list(radio),
        pit=list(pit),
        messages=list(messages),
        gmt_offset=gmt,
        dnf_cars=frozenset(dnf),
    )


def _kinds(payload: dict) -> list[tuple]:
    return [(m["kind"], m["lap"], len(m["clips"])) for m in payload["moments"]]


def test_mexico_clips_sit_with_the_moment_they_came_within_a_lap_of():
    payload = module.radio_payload(radio_inputs())

    assert payload["total"] == 27
    assert _kinds(payload) == [
        ("start", 1, 2),
        ("incident", 1, 1),
        ("safety_car", 44, 1),
        ("red_flag", 45, 2),
        ("safety_car", 59, 1),
        ("incident", 59, 1),
        ("safety_car_in", 62, 2),
        ("chequered", 71, 4),
    ]
    assert sum(len(m["clips"]) for m in payload["moments"]) == 14
    assert [c["lap"] for c in payload["unattached"]] == [14, 15, 15, 23, 24, 29, 30, 32, 38, 38, 52, 54, 56]
    assert payload["utc_offset_minutes"] == -360
    assert [m["detail"] for m in payload["moments"] if m["kind"] == "incident"] == [
        "Turn 4 · with LEC",
        "Turn 2 · with LIN",
    ]


def test_mexico_clips_land_where_the_nearest_moment_is():
    moments = module.radio_payload(radio_inputs())["moments"]
    where = {c["at"][11:19]: m["kind"] for m in moments for c in m["clips"]}

    assert [c["at"][11:19] for c in moments[0]["clips"]] == ["19:55:24", "19:59:28"]
    assert where["20:05:33"] == "incident"
    assert where["21:06:01"] == where["21:08:33"] == "red_flag"
    assert where["21:02:27"] == "safety_car"
    assert where["22:04:23"] == "safety_car"
    assert where["22:06:55"] == "incident"  # PIA's own Turn 2 incident, not the Safety Car
    assert where["22:08:57"] == where["22:09:58"] == "safety_car_in"


def test_mexico_candidate_moments_are_counted_but_most_attach_no_clip():
    inputs = radio_inputs()
    starts = module._starts(inputs.laps)
    moments = module.build_moments(inputs, starts, -360)

    assert Counter(m.kind for m in moments if m.kind in {"penalty", "retirement", "vsc", "vsc_ending", "red_flag"}) == {
        "penalty": 4,
        "retirement": 5,
        "vsc": 1,
        "vsc_ending": 1,
        "red_flag": 1,
    }
    assert sorted((m.lap, m.car) for m in moments if m.kind == "penalty") == [(12, 16), (13, 63), (46, 11), (51, 27)]
    assert sorted((m.car, m.lap) for m in moments if m.kind == "retirement") == [
        (14, 6),
        (18, 6),
        (41, 59),
        (77, 43),
        (87, 48),
    ]
    stops = [m for m in moments if m.kind == "stop"]
    assert all(m.detail for m in stops)
    assert not any(m.car == 3 and m.lap == 45 for m in stops)
    assert not any(m.car == 6 and m.lap == 45 for m in stops)


def test_a_clip_after_the_drivers_own_stop_attaches_to_it_and_another_cars_stop_does_not():
    pit = [
        {"date": _at(105), "lap_number": 2, "driver_number": 3, "lane_duration": 22.0, "stop_duration": 2.43},
        {"date": _at(105), "lap_number": 2, "driver_number": 1, "lane_duration": 22.0, "stop_duration": 2.6},
    ]
    payload = module.radio_payload(_inputs(radio=[_clip(3, 250)], pit=pit))

    assert _kinds(payload) == [("stop", 2, 1)]
    assert payload["moments"][0]["detail"] == "2.4 s"
    assert payload["moments"][0]["driver"]["driver_code"] == "VER"
    assert module.radio_payload(_inputs(radio=[_clip(3, 505)], pit=pit))["unattached"][0]["lap"] == 6
    assert module.radio_payload(_inputs(radio=[_clip(1, 205)], pit=pit[:1]))["unattached"][0]["lap"] == 3


def test_a_stop_without_a_stationary_time_reads_its_pit_lane_time_and_pit_duration_counts():
    pit = [
        {"date": _at(105), "lap_number": 2, "driver_number": 3, "pit_duration": 23.04},
        {"date": _at(106), "lap_number": 2, "driver_number": 1, "lane_duration": 22.0, "stop_duration": 2.0},
        {"date": _at(107), "lap_number": 2, "driver_number": 3, "lane_duration": 90.0},
        {"date": None, "lap_number": 2, "driver_number": 3, "lane_duration": 22.0},
        {"date": _at(108), "lap_number": None, "driver_number": 3, "lane_duration": 22.0},
        {"date": _at(109), "lap_number": 2, "driver_number": 3},
    ]
    moments = module.build_moments(_inputs(pit=pit), {}, None)

    assert [(m.car, m.detail) for m in moments if m.kind == "stop"] == [(3, "pit lane 23.0 s"), (1, "2.0 s")]
    assert module.stop_lane_limit([]) is None
    assert module.stop_lane_limit([{"lane_duration": 20.0}, {"pit_duration": 30.0}]) == 37.5
    assert module.is_stop({"lane_duration": 1.0, "lap_number": 2}, None) is False


def test_a_penalty_attaches_to_its_car_and_a_served_message_is_no_moment():
    messages = [
        {
            "date": _at(105),
            "lap_number": 2,
            "message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 3 (VER) - SPEEDING",
        },
        {
            "date": _at(110),
            "lap_number": 2,
            "message": "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 3 (VER)",
        },
    ]
    payload = module.radio_payload(_inputs(radio=[_clip(3, 120)], messages=messages))

    assert _kinds(payload) == [("penalty", 2, 1)]
    assert payload["moments"][0]["detail"] == "5 second time penalty"


def test_a_dnf_cars_clip_on_its_last_lap_attaches_and_a_dnf_car_without_laps_adds_none():
    laps = tuple(_lap(3, n, (n - 1) * 100) for n in range(1, 4))
    payload = module.radio_payload(_inputs(radio=[_clip(3, 250)], dnf=(3, 1), laps=laps))

    assert _kinds(payload) == [("retirement", 3, 1)]
    assert [
        m.car for m in module.build_moments(_inputs(dnf=(3, 1), laps=laps), {}, None) if m.kind == "retirement"
    ] == [3]


def test_a_clip_between_a_stop_and_the_safety_car_goes_to_the_nearer_and_a_tie_to_the_earlier():
    pit = [{"date": _at(210), "lap_number": 3, "driver_number": 3, "lane_duration": 22.0, "stop_duration": 2.0}]
    sc = [{"date": _at(250), "lap_number": 3, "message": "SAFETY CAR DEPLOYED"}]

    assert _kinds(module.radio_payload(_inputs(radio=[_clip(3, 220)], pit=pit, messages=sc))) == [("stop", 3, 1)]
    assert _kinds(module.radio_payload(_inputs(radio=[_clip(3, 240)], pit=pit, messages=sc))) == [("safety_car", 3, 1)]
    assert _kinds(module.radio_payload(_inputs(radio=[_clip(3, 230)], pit=pit, messages=sc))) == [("stop", 3, 1)]


def test_an_unclosed_red_flag_takes_every_later_clip_and_vsc_messages_are_moments():
    messages = [
        {"date": _at(150), "lap_number": 2, "message": "RED FLAG", "flag": "RED", "scope": "Track"},
        {"date": _at(20), "lap_number": 1, "message": "VSC DEPLOYED"},
        {"date": _at(30), "lap_number": 1, "message": "VIRTUAL SAFETY CAR ENDING"},
        {"date": _at(40), "lap_number": 1, "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"date": _at(50), "lap_number": 1, "message": "VSC ENDING"},
        {"date": _at(60), "message": "SAFETY CAR DEPLOYED"},
        {"date": _at(900), "lap_number": 9, "message": "CHEQUERED FLAG", "flag": "CHEQUERED"},
        {"date": "soon", "lap_number": 9, "message": "SAFETY CAR DEPLOYED"},
    ]
    moments = module.build_moments(_inputs(messages=messages), {}, None)
    payload = module.radio_payload(_inputs(radio=[_clip(3, 800)], messages=messages))

    assert [m.kind for m in moments] == ["start", "vsc", "vsc_ending", "vsc", "vsc_ending", "red_flag", "chequered"]
    assert moments[5].until is None
    assert _kinds(payload) == [("red_flag", 2, 1)]


def test_a_red_flag_without_a_lap_is_no_moment():
    messages = [{"date": _at(150), "message": "RED FLAG", "flag": "RED"}]

    assert [m.kind for m in module.build_moments(_inputs(messages=messages), {}, None)] == ["start"]


def test_an_incident_naming_two_cars_makes_a_moment_per_car_at_the_bracketed_time():
    messages = [
        {
            "date": _at(130),
            "lap_number": 2,
            "message": "Turn 4 incident involving cars 3 (VER) and 1 (NOR) noted (14:01:45)",
        },
        {"date": _at(140), "message": "INCIDENT INVOLVING CAR 3 (VER) NOTED"},
        {"date": _at(150), "lap_number": 2, "message": "INCIDENT INVOLVING CAR 1 (NOR) NOTED - FALSE START"},
    ]
    starts = module._starts(_inputs().laps)
    moments = [m for m in module.build_moments(_inputs(messages=messages), starts, -360) if m.kind == "incident"]

    assert [(m.car, m.lap, m.detail, m.at) for m in moments] == [
        (3, 2, "Turn 4 · with NOR", T0 + timedelta(seconds=105)),
        (1, 2, "Turn 4 · with VER", T0 + timedelta(seconds=105)),
        (1, 2, "False start", T0 + timedelta(seconds=150)),
    ]
    no_offset = module.build_moments(_inputs(messages=messages[:1]), starts, None)
    assert [m.at for m in no_offset if m.kind == "incident"] == [T0 + timedelta(seconds=130)] * 2


def test_clips_with_a_foreign_url_a_bad_date_or_an_unknown_car_are_dropped():
    radio = [
        _clip(3, 10),
        {**_clip(3, 20), "recording_url": "https://evil.example/a.mp3"},
        {**_clip(3, 30), "recording_url": None},
        {**_clip(3, 40), "date": "soon"},
        _clip(999, 50),
    ]
    undated = _lap(3, 11, 0).__class__(3, 11, None, None, (None, None, None), (None, None, None), False)
    laps = (*_inputs().laps.laps, undated)
    payload = module.radio_payload(_inputs(radio=radio, laps=laps))

    assert payload["total"] == 1
    assert payload["unattached"] == []
    assert [c["driver_code"] for m in payload["moments"] for c in m["clips"]] == ["VER"]


def test_a_clip_with_no_moment_within_a_lap_is_unattached_and_the_start_is_skipped_without_a_date():
    inputs = _inputs(radio=[_clip(3, 800)])
    no_start = replace(inputs, laps=replace(inputs.laps, session=replace(race_session(), date_start=None)))
    payload = module.radio_payload(no_start)

    assert payload["moments"] == []
    assert [c["lap"] for c in payload["unattached"]] == [9]


@pytest.mark.parametrize(
    ("value", "minutes"), [("+05:30:00", 330), ("-06:00:00", -360), ("00:00", 0), (None, None), ("soon", None)]
)
def test_the_circuit_offset_reads_from_gmt_offset(value, minutes):
    assert module.offset_minutes(value) == minutes


@pytest.fixture
def serve(monkeypatch):
    def start(*, laps="r19", radio=None, sessions=None, result=None):
        asked: list[str] = []
        inputs = radio_inputs()

        def get_json(_client, path, _params):
            asked.append(path)
            return {
                "team_radio": inputs.radio if radio is None else radio,
                "pit": inputs.pit,
                "race_control": inputs.messages,
                "sessions": [{"gmt_offset": "-06:00:00"}] if sessions is None else sessions,
            }[path]

        monkeypatch.setattr(module, "load_session_laps", lambda *_a: inputs.laps if laps == "r19" else laps)
        monkeypatch.setattr(module, "new_client", nullcontext)
        monkeypatch.setattr(module, "get_json", get_json)
        monkeypatch.setattr(module, "build_session_result", lambda *_a: result)
        return asked

    return start


def test_build_without_a_session_or_laps_says_the_laps_are_not_published(serve):
    serve(laps=None)
    missing = module.build_debrief_radio(2026, 19)
    serve(laps=replace(radio_inputs().laps, laps=()))
    empty = module.build_debrief_radio(2026, 19)

    assert (
        missing
        == empty
        == {
            "available": False,
            "reason": module.NO_LAPS,
            "total": 0,
            "utc_offset_minutes": None,
            "moments": [],
            "unattached": [],
        }
    )


def test_build_without_radio_says_so_and_asks_for_nothing_else(serve):
    asked = serve(radio=[])

    assert module.build_debrief_radio(2026, 19)["reason"] == module.NO_RADIO
    assert asked == ["team_radio"]


def test_build_maps_a_dnf_classification_row_to_its_car_by_canonical_code(serve):
    serve(result={"classification": [{"driver_code": "VER", "status": "DNF"}, {"driver_code": "HAM", "status": "FIN"}]})

    moments = module.build_debrief_radio(2026, 19)["moments"]

    assert [m["driver"]["driver_code"] for m in moments if m["kind"] == "retirement"] == []
    serve(result=None)
    assert module.build_debrief_radio(2026, 19)["total"] == 27
    assert module._dnf_cars(2026, 19, entries()) == frozenset()


def test_build_without_a_sessions_row_has_no_offset(serve):
    asked = serve(sessions=[])

    assert module.build_debrief_radio(2026, 19)["utc_offset_minutes"] is None
    assert asked == ["team_radio", "pit", "race_control", "sessions"]
