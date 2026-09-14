"""The starting grid for one round, with its provenance attached.

Three states, not one. Which source answered decides what the panel is allowed
to claim, so the source travels with the payload rather than being flattened
away:

1. **The official grid sheet** (:mod:`app.data.f1db_grid`) — the real starting
   order with penalties applied. f1db publishes qualifying, grid and race
   classification together once a round is complete, so this is what every past
   round returns and what no in-progress round does.
2. **The qualifying classification** (:func:`app.data.predictions.load_qualifying`)
   — available from the moment qualifying ends, hours before f1db catches up.
   It is *not* the grid: no penalty is applied to it. It is returned marked
   ``provisional`` with a warning saying so, because showing the qualifying
   order under a "starting grid" heading is wrong on every weekend a penalty is
   handed out.
3. **Nothing** — before qualifying has run there is no grid and no honest
   stand-in for one. The response says so instead of ordering the entry list by
   championship position and letting it read as a grid.

The offence behind a penalty (gearbox, power unit, impeding) is not recorded in
f1db and is not inferred here.
"""

from __future__ import annotations

import structlog

from app.data.f1db_grid import GridSlot, starting_grid
from app.data.predictions import load_qualifying

logger = structlog.get_logger()

SOURCE_OFFICIAL_GRID = "official_grid"
SOURCE_QUALIFYING = "qualifying_classification"
SOURCE_NONE = "unavailable"

PROVISIONAL_WARNING = (
    "The official grid sheet for this round has not been published yet. The "
    "order shown is the qualifying classification, so any grid penalty is not "
    "applied to it."
)
UNAVAILABLE_REASON = (
    "No grid for this round yet — qualifying has not run, or its results are "
    "not available."
)
PENALTY_SOURCE_NOTE = (
    "Grid penalties are read from the published grid sheet, which records the "
    "places dropped but not the offence behind them."
)


def _official_row(slot: GridSlot) -> dict:
    return {
        "driver_code": slot.driver_code,
        "driver_name": slot.driver_name,
        "team": slot.team,
        "position": slot.position,
        "qualifying_position": slot.qualifying_position,
        "penalty_positions": slot.penalty_positions,
        "start_from_back": slot.start_from_back,
        "pit_lane": slot.pit_lane,
        "penalised": slot.penalised,
        "places_lost": slot.places_lost,
    }


def _provisional_row(driver: dict) -> dict:
    """A qualifying row shaped like a grid row, with every penalty field empty.

    The penalty fields are absent rather than zero: nothing here has been
    checked against a grid sheet, and a zero would read as "no penalty".
    """
    position = driver.get("position")
    return {
        "driver_code": driver.get("driver_code", ""),
        "driver_name": driver.get("driver_name", "") or driver.get("driver_code", ""),
        "team": driver.get("team", ""),
        "position": position,
        "qualifying_position": position,
        "penalty_positions": None,
        "start_from_back": False,
        "pit_lane": False,
        "penalised": False,
        "places_lost": None,
    }


def _empty(year: int, round_num: int) -> dict:
    return {
        "year": year,
        "round": round_num,
        "available": False,
        "provisional": False,
        "source": SOURCE_NONE,
        "grid": [],
        "penalties": [],
        "warnings": [UNAVAILABLE_REASON],
    }


def _from_official(year: int, round_num: int, slots: tuple[GridSlot, ...]) -> dict:
    grid = [_official_row(slot) for slot in slots]
    penalties = [row for row in grid if row["penalised"]]
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "provisional": False,
        "source": SOURCE_OFFICIAL_GRID,
        "grid": grid,
        "penalties": penalties,
        "warnings": [PENALTY_SOURCE_NOTE] if penalties else [],
    }


def _from_qualifying(year: int, round_num: int, drivers: list[dict]) -> dict:
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "provisional": True,
        "source": SOURCE_QUALIFYING,
        "grid": [_provisional_row(driver) for driver in drivers],
        "penalties": [],
        "warnings": [PROVISIONAL_WARNING],
    }


def build_starting_grid(year: int, round_num: int) -> dict:
    """Resolve the best available grid for a round, labelled with its source."""
    slots = starting_grid(year, round_num)
    if slots:
        logger.info("race_grid.official", year=year, round=round_num, slots=len(slots))
        return _from_official(year, round_num, slots)

    qualifying = load_qualifying(year, round_num)
    if qualifying:
        logger.info("race_grid.provisional", year=year, round=round_num, drivers=len(qualifying))
        return _from_qualifying(year, round_num, qualifying)

    logger.info("race_grid.unavailable", year=year, round=round_num)
    return _empty(year, round_num)
