"""Can a rival still beat the championship leader? The one rule every title read shares.

Pure: no I/O. A rival is out once the leader's lead is more than the most the
rival can gain in what is left, and the title is decided once every rival is
out. The most an entrant can gain is its best possible score while the leader
scores nothing:

* **A driver's** best is a win: 25 points a Grand Prix and 8 a sprint.
* **A team's** best is a one-two, because both cars score: 25 + 18 = 43 a Grand
  Prix and 8 + 7 = 15 a sprint.

**A deficit exactly equal to what is left** is bridged only one way: the rival
takes that best score in every session left and the leader scores nothing. Level
on points, the FIA count-back decides (most Grand Prix wins, then seconds, and
so on; sprint places take no part), the same count-back ``standings_table``
orders the table with. That scenario fixes what the rival adds to it, a win per
Grand Prix (a win and a second for a team), and the leader's worst case adds
nothing, since a classified place outside the points can only help the leader
in a count-back. So the tie is decided exactly: the rival is out only when the
leader would still win that count-back outright. One level all the way down
goes to the FIA's own criteria, so that rival stays in.

Points left are the caller's to count, against the standings rather than the
clock (``stakes.points_left``): a round the table does not hold yet still counts
as to come, which can only delay a verdict, never bring one early.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.standings_table import countback

if TYPE_CHECKING:
    from app.data.standings_table import Standing


@dataclass(frozen=True)
class Scoring:
    """The most one entrant can score in a Grand Prix and in a sprint, and the places that takes."""

    per_race: int
    per_sprint: int
    #: The Grand Prix places a maximum race score is made of.
    race_places: tuple[int, ...]


DRIVERS = Scoring(per_race=25, per_sprint=8, race_places=(1,))
CONSTRUCTORS = Scoring(per_race=25 + 18, per_sprint=8 + 7, race_places=(1, 2))


@dataclass(frozen=True)
class Remaining:
    """Points-paying sessions still to count: Grands Prix and sprints."""

    races: int
    sprints: int


def max_points(remaining: Remaining, scoring: Scoring) -> int:
    """The most one entrant can still score."""
    return remaining.races * scoring.per_race + remaining.sprints * scoring.per_sprint


def _wins_tie(leader: Standing, rival: Standing, remaining: Remaining, scoring: Scoring) -> bool:
    """Whether the leader wins the count-back outright after the rival's perfect run."""
    rival_best = (*rival.finishes, *(scoring.race_places * remaining.races))
    return countback(leader.finishes) < countback(rival_best)


def can_still_beat(leader: Standing, rival: Standing, remaining: Remaining, scoring: Scoring) -> bool:
    """Whether ``rival`` can still finish the season ahead of ``leader``."""
    gap = leader.points - rival.points
    available = max_points(remaining, scoring)
    if gap != available:
        return gap < available
    return not _wins_tie(leader, rival, remaining, scoring)
