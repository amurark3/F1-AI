"""The starting grid for one round, with its provenance attached.

Three states, not one. Which source answered decides what the panel is allowed
to claim, so the source travels with the payload rather than being flattened
away:

1. **The official grid sheet** (:mod:`app.data.f1db_grid`) — the real starting
   order with penalties applied. f1db publishes qualifying, grid and race
   classification together once a round is complete, so this is what every past
   round returns and what no in-progress round does.
2. **The FIA's starting grid** (:func:`app.data.fia_documents.results.fia_starting_grid`)
   — the same sheet, read from the FIA's document as soon as the ingest holds
   it: the provisional grid on Saturday evening, the final one before the race.
   A provisional one is labelled so.
3. **The qualifying classification** (:func:`app.data.predictions.load_qualifying`)
   — available from the moment qualifying ends, hours before f1db catches up.
   It is *not* the grid: no penalty is applied to it. It is returned marked
   ``provisional`` with a warning saying so, because showing the qualifying
   order under a "starting grid" heading is wrong on every weekend a penalty is
   handed out.
4. **Nothing** — before qualifying has run there is no grid and no honest
   stand-in for one. The response says so instead of ordering the entry list by
   championship position and letting it read as a grid.

Every slot carries the FIA's rulings for that car (``reasons``: the ruling,
the offence and the stewards' document) whenever the store holds the FIA grid,
on f1db's sheet too. f1db records the places dropped and never the offence, and
nothing here infers one.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from app.data.canonical_names import CODE_UNRESOLVED, driver_identity, team_display_name
from app.data.f1db_grid import GridSlot, starting_grid
from app.data.fia_documents.results import fia_starting_grid
from app.data.jolpica import QUALIFYING_SOURCE, JolpicaUnavailableError, provisional_grid
from app.data.predictions import load_qualifying

if TYPE_CHECKING:
    from app.data.fia_documents.parsers.fields import RuledNote
    from app.data.fia_documents.results import FiaGrid

logger = structlog.get_logger()

SOURCE_OFFICIAL_GRID = "official_grid"
SOURCE_FIA_GRID = "fia_starting_grid"
SOURCE_QUALIFYING = "qualifying_classification"
SOURCE_NONE = "unavailable"

# Says only what the code knows: the sheet is missing from *our* dataset. That
# is true whether f1db has not released the round or this server is reading an
# old release — and the old wording ("has not been published") hid the second
# case for five rounds.
PROVISIONAL_WARNING = (
    "The official grid sheet for this round is not in our dataset yet. The "
    "order shown is the qualifying classification, so any grid penalty is not "
    "applied to it."
)
UNAVAILABLE_REASON = "No grid for this round yet — qualifying has not run, or its results are not available."
FIA_PROVISIONAL_WARNING = (
    "This is the FIA's provisional starting grid. The final grid, published before the race, can still change it."
)
_PLACES = re.compile(r"(\d+)\s+place\s+grid\s+penalty", re.IGNORECASE)
_BACK = re.compile(r"\bback\s+of\s+the\s+grid\b", re.IGNORECASE)
PENALTY_SOURCE_NOTE = (
    "Grid penalties are read from the published grid sheet, which records the "
    "places dropped but not the offence behind them."
)


def _ruling(note: RuledNote) -> dict:
    return {"ruling": note.ruling, "reason": note.reason, "document": note.document}


def _code(year: int, fia: FiaGrid, car: int) -> str:
    return fia.driver(year, car).code or str(car)


def _reasons(year: int, fia: FiaGrid | None) -> dict[str, list[dict]]:
    """Each car's rulings on the FIA grid (notes, then penalties), keyed by driver code."""
    if fia is None:
        return {}
    cars = {note.car for note in (*fia.grid.notes, *fia.grid.penalties)}
    return {_code(year, fia, car): [_ruling(note) for note in fia.rulings(car)] for car in cars}


def _fia_document(fia: FiaGrid | None) -> dict | None:
    return {"number": fia.grid.document, "final": fia.grid.final, "url": fia.url} if fia else None


def _fia_slot(year: int, fia: FiaGrid, car: int, position: int | None) -> GridSlot:
    rulings = [note.ruling for note in fia.grid.penalties if note.car == car]
    entry = fia.entries.get(car)
    driver = fia.driver(year, car)
    return GridSlot(
        driver_code=driver.code or str(car),
        driver_name=driver.name,
        team=team_display_name(year, entry.team if entry else None),
        position=position,
        qualifying_position=fia.qualified(car),
        penalty_positions=sum(int(match[1]) for ruling in rulings for match in _PLACES.finditer(ruling)) or None,
        start_from_back=any(_BACK.search(ruling) for ruling in rulings),
        pit_lane=position is None,
    )


def _fia_slots(year: int, fia: FiaGrid) -> tuple[GridSlot, ...]:
    """The FIA grid's slots in order, then its pit-lane starters, shaped like f1db's."""
    cars = [(slot.car, slot.position) for slot in fia.grid.slots]
    cars += [(start.car, None) for start in fia.grid.pit_lane]
    return tuple(_fia_slot(year, fia, car, position) for car, position in cars)


def _official_row(slot: GridSlot, reasons: dict[str, list[dict]]) -> dict:
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
        "reasons": reasons.get(slot.driver_code, []),
        CODE_UNRESOLVED: False,
    }


def _provisional_row(driver: dict) -> dict:
    """A qualifying row shaped like a grid row, with every penalty field empty.

    The penalty fields are absent rather than zero: nothing here has been
    checked against a grid sheet, and a zero would read as "no penalty". A
    driver no source could code keeps their slot with an empty code and
    ``code_unresolved`` set (:func:`app.data.predictions.openf1_qualifying.order_row`).
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
        "reasons": [],
        CODE_UNRESOLVED: bool(driver.get(CODE_UNRESOLVED)),
    }


def _jolpica_row(year: int, row: dict) -> dict:
    """A Jolpica qualifying row shaped like a grid row, named the way f1db names it."""
    driver = driver_identity(year, code=row["driverCode"], name=row["driverName"])
    return {
        **_provisional_row({"position": row["position"], "driver_code": row["driverCode"]}),
        "driver_name": driver.name,
        "team": team_display_name(year, row["constructorName"]),
    }


def _jolpica_qualifying(year: int, round_num: int) -> list[dict]:
    """Jolpica's qualifying order as grid rows; empty when it has none or cannot be read."""
    try:
        return [_jolpica_row(year, row) for row in provisional_grid(year, round_num)]
    except JolpicaUnavailableError as exc:
        logger.warning("race_grid.jolpica_unavailable", year=year, round=round_num, error=str(exc))
        return []


def _empty(year: int, round_num: int) -> dict:
    return {
        "year": year,
        "round": round_num,
        "available": False,
        "provisional": False,
        "source": SOURCE_NONE,
        "fia_document": None,
        "grid": [],
        "penalties": [],
        "warnings": [UNAVAILABLE_REASON],
    }


def _from_official(year: int, round_num: int, slots: tuple[GridSlot, ...], fia: FiaGrid | None) -> dict:
    reasons = _reasons(year, fia)
    grid = [_official_row(slot, reasons) for slot in slots]
    penalties = [row for row in grid if row["penalised"]]
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "provisional": False,
        "source": SOURCE_OFFICIAL_GRID,
        "fia_document": _fia_document(fia),
        "grid": grid,
        "penalties": penalties,
        "warnings": [PENALTY_SOURCE_NOTE] if penalties and fia is None else [],
    }


def _from_fia(year: int, round_num: int, fia: FiaGrid) -> dict:
    reasons = _reasons(year, fia)
    grid = [_official_row(slot, reasons) for slot in _fia_slots(year, fia)]
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "provisional": not fia.grid.final,
        "source": SOURCE_FIA_GRID,
        "fia_document": _fia_document(fia),
        "grid": grid,
        "penalties": [row for row in grid if row["penalised"]],
        "warnings": [] if fia.grid.final else [FIA_PROVISIONAL_WARNING],
    }


def _from_qualifying(year: int, round_num: int, rows: list[dict], source_detail: str) -> dict:
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "provisional": True,
        "source": SOURCE_QUALIFYING,
        "source_detail": source_detail,
        "fia_document": None,
        "grid": rows,
        "penalties": [],
        "warnings": [PROVISIONAL_WARNING],
    }


def build_starting_grid(year: int, round_num: int) -> dict:
    """Resolve the best available grid for a round, labelled with its source."""
    fia = fia_starting_grid(year, round_num)
    slots = starting_grid(year, round_num)
    if slots:
        logger.info("race_grid.official", year=year, round=round_num, slots=len(slots), fia=fia is not None)
        return _from_official(year, round_num, slots, fia)

    if fia is not None:
        logger.info("race_grid.fia", year=year, round=round_num, document=fia.grid.document, final=fia.grid.final)
        return _from_fia(year, round_num, fia)

    jolpica_rows = _jolpica_qualifying(year, round_num)
    if jolpica_rows:
        logger.info("race_grid.provisional", year=year, round=round_num, drivers=len(jolpica_rows), source="jolpica")
        return _from_qualifying(year, round_num, jolpica_rows, QUALIFYING_SOURCE)

    qualifying = load_qualifying(year, round_num)
    if qualifying:
        logger.info("race_grid.provisional", year=year, round=round_num, drivers=len(qualifying), source="openf1")
        return _from_qualifying(
            year, round_num, [_provisional_row(driver) for driver in qualifying], "openf1-qualifying"
        )

    logger.info("race_grid.unavailable", year=year, round=round_num)
    return _empty(year, round_num)
