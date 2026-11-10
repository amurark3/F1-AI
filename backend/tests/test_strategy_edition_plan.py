"""Tests for app.data.strategy.edition_plan: one edition reduced to its measured plan.

The R20 2026 baseline is read off the 2025 São Paulo Grand Prix (real OpenF1
and Jolpica responses, captured 10 Nov 2026; see ``sao_paulo_2025_support``).
What it must get right, each checked against that race:

* the sample is the classified finishers, never a car whose stints simply stop
  (Hamilton, Leclerc and Bortoleto retired);
* every compound a finisher ran is in the sequence, the middle stint included;
* stop counts and stop laps are the published sheet's, not stint boundaries;
* the pit-lane time is the median of OpenF1's ``pit_duration`` over those stops.
"""

from __future__ import annotations

import pytest

from app.data.f1db_pitstops import PitStop
from app.data.race_classification import ClassifiedDriver
from app.data.stint_model import Stint
from app.data.strategy.edition_plan import Edition, EditionRace, summarize_edition
from tests import sao_paulo_2025_support as r21

pytestmark = pytest.mark.unit

EDITION = Edition(year=r21.YEAR, round=r21.ROUND, name=r21.EVENT_NAME)


def r21_plan() -> dict:
    race = EditionRace(r21.stints(), r21.sheet_entries(), r21.classification(), r21.pit_lane_millis())
    plan = summarize_edition(EDITION, race)
    assert plan is not None
    return plan


def plan_of(
    stints: tuple[Stint, ...],
    stops: tuple[PitStop, ...],
    classification: tuple[ClassifiedDriver, ...],
    lane_millis: dict[tuple[str, int], int],
) -> dict | None:
    return summarize_edition(EDITION, EditionRace(stints, stops, classification, lane_millis))


def stint(code: str, number: int, compound: str | None, start: int, end: int) -> Stint:
    return Stint(
        driver_code=code,
        team="",
        stint=number,
        compound=compound,
        start_lap=start,
        end_lap=end,
        laps=end - start + 1,
        tyre_life_start=0,
        fresh=True,
        ended_under_red_flag=False,
    )


def stop(code: str, lap: int, number: int = 1) -> PitStop:
    return PitStop(driver_code=code, stop=number, lap=lap, time="23.000", millis=23_000)


def finisher(code: str, position: int, laps: int | None = 50) -> ClassifiedDriver:
    return ClassifiedDriver(driver_code=code, position=position, status="finished", laps_completed=laps)


# --- the 2025 São Paulo Grand Prix ----------------------------------------------------


def test_the_edition_is_named_with_its_year_and_round():
    plan = r21_plan()

    assert (plan["source_year"], plan["round"], plan["event_name"]) == (2025, 21, "São Paulo Grand Prix")
    assert plan["total_laps"] == 71
    assert plan["winner"] == "NOR"


def test_only_the_classified_finishers_are_counted():
    plan = r21_plan()

    assert plan["finishers"] == 17
    drivers = {code for sequence in plan["sequences"] for code in sequence["drivers"]}
    assert {"HAM", "LEC", "BOR"}.isdisjoint(drivers)
    assert len(drivers) == 17


def test_the_most_common_sequence_is_named_in_full_with_its_stop_laps():
    headline = r21_plan()["sequences"][0]

    # Tied with Soft-Medium-Medium on five finishers; the winner's sequence leads.
    assert headline == {
        "compounds": ["MEDIUM", "SOFT", "MEDIUM"],
        "stops": 2,
        "drivers": ["NOR", "RUS", "PIA", "ALB", "COL"],
        "stop_laps": [34, 50],
    }


def test_every_sequence_the_finishers_ran_is_ranked_by_how_many_ran_it():
    sequences = r21_plan()["sequences"]

    assert [(sequence["compounds"], sequence["stops"], len(sequence["drivers"])) for sequence in sequences] == [
        (["MEDIUM", "SOFT", "MEDIUM"], 2, 5),
        (["SOFT", "MEDIUM", "MEDIUM"], 2, 5),
        (["HARD", "MEDIUM", "MEDIUM"], 2, 3),
        (["HARD", "MEDIUM", "MEDIUM", "SOFT"], 3, 1),
        (["SOFT", "MEDIUM"], 1, 1),
        (["MEDIUM", "SOFT"], 1, 1),
        (["HARD", "MEDIUM", "MEDIUM", "MEDIUM"], 3, 1),
    ]
    assert sequences[1]["drivers"] == ["ANT", "BEA", "HAD", "GAS", "SAI"]
    assert sequences[1]["stop_laps"] == [18, 39]


def test_stop_counts_come_from_the_pit_sheet():
    assert r21_plan()["stop_counts"] == [
        {"stops": 2, "drivers": 13},
        {"stops": 1, "drivers": 2},
        {"stops": 3, "drivers": 2},
    ]


def test_the_first_stop_window_is_the_finishers_first_stops():
    # First stops: 2, 7, 8, 17, 17, 18, 18, 19, 21, 28, 29, 29, 30, 34, 35, 36, 38.
    assert r21_plan()["first_stop"] == {"median_lap": 21, "p25_lap": 17, "p75_lap": 30, "drivers": 17}


def test_the_pit_lane_time_is_the_median_of_openf1s_pit_duration_over_the_finishers_stops():
    # 34 stops; the penalty stops (TSU 34.2 s, PIA 34.6 s) do not move the median.
    assert r21_plan()["pit_lane"] == {"median_seconds": 23.5, "stops": 34}


# --- edge cases -------------------------------------------------------------------------


def test_no_finisher_means_no_plan():
    retired = ClassifiedDriver(driver_code="VER", position=None, status="dnf", laps_completed=3)

    assert plan_of((stint("VER", 1, "SOFT", 1, 3),), (), (retired,), {}) is None


def test_a_finisher_without_stints_is_left_out_of_the_sample():
    plan = plan_of(
        (stint("VER", 1, "MEDIUM", 1, 20), stint("VER", 2, "HARD", 21, 50)),
        (stop("VER", 20),),
        (finisher("VER", 1), finisher("NOR", 2)),
        {},
    )

    assert plan is not None
    assert plan["finishers"] == 1


def test_an_unknown_compound_is_named_unknown():
    plan = plan_of((stint("VER", 1, None, 1, 50),), (), (finisher("VER", 1),), {})

    assert plan is not None
    assert plan["sequences"][0]["compounds"] == ["UNKNOWN"]


def test_a_field_that_never_stopped_has_no_first_stop_window():
    plan = plan_of((stint("VER", 1, "HARD", 1, 50),), (), (finisher("VER", 1),), {})

    assert plan is not None
    assert plan["first_stop"] is None
    assert plan["stop_counts"] == [{"stops": 0, "drivers": 1}]
    assert plan["sequences"][0]["stop_laps"] == []


def test_without_published_pit_lane_times_there_is_no_pit_lane_figure():
    plan = plan_of(
        (stint("VER", 1, "MEDIUM", 1, 20), stint("VER", 2, "HARD", 21, 50)),
        (stop("VER", 20),),
        (finisher("VER", 1),),
        {("VER", 21): 22_000},
    )

    assert plan is not None
    assert plan["pit_lane"] is None


def test_the_distance_falls_back_to_the_stints_when_the_classification_has_no_laps():
    plan = plan_of((stint("VER", 1, "HARD", 1, 52),), (), (finisher("VER", 1, laps=None),), {})

    assert plan is not None
    assert plan["total_laps"] == 52


def test_a_race_whose_winner_is_not_among_the_finishers_names_none():
    # Position 1 is the winner; a sample that starts lower has none.
    plan = plan_of((stint("VER", 1, "HARD", 1, 50),), (), (finisher("VER", 2),), {})

    assert plan is not None
    assert plan["winner"] is None


def test_a_tie_goes_to_the_sequence_of_the_better_placed_finisher():
    stints = (
        stint("NOR", 1, "SOFT", 1, 20),
        stint("NOR", 2, "HARD", 21, 50),
        stint("VER", 1, "MEDIUM", 1, 25),
        stint("VER", 2, "HARD", 26, 50),
    )
    plan = plan_of(
        stints,
        (stop("NOR", 20), stop("VER", 25)),
        (finisher("VER", 1), finisher("NOR", 2)),
        {},
    )

    assert plan is not None
    assert [sequence["drivers"] for sequence in plan["sequences"]] == [["VER"], ["NOR"]]


def test_stints_are_read_in_stint_order_whatever_order_they_arrive_in():
    stints = (stint("VER", 2, "HARD", 21, 50), stint("VER", 1, "MEDIUM", 1, 20))

    plan = plan_of(stints, (stop("VER", 20),), (finisher("VER", 1),), {})

    assert plan is not None
    assert plan["sequences"][0]["compounds"] == ["MEDIUM", "HARD"]
