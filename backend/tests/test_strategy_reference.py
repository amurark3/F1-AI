"""Tests for app.data.strategy.reference — pre-race planning numbers.

An upcoming race has no laps of its own, so every number here is borrowed from
the most recent completed edition of the same circuit. That makes provenance
the thing to guard:

* **Pit loss must come from real stop pairs.** The in-lap/out-lap estimate is
  bounded to 5-60s precisely so a safety-car lap cannot be read as a pit stop.
* **A circuit with no loadable edition returns None.** Inventing a tyre window
  for a track we have no data for is the failure mode this screen exists to
  avoid.
* **The answer is cached per (circuit, season), including the misses**, so a
  missing circuit is not re-searched across a decade of schedules every call.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.strategy import reference as module
from tests.strategy_fixture import laps_frame, schedule_frame, stint_rows


@pytest.fixture(autouse=True)
def _clear_cache():
    """The reference memoises per (circuit, season) for the process lifetime."""
    module._circuit_reference_cache.clear()
    yield
    module._circuit_reference_cache.clear()


def _stub_seasons(
    monkeypatch: pytest.MonkeyPatch,
    *,
    schedules: dict[int, object] | None = None,
    races: dict[int, object] | None = None,
) -> dict[str, list]:
    """Serve a schedule and race data per season year; record the requests."""
    seen: dict[str, list] = {"schedules": [], "races": []}

    def _resolve(mapping: dict | None, key: int, default=None):
        value = (mapping or {}).get(key, default)
        if isinstance(value, BaseException):
            raise value
        return value

    def _get_event_schedule(year: int, include_testing: bool):
        seen["schedules"].append(year)
        return _resolve(schedules, year, pd.DataFrame(columns=["RoundNumber", "Location"]))

    def _load_race_data(year: int, round_num: int):
        seen["races"].append((year, round_num))
        return _resolve(races, year)

    monkeypatch.setattr(module.fastf1, "get_event_schedule", _get_event_schedule)
    monkeypatch.setattr(module, "_load_race_data", _load_race_data)
    return seen


def _field_race() -> pd.DataFrame:
    """Three cars: two one-stoppers on Medium-Hard, one two-stopper."""
    return laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 24), ("HARD", 25, 50)]),
        stint_rows("LEC", [("SOFT", 1, 14), ("MEDIUM", 15, 32), ("HARD", 33, 50)]),
    )


# ---------------------------------------------------------------------------
# _estimate_pit_loss
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pit_loss_is_the_time_the_in_and_out_laps_cost_over_green_pace():
    # Laps 1-10 at 90s except the in-lap (lap 5) and out-lap (lap 6) at 100s.
    times = [90.0] * 10
    times[4] = 100.0
    times[5] = 100.0
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 5), ("HARD", 6, 10)], lap_seconds=times, pit_laps=(5,)))

    assert module._estimate_pit_loss(laps) == 20.0


@pytest.mark.unit
def test_the_median_across_the_field_is_reported():
    slow = [90.0] * 10
    slow[4] = slow[5] = 100.0
    slower = [90.0] * 10
    slower[4] = slower[5] = 105.0
    laps = laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 5), ("HARD", 6, 10)], lap_seconds=slow, pit_laps=(5,)),
        stint_rows("NOR", [("MEDIUM", 1, 5), ("HARD", 6, 10)], lap_seconds=slower, pit_laps=(5,)),
    )

    assert module._estimate_pit_loss(laps) == 25.0


@pytest.mark.unit
def test_a_race_with_no_pit_stops_yields_no_estimate():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 10)]))

    assert module._estimate_pit_loss(laps) is None


@pytest.mark.unit
@pytest.mark.parametrize("penalty", [2.0, 60.0])
def test_deltas_outside_the_plausible_band_are_discarded(penalty: float):
    """A 2s delta is noise; a 60s+ delta is a safety car, not a pit stop."""
    times = [90.0] * 10
    times[4] = times[5] = 90.0 + penalty
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 5), ("HARD", 6, 10)], lap_seconds=times, pit_laps=(5,)))

    assert module._estimate_pit_loss(laps) is None


@pytest.mark.unit
def test_a_stop_on_the_final_lap_has_no_out_lap_to_compare():
    times = [90.0] * 10
    times[9] = 110.0
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 10)], lap_seconds=times, pit_laps=(10,)))

    assert module._estimate_pit_loss(laps) is None


@pytest.mark.unit
def test_a_driver_with_no_green_flag_reference_lap_is_skipped():
    """Every lap is a pit lap, so there is no clean pace to measure against."""
    rows = stint_rows("VER", [("MEDIUM", 1, 2), ("HARD", 3, 4)], pit_laps=(1, 2, 3, 4))

    assert module._estimate_pit_loss(laps_frame(rows)) is None


@pytest.mark.unit
def test_an_untimed_in_lap_or_out_lap_cannot_be_measured():
    times: list[float | None] = [90.0] * 10
    times[4] = None
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 5), ("HARD", 6, 10)], lap_seconds=times, pit_laps=(5,)))

    assert module._estimate_pit_loss(laps) is None


# ---------------------------------------------------------------------------
# _summarize_circuit_edition
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_edition_is_reduced_to_its_planning_numbers():
    reference = module._summarize_circuit_edition({"laps": _field_race()}, 2023)

    assert reference["source_year"] == 2023
    assert reference["sample_size"] == 3
    assert reference["total_laps"] == 50
    # First stops on laps 21, 25 and 15.
    assert reference["median_first_stop"] == 21
    assert reference["first_stop_p25"] == 18
    assert reference["first_stop_p75"] == 23
    assert reference["most_common_stops"] == 1
    assert reference["opening_compound"] == "Medium"
    assert reference["finishing_compound"] == "Hard"
    assert reference["pit_loss_seconds"] is None


@pytest.mark.unit
@pytest.mark.parametrize("laps", [None, pd.DataFrame()])
def test_an_edition_with_no_laps_cannot_be_summarised(laps):
    assert module._summarize_circuit_edition({"laps": laps}, 2023) is None


@pytest.mark.unit
def test_an_edition_whose_laps_are_all_numbered_zero_cannot_be_summarised():
    """A formation-lap-only frame has no race distance to plan against."""
    rows = stint_rows("VER", [("MEDIUM", 1, 3)])
    for row in rows:
        row["LapNumber"] = 0.0

    assert module._summarize_circuit_edition({"laps": laps_frame(rows)}, 2023) is None


@pytest.mark.unit
def test_an_edition_whose_field_never_pitted_cannot_be_summarised():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 50)]))

    assert module._summarize_circuit_edition({"laps": laps}, 2023) is None


@pytest.mark.unit
def test_drivers_without_stint_data_do_not_enter_the_sample():
    rows = stint_rows("LAW", [("MEDIUM", 1, 30)])
    for row in rows:
        row["Stint"] = None
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]), rows)

    reference = module._summarize_circuit_edition({"laps": laps}, 2023)

    assert reference["sample_size"] == 1


@pytest.mark.unit
def test_a_single_stint_driver_contributes_no_finishing_compound():
    """One driver pits, the other never does — the latter has no last stint."""
    laps = laps_frame(
        stint_rows("VER", [("SOFT", 1, 20), ("MEDIUM", 21, 50)]),
        stint_rows("NOR", [("SOFT", 1, 50)]),
    )

    reference = module._summarize_circuit_edition({"laps": laps}, 2023)

    assert reference["opening_compound"] == "Soft"
    assert reference["finishing_compound"] == "Medium"
    # One stop each way; the tie resolves to the first count seen.
    assert reference["most_common_stops"] == 1


# ---------------------------------------------------------------------------
# circuit_strategy_reference
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_location_string_is_reduced_to_its_city(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2024: schedule_frame([(12, "Budapest")])},
        races={2024: {"laps": _field_race()}},
    )

    reference = module.circuit_strategy_reference("Budapest, Hungary", 2024)

    assert reference["source_year"] == 2024
    assert seen["races"] == [(2024, 12)]


@pytest.mark.unit
def test_an_empty_location_is_rejected_before_any_lookup(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(monkeypatch)

    assert module.circuit_strategy_reference("", 2024) is None
    assert module.circuit_strategy_reference("  ,  ", 2024) is None
    assert seen["schedules"] == []


@pytest.mark.unit
def test_the_search_walks_backwards_to_the_most_recent_usable_edition(
    monkeypatch: pytest.MonkeyPatch,
):
    schedule = schedule_frame([(12, "Budapest")])
    seen = _stub_seasons(
        monkeypatch,
        schedules={2024: schedule, 2023: schedule, 2022: schedule},
        races={2024: None, 2023: {"laps": _field_race()}},
    )

    reference = module.circuit_strategy_reference("Budapest", 2024)

    assert reference["source_year"] == 2023
    assert seen["schedules"] == [2024, 2023]
    assert seen["races"] == [(2024, 12), (2023, 12)]


@pytest.mark.unit
def test_a_renamed_circuit_is_matched_by_substring(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(
        monkeypatch,
        schedules={2024: schedule_frame([(1, "Sakhir"), (12, "Budapest, Hungary")])},
        races={2024: {"laps": _field_race()}},
    )

    assert module.circuit_strategy_reference("Budapest", 2024)["source_year"] == 2024


@pytest.mark.unit
def test_a_season_the_circuit_is_absent_from_is_skipped(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={
            2024: schedule_frame([(1, "Sakhir")]),
            2023: schedule_frame([(12, "Budapest")]),
        },
        races={2023: {"laps": _field_race()}},
    )

    reference = module.circuit_strategy_reference("Budapest", 2024)

    assert reference["source_year"] == 2023
    assert seen["races"] == [(2023, 12)]


@pytest.mark.unit
def test_a_season_whose_schedule_fails_to_load_is_skipped(monkeypatch: pytest.MonkeyPatch):
    _stub_seasons(
        monkeypatch,
        schedules={2024: RuntimeError("network down"), 2023: schedule_frame([(12, "Budapest")])},
        races={2023: {"laps": _field_race()}},
    )

    assert module.circuit_strategy_reference("Budapest", 2024)["source_year"] == 2023


@pytest.mark.unit
def test_an_edition_whose_summary_raises_is_skipped(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(12, "Budapest")])
    _stub_seasons(
        monkeypatch,
        schedules={2024: schedule, 2023: schedule},
        races={2024: {}, 2023: {"laps": _field_race()}},
    )

    assert module.circuit_strategy_reference("Budapest", 2024)["source_year"] == 2023


@pytest.mark.unit
def test_a_circuit_with_no_usable_edition_returns_nothing(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(monkeypatch)

    assert module.circuit_strategy_reference("Nowhere", 2024) is None
    # Searched back to the 2018 data floor and gave up rather than inventing one.
    assert seen["schedules"] == list(range(2024, 2017, -1))


@pytest.mark.unit
def test_a_repeat_request_is_served_from_the_cache(monkeypatch: pytest.MonkeyPatch):
    seen = _stub_seasons(
        monkeypatch,
        schedules={2024: schedule_frame([(12, "Budapest")])},
        races={2024: {"laps": _field_race()}},
    )

    first = module.circuit_strategy_reference("Budapest", 2024)
    second = module.circuit_strategy_reference("Budapest, Hungary", 2024)

    assert first is second
    assert seen["races"] == [(2024, 12)]


@pytest.mark.unit
def test_a_miss_is_cached_too_so_the_search_is_not_repeated(
    monkeypatch: pytest.MonkeyPatch,
):
    seen = _stub_seasons(monkeypatch)

    assert module.circuit_strategy_reference("Nowhere", 2024) is None
    assert module.circuit_strategy_reference("Nowhere", 2024) is None
    assert seen["schedules"] == list(range(2024, 2017, -1))


@pytest.mark.unit
def test_each_season_gets_its_own_cache_entry(monkeypatch: pytest.MonkeyPatch):
    schedule = schedule_frame([(12, "Budapest")])
    _stub_seasons(
        monkeypatch,
        schedules={2024: schedule, 2023: schedule},
        races={2024: {"laps": _field_race()}, 2023: {"laps": _field_race()}},
    )

    module.circuit_strategy_reference("Budapest", 2024)
    module.circuit_strategy_reference("Budapest", 2023)

    assert set(module._circuit_reference_cache) == {"Budapest_2024", "Budapest_2023"}
