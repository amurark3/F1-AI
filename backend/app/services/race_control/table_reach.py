"""What each row of a standings table can still reach: the title rule over a whole table.

``title_rule.can_still_beat`` answers for one pair. A page reading a team's
place asks it of several (can this team still pass the one ahead, can the one
behind still pass it, is the title decided), so this holds the table and what
is still to score, and every answer here is that rule. What is left is counted
as the stakes count it (``stakes.points_left``): against the table's round, not
the clock.

Without a calendar nothing is known about what is left, so every answer is
``None``. A caller says nothing about reach then, rather than guess either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.data.title_rule import CONSTRUCTORS, Remaining, Scoring, can_still_beat, max_points
from app.services.race_control.stakes import points_left
from app.services.race_control.strategy_context import season_events

if TYPE_CHECKING:
    from app.data.current_standings import CurrentStandings
    from app.data.standings_table import Standing

logger = structlog.get_logger()


@dataclass(frozen=True)
class TableReach:
    """A standings table, in order, and the points-paying sessions still to score."""

    rows: tuple[Standing, ...]
    scoring: Scoring
    #: ``None`` when the calendar could not be read.
    remaining: Remaining | None

    @property
    def leader_points(self) -> float:
        return self.rows[0].points if self.rows else 0

    @property
    def points_on_offer(self) -> int | None:
        """The most one entrant can still score."""
        return None if self.remaining is None else max_points(self.remaining, self.scoring)

    def can_pass(self, chaser: str, target: str) -> bool | None:
        """Whether the ``chaser`` row can still finish the season ahead of the ``target`` row (keys)."""
        if self.remaining is None:
            return None
        rows = {row.key: row for row in self.rows}
        return can_still_beat(rows[target], rows[chaser], self.remaining, self.scoring)

    def decided(self) -> bool | None:
        """Whether no rival can still finish ahead of the leader."""
        if self.remaining is None:
            return None
        if len(self.rows) < 2:
            return False
        leader = self.rows[0].key
        return not any(self.can_pass(row.key, leader) for row in self.rows[1:])

    def highest_in_reach(self, key: str) -> tuple[int, Standing] | None:
        """The highest place above ``key`` it can still take, and the row holding it."""
        above = self.rows[: [row.key for row in self.rows].index(key)]
        return next(((place, row) for place, row in enumerate(above, start=1) if self.can_pass(key, row.key)), None)


def remaining_after(year: int, as_of_round: int | None) -> Remaining | None:
    """Grands Prix and sprints the table after ``as_of_round`` does not hold yet; ``None`` without a calendar.

    An empty calendar is an unreadable one, not a finished season: read as
    nothing left, it would call every title decided.
    """
    try:
        events = season_events(year)
    except Exception as exc:
        logger.warning("race_control.table_reach.calendar_failed", year=year, error=str(exc))
        return None
    if not events:
        return None
    left = points_left(events, None, as_of_round, datetime.now(UTC))
    return Remaining(races=left.races, sprints=left.sprints)


def constructors_reach(standings: CurrentStandings) -> TableReach:
    """The constructors' table and what is left to score after its round."""
    return TableReach(
        rows=standings.teams,
        scoring=CONSTRUCTORS,
        remaining=remaining_after(standings.year, standings.as_of_round),
    )
