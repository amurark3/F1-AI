"""Official starting grid and grid penalties from the local f1db dataset.

The starting grid is a *different fact* from the qualifying classification, and
the difference is exactly what this module exists to expose. A driver who
qualifies third and takes a five-place gearbox penalty starts eighth; a driver
sent to the back of the grid or released from the pit lane has no grid slot at
all. Reading the qualifying order and calling it "the grid" is wrong on any
weekend a penalty is applied, which is most of them.

f1db records the grid sheet under ``race_data.type = 'STARTING_GRID_POSITION'``:

``starting_grid_position_qualification_position_number``
    Where the driver qualified, before any penalty.
``starting_grid_position_grid_penalty``
    The penalty as published: a number of places, or ``"SFB"`` for a
    start-from-the-back sanction.
``starting_grid_position_grid_penalty_positions``
    The same penalty as an integer. ``NULL`` for ``"SFB"``, which has no
    fixed place count.
``position_text = 'PL'``
    A pit-lane start. ``position_number`` is ``NULL`` for these rows because
    the driver occupies no grid slot.

What f1db does **not** carry is the *offence* — no gearbox/engine/impeding
reason is recorded anywhere in the dataset. Callers must not invent one.

Availability follows the dataset's release cadence, not the race weekend's:
f1db publishes qualifying, grid and race classification together once a round
is complete, so the grid for a round still being run is simply absent here.
:mod:`app.services.race_grid` owns that fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.f1db_source import connect

logger = structlog.get_logger()

# f1db's marker for a start-from-the-back sanction, stored in the penalty
# column in place of a place count.
PENALTY_START_FROM_BACK = "SFB"

# The two grids a weekend can publish. A sprint grid is recorded with the same
# column family as the Grand Prix grid — qualification position, penalty and
# penalty places — so one reader serves both.
TYPE_RACE_GRID = "STARTING_GRID_POSITION"
TYPE_SPRINT_GRID = "SPRINT_STARTING_GRID_POSITION"

# f1db's ``position_text`` for a driver released from the pit lane, who holds
# no grid slot and therefore has a NULL ``position_number``.
POSITION_TEXT_PIT_LANE = "PL"

_GRID_QUERY = """
    SELECT rd.position_number AS position,
           rd.position_text AS position_text,
           d.abbreviation AS code,
           d.name AS name,
           con.name AS team,
           rd.starting_grid_position_qualification_position_number AS qualifying_position,
           rd.starting_grid_position_grid_penalty AS penalty,
           rd.starting_grid_position_grid_penalty_positions AS penalty_positions
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor con ON con.id = rd.constructor_id
    WHERE r.year = ? AND r.round = ? AND rd.type = ?
    ORDER BY rd.position_display_order
"""


@dataclass(frozen=True)
class GridSlot:
    """One driver's place on the published starting grid."""

    driver_code: str
    driver_name: str
    team: str
    #: Grid slot, or ``None`` for a pit-lane start.
    position: int | None
    #: Where the driver qualified, or ``None`` when f1db has no quali row.
    qualifying_position: int | None
    #: Places dropped, or ``None`` for an unquantified sanction.
    penalty_positions: int | None
    #: True for a start-from-the-back sanction.
    start_from_back: bool
    #: True for a pit-lane start.
    pit_lane: bool

    @property
    def penalised(self) -> bool:
        """Whether any sanction moved this driver off their qualifying slot."""
        return self.pit_lane or self.start_from_back or bool(self.penalty_positions)

    @property
    def places_lost(self) -> int | None:
        """Slots actually dropped between qualifying and the grid.

        Derived from the two published positions rather than the penalty
        column, because a penalty of five places moves a driver fewer than
        five slots when a driver ahead of them is also penalised.
        """
        if self.position is None or self.qualifying_position is None:
            return None
        return self.position - self.qualifying_position


def _slot_from_row(row) -> GridSlot:
    penalty = row["penalty"]
    return GridSlot(
        driver_code=row["code"],
        driver_name=row["name"],
        team=row["team"],
        position=None if row["position"] is None else int(row["position"]),
        qualifying_position=(
            None if row["qualifying_position"] is None else int(row["qualifying_position"])
        ),
        penalty_positions=(
            None if row["penalty_positions"] is None else int(row["penalty_positions"])
        ),
        start_from_back=penalty == PENALTY_START_FROM_BACK,
        pit_lane=row["position_text"] == POSITION_TEXT_PIT_LANE,
    )


def starting_grid(
    year: int,
    round_num: int,
    result_type: str = TYPE_RACE_GRID,
) -> tuple[GridSlot, ...]:
    """The published grid for a round, in starting order.

    Args:
        year: Season.
        round_num: Round within the season.
        result_type: Which grid to read — :data:`TYPE_RACE_GRID` (default) or
            :data:`TYPE_SPRINT_GRID` for the sprint's own grid, which is a
            separate sheet with its own penalties.

    Returns an empty tuple when f1db holds no such grid for the round — which
    is the normal state for a weekend that has not finished yet, and for the
    sprint grid of any weekend that has no sprint. Neither is an error.
    """
    with connect() as conn:
        rows = conn.execute(_GRID_QUERY, (year, round_num, result_type)).fetchall()

    slots = tuple(_slot_from_row(row) for row in rows if row["code"])
    logger.info(
        "f1db_grid.loaded",
        year=year,
        round=round_num,
        result_type=result_type,
        slots=len(slots),
        penalised=sum(1 for slot in slots if slot.penalised),
    )
    return slots
