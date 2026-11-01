"""Tests for tyre degradation: lap statuses, the fuel model, the fitted wear rates and the payload.

* Each lap gets exactly one status, in a fixed priority, and only clean laps
  are fitted.
* A neutralisation is placed by *time* against each car's own laps.
* Stint boundaries snap to OpenF1's pit-out laps, because ``/stints`` numbers
  some races a lap low.
* The fuel correction adds ``k × burn`` to every slope, so the raw slope is
  always reported beside it, and a sprint gets no correction at all.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import FUEL_EFFECT_SECONDS_PER_KG, RACE_START_FUEL_KG
from app.data.openf1.race_context import RaceContext
from app.data.openf1.race_control import RED_FLAG, SAFETY_CAR, VIRTUAL_SAFETY_CAR, Window
from app.data.stint_model import Stint
from app.services.analysis import degradation as degradation_module
from app.services.analysis.common import AnalysisUnavailableError, SessionRef
from app.services.analysis.degradation import NO_FUEL_MODEL_WARNING, build_degradation, neutralised_bands
from app.services.analysis.degradation_model import (
    MIN_FIT_LAPS,
    FuelModel,
    compound_summary,
    fuel_model,
    line_fit,
    stint_fit,
)
from app.services.analysis.lap_status import (
    CLEAN,
    LAP1,
    NO_TIME,
    OUTLIER,
    PIT_IN,
    PIT_OUT,
    RESTART,
    TRAFFIC,
    UNKNOWN_AGE,
    WET,
    LapFacts,
    StintSpan,
    all_spans,
    driver_spans,
    driver_statuses,
    first_status,
    is_wet,
    neutralised,
    restart_laps,
    span_of,
)
from tests.openf1_support import NOR, T0, VER, make_lap, make_session_laps

pytestmark = pytest.mark.unit

LAP_SECONDS = 90.0


def _at(seconds: float):
    return T0 + timedelta(seconds=seconds)


def _stint(code: str, number: int, compound: str, start: int, end: int, age: int | None = 0) -> Stint:
    return Stint(code, "", number, compound, start, end, end - start + 1, age, age == 0, False)


def _laps(driver: int, count: int, *, pit_out: tuple[int, ...] = (), slow: dict[int, float] | None = None):
    laps = []
    for number in range(1, count + 1):
        time = LAP_SECONDS + (slow or {}).get(number, 0.0)
        laps.append(
            make_lap(
                driver,
                number,
                start=None if number == 1 else (number - 1) * LAP_SECONDS,
                time=time,
                pit_out=number in pit_out,
            )
        )
    return tuple(laps)


# ---------------------------------------------------------------------------
# Stint spans
# ---------------------------------------------------------------------------


def test_a_new_stint_is_snapped_onto_its_pit_out_lap():
    laps = _laps(1, 20, pit_out=(11,))
    stints = [_stint("NOR", 2, "HARD", 10, 20), _stint("NOR", 1, "MEDIUM", 1, 9)]

    first, second = driver_spans(stints, laps, 1)

    assert (first.start, first.end, first.compound) == (1, 10, "MEDIUM")
    assert (second.start, second.end, second.checked) == (11, 20, True)


def test_a_stint_with_no_pit_out_lap_nearby_keeps_its_lap_and_is_unchecked():
    laps = _laps(3, 18, pit_out=(9, 11))
    stints = [_stint("VER", 1, "SOFT", 1, 14), _stint("VER", 2, "HARD", 15, 20)]

    _first, second = driver_spans(stints, laps, 3)

    assert (second.start, second.end, second.checked) == (15, 20, False)


def test_two_pit_out_laps_equally_near_snap_to_the_earlier():
    laps = _laps(1, 20, pit_out=(9, 11))

    _first, second = driver_spans([_stint("NOR", 1, "SOFT", 1, 9), _stint("NOR", 2, "HARD", 10, 20)], laps, 1)

    assert second.start == 9


def test_tyre_age_counts_laps_on_the_set_at_the_end_of_each_lap():
    span = StintSpan(1, 2, "HARD", 11, 20, 3, True)

    assert span.tyre_age(11) == 4
    assert StintSpan(1, 1, "SOFT", 1, 10, None, True).tyre_age(5) is None


def test_stints_of_a_car_not_in_the_session_are_ignored():
    session = make_session_laps(_laps(1, 5))
    context = RaceContext(
        stints=(_stint("HAM", 1, "SOFT", 1, 5), _stint("NOR", 1, "SOFT", 1, 5)), gaps={}, rain=(), classification=()
    )

    assert set(all_spans(session, context)) == {1}
    assert span_of(all_spans(session, context)[1], 99) is None


# ---------------------------------------------------------------------------
# Neutralisations, restarts, rain
# ---------------------------------------------------------------------------


def test_a_lap_under_several_neutralisations_takes_the_most_severe():
    lap = make_lap(1, 5, start=400, time=90)
    windows = (Window(VIRTUAL_SAFETY_CAR, _at(410), _at(420)), Window(RED_FLAG, _at(480), None))

    assert neutralised(lap, windows) == RED_FLAG
    assert neutralised(lap, (Window(SAFETY_CAR, _at(491), None),)) is None
    assert neutralised(make_lap(1, 1, time=90), windows) is None


def test_an_untimed_lap_is_placed_by_its_start():
    assert neutralised(make_lap(1, 5, start=400), (Window(SAFETY_CAR, _at(390), _at(500)),)) == SAFETY_CAR


def test_the_first_lap_begun_after_a_safety_car_is_the_restart():
    laps = _laps(1, 10)
    windows = (
        Window(SAFETY_CAR, _at(200), _at(400)),
        Window(VIRTUAL_SAFETY_CAR, _at(500), _at(600)),
        Window(RED_FLAG, _at(700), None),
        Window(SAFETY_CAR, _at(5000), _at(6000)),
    )

    assert restart_laps(laps, windows) == {6}


def test_a_lap_overlapping_reported_rain_is_wet():
    lap = make_lap(1, 3, start=180, time=90)

    assert is_wet(lap, ((_at(250), _at(310)),))
    assert not is_wet(lap, ((_at(270), _at(330)),))


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

SPANS = [StintSpan(1, 1, "MEDIUM", 1, 10, 0, True), StintSpan(1, 2, "HARD", 11, 20, None, True)]
FACTS = LapFacts(
    spans=SPANS,
    restarts={8},
    windows=(Window(VIRTUAL_SAFETY_CAR, _at(5 * LAP_SECONDS + 10), _at(5 * LAP_SECONDS + 20)),),
    rain=((_at(6 * LAP_SECONDS + 10), _at(6 * LAP_SECONDS + 20)),),
)


@pytest.mark.parametrize(
    ("lap", "gap", "status"),
    [
        (make_lap(1, 1, start=None, time=95), None, LAP1),
        (make_lap(1, 2, start=90), None, NO_TIME),
        (make_lap(1, 3, start=180, time=110, pit_out=True), None, PIT_OUT),
        (make_lap(1, 10, start=810, time=110), None, PIT_IN),
        (make_lap(1, 6, start=450, time=99), None, VIRTUAL_SAFETY_CAR),
        (make_lap(1, 8, start=630, time=90), None, RESTART),
        (make_lap(1, 7, start=540, time=91), None, WET),
        (make_lap(1, 12, start=990, time=90), None, UNKNOWN_AGE),
        (make_lap(1, 25, start=2160, time=90), None, UNKNOWN_AGE),
        (make_lap(1, 4, start=270, time=90), 0.8, TRAFFIC),
        (make_lap(1, 4, start=270, time=90), 2.5, CLEAN),
        (make_lap(1, 20, start=1710, time=90), None, UNKNOWN_AGE),
    ],
    ids=[
        "opening-lap",
        "no-time",
        "pit-out",
        "pit-in",
        "vsc",
        "restart",
        "wet",
        "unknown-age",
        "no-stint",
        "traffic",
        "clean-air",
        "final-stint-end-is-not-pit-in",
    ],
)
def test_each_lap_gets_the_first_status_that_applies(lap, gap, status):
    assert first_status(lap, FACTS, gap) == status


def test_a_lap_slower_than_107_percent_of_the_drivers_median_is_an_outlier():
    laps = _laps(1, 9, slow={5: 10.0})
    facts = LapFacts([StintSpan(1, 1, "HARD", 1, 9, 0, True)], set(), (), ())

    statuses = driver_statuses(laps, facts, {(1, 4): 0.5})

    assert statuses[5] == OUTLIER
    assert statuses[4] == TRAFFIC
    assert statuses[3] == CLEAN


def test_without_green_flag_laps_nothing_is_an_outlier():
    laps = _laps(1, 2)

    assert driver_statuses(laps, LapFacts([], set(), (), ()), {}) == {1: LAP1, 2: UNKNOWN_AGE}


# ---------------------------------------------------------------------------
# Fuel and fits
# ---------------------------------------------------------------------------


def test_the_fuel_model_puts_each_lap_on_an_empty_tank():
    fuel = fuel_model(2026, "R", 50)

    assert fuel == FuelModel(RACE_START_FUEL_KG[2026], FUEL_EFFECT_SECONDS_PER_KG, 50)
    assert fuel.on_board(1) == pytest.approx(70 * (1 - 0.5 / 50))
    assert fuel.on_board(60) == 0.0
    assert fuel.corrected(1, 90.0) == round(90.0 - 0.03 * 69.3, 3)
    assert fuel.slope_effect == pytest.approx(0.03 * 70 / 50)
    assert fuel.to_json()["slope_effect"] == 0.042


@pytest.mark.parametrize(("year", "code", "laps"), [(2026, "S", 19), (2019, "R", 58), (2026, "R", 0)])
def test_a_sprint_an_unconfigured_season_or_no_laps_gets_no_fuel_model(year, code, laps):
    assert fuel_model(year, code, laps) is None


def test_a_straight_line_fit_reports_slope_and_fit_quality():
    fit = line_fit([1, 2, 3, 4], [90.0, 90.1, 90.2, 90.3])

    assert (fit.slope, fit.intercept, fit.r2) == (0.1, 89.9, 1.0)
    assert line_fit([1, 2], [90.0, 90.0]).r2 == 1.0


def _rows(count: int, *, corrected: bool = True, age_step: int = 1) -> list[dict]:
    return [
        {
            "status": CLEAN,
            "tyre_age": 1 + (index * age_step),
            "time": 90.0 + 0.05 * index,
            "corrected": 88.0 + 0.02 * index if corrected else None,
        }
        for index in range(count)
    ]


def test_a_stint_is_fitted_raw_and_corrected_from_its_clean_laps():
    fit = stint_fit([*_rows(MIN_FIT_LAPS), {"status": TRAFFIC, "tyre_age": 9, "time": 120.0, "corrected": 118.0}])

    assert fit["laps_fitted"] == MIN_FIT_LAPS
    assert fit["raw"]["slope"] == 0.05
    assert fit["corrected"]["slope"] == 0.02


def test_a_stint_without_corrected_times_is_fitted_raw_only():
    assert stint_fit(_rows(MIN_FIT_LAPS, corrected=False))["corrected"] is None


@pytest.mark.parametrize("rows", [_rows(MIN_FIT_LAPS - 1), _rows(MIN_FIT_LAPS, age_step=0)], ids=["few", "one-age"])
def test_a_stint_with_too_little_to_fit_has_no_fit(rows):
    assert stint_fit(rows) is None


def test_each_compound_gets_the_median_rate_and_its_spread():
    corrected = stint_fit(_rows(6))
    raw_only = stint_fit(_rows(6, corrected=False))
    stints = [
        {"compound": "SOFT", "fit": corrected},
        {"compound": "SOFT", "fit": raw_only},
        {"compound": "HARD", "fit": corrected},
        {"compound": "HARD", "fit": None},
    ]

    hard, soft = compound_summary(stints)

    assert (hard["compound"], hard["stints"], hard["median_slope"], hard["corrected"]) == ("HARD", 1, 0.02, True)
    assert (soft["stints"], soft["median_slope"], soft["median_raw_slope"]) == (2, 0.035, 0.05)
    assert soft["corrected"] is False
    assert soft["iqr"] == [0.0275, 0.0425]


# ---------------------------------------------------------------------------
# The payload
# ---------------------------------------------------------------------------

RACE_LAPS = _laps(1, 20, pit_out=(11,)) + _laps(3, 20, pit_out=(9,))
RACE_WINDOWS = (Window(VIRTUAL_SAFETY_CAR, _at(4 * LAP_SECONDS + 10), _at(4 * LAP_SECONDS + 30)),)
RACE_CONTEXT = RaceContext(
    stints=(
        _stint("NOR", 1, "MEDIUM", 1, 9),
        _stint("NOR", 2, "HARD", 10, 20),
        _stint("VER", 1, "SOFT", 1, 14),
        _stint("VER", 2, "HARD", 15, 20, age=2),
    ),
    gaps={(3, 3): 0.7},
    rain=(),
    classification=(1,),
)


@pytest.fixture
def race(monkeypatch):
    def install(context: RaceContext, code: str = "R"):
        session = make_session_laps(RACE_LAPS, code=code, windows=RACE_WINDOWS)
        monkeypatch.setattr(degradation_module, "require_session", lambda _ref: session)
        monkeypatch.setattr(degradation_module, "load_race_context", lambda _session: context)
        return session

    return install


def test_every_lap_is_returned_with_its_status_and_the_stints_are_fitted(race):
    race(RACE_CONTEXT)

    answer = build_degradation(SessionRef(2026, 18, "R"))

    assert [driver["code"] for driver in answer["drivers"]] == ["NOR", "VER"]
    assert [driver["position"] for driver in answer["drivers"]] == [1, None]
    assert len(answer["laps"]) == 40
    nor = {row["lap"]: row for row in answer["laps"] if row["driver"] == "NOR"}
    assert (nor[5]["status"], nor[10]["status"], nor[11]["status"]) == (VIRTUAL_SAFETY_CAR, PIT_IN, PIT_OUT)
    assert (nor[12]["compound"], nor[12]["tyre_age"], nor[12]["stint"]) == ("HARD", 2, 2)
    assert nor[12]["corrected"] < nor[12]["time"]
    nor_stints = [stint for stint in answer["stints"] if stint["driver"] == "NOR"]
    assert all(stint["fit"] is not None for stint in nor_stints)
    assert {compound["compound"] for compound in answer["compounds"]} == {"MEDIUM", "HARD", "SOFT"}
    assert answer["neutralised"] == [{"kind": VIRTUAL_SAFETY_CAR, "from_lap": 5, "to_lap": 5}]
    assert answer["assumptions"]["fuel"]["race_laps"] == 20
    assert answer["warnings"] == ["1 stint change(s) had no pit-out lap nearby; OpenF1's stint lap was kept."]
    assert "corrected" in answer["modeled"]


def test_a_sprint_is_analysed_without_fuel_correction(race):
    race(RACE_CONTEXT, code="S")

    answer = build_degradation(SessionRef(2026, 18, "S"))

    assert answer["assumptions"]["fuel"] is None
    assert {row["corrected"] for row in answer["laps"]} == {None}
    assert answer["warnings"][0] == NO_FUEL_MODEL_WARNING


def test_a_race_without_stints_says_so(race):
    race(RaceContext(stints=(), gaps={}, rain=(), classification=()))

    with pytest.raises(AnalysisUnavailableError, match="no_stints"):
        build_degradation(SessionRef(2026, 18, "R"))


def test_an_unclassified_field_is_listed_by_number_and_bands_need_a_leader(race):
    session = race(RaceContext(stints=RACE_CONTEXT.stints, gaps={}, rain=(), classification=()))

    answer = build_degradation(SessionRef(2026, 18, "R"))

    assert [driver["code"] for driver in answer["drivers"]] == [NOR.code, VER.code]
    assert neutralised_bands(session, None) == []
