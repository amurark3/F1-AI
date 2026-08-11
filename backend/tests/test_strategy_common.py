"""Shared laps builders for the strategy slice, plus the package's public surface.

``app.data.strategy`` is the only part of the backend that reads a FastF1 *laps*
table rather than a classification table, so every module in the slice needs the
same scaffolding: rows carrying stint numbers, compounds, lap times and pit
markers. Building that once here keeps each module's own tests about behaviour
rather than about frame construction.

The risk this file itself pins is the package surface: ``analyze_pit_strategy``
and ``circuit_strategy_reference`` are the two functions the API and the MCP
tools import. Everything else is private and is imported directly by whichever
test module covers it.

Every strategy cache is a module-global dict that is never evicted, so
``reset_strategy_caches`` is wired into an autouse fixture in each test module —
a cached race would otherwise leak a fake session into the next test.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data import strategy
from app.data.strategy import history, pit, reference, session

# ---------------------------------------------------------------------------
# Laps / results / schedule builders
# ---------------------------------------------------------------------------


def lap_row(driver: str, lap_number: float, stint: float, **fields) -> dict:
    """One laps-table row with the columns FastF1 always supplies.

    Defaults describe a clean green-flag lap: no pit markers, a 90-second lap on
    mediums, track status 1 (clear).
    """
    row = {
        "Driver": driver,
        "LapNumber": float(lap_number),
        "Stint": float(stint),
        "Compound": "MEDIUM",
        "LapTime": pd.Timedelta(seconds=90),
        "FreshTyre": True,
        "Position": 1.0,
        "TrackStatus": "1",
        "PitInTime": pd.NaT,
        "PitOutTime": pd.NaT,
    }
    row.update(fields)
    return row


def stint_rows(driver: str, stint: float, lap_numbers, **fields) -> list[dict]:
    """A run of laps on one set of tyres — a stint."""
    return [lap_row(driver, number, stint, **fields) for number in lap_numbers]


def laps_frame(rows: list[dict]) -> pd.DataFrame:
    """The laps table for a race."""
    return pd.DataFrame(rows)


def results_frame(finishers) -> pd.DataFrame:
    """A classification frame from ``[("VER", 1), ("LEC", 2)]`` pairs."""
    return pd.DataFrame([{"Abbreviation": code, "Position": position} for code, position in finishers])


def schedule_frame(locations) -> pd.DataFrame:
    """A season event schedule; round numbers follow the listed order."""
    return pd.DataFrame(
        [{"RoundNumber": number, "Location": location} for number, location in enumerate(locations, start=1)]
    )


def vanishing_slice_frame(rows: list[dict], column: str) -> pd.DataFrame:
    """A laps frame whose ``column == value`` slice comes back empty.

    Both ``_extract_stint_data`` and ``_estimate_pit_loss`` loop over the values
    of a column and then re-select the rows carrying each one, guarding against
    a slice that turns out to be empty. With ordinary values that guard cannot
    fire: pandas compares each cell against the scalar with an identity fast
    path, so a value taken from ``.unique()`` always matches at least its own
    row, and anything NaN-like was already dropped. Producing the empty slice
    directly is the only way to execute those two guards — they are dead
    defensive code otherwise.
    """

    class _VanishingSlice(pd.DataFrame):
        @property
        def _constructor(self) -> type[_VanishingSlice]:
            return _VanishingSlice

        def __getitem__(self, key):
            if getattr(key, "name", None) == column:
                return self.iloc[0:0]
            return super().__getitem__(key)

    return _VanishingSlice(rows)


# ---------------------------------------------------------------------------
# Cache isolation
# ---------------------------------------------------------------------------


def reset_strategy_caches() -> None:
    """Empty every module-global strategy cache.

    None of them is ever evicted in production, so a race loaded by one test
    would otherwise be served to the next one from memory.
    """
    session._race_data_cache.clear()
    history._historical_cache.clear()
    history._safety_car_cache.clear()
    reference._circuit_reference_cache.clear()


@pytest.fixture(autouse=True)
def _clear_strategy_caches():
    reset_strategy_caches()
    yield
    reset_strategy_caches()


# ---------------------------------------------------------------------------
# Package surface
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_package_exports_only_the_two_entry_points():
    assert strategy.__all__ == ["analyze_pit_strategy", "circuit_strategy_reference"]


@pytest.mark.unit
def test_the_exported_names_are_the_implementations_not_copies():
    assert strategy.analyze_pit_strategy is pit.analyze_pit_strategy
    assert strategy.circuit_strategy_reference is reference.circuit_strategy_reference
