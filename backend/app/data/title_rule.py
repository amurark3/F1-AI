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

**At one event** (``needs_at``, ``can_settle_at``, ``earliest``): the leader settles
the title against a rival X at event E for certain when the leader outscores X
at E by ``margin = left_after - lead`` points (``+ 1`` unless the count-back is
already won). A finish exactly one point short of that goes to the count-back on
E's places, which is not known in advance, so it takes three states: the count-back
is won even if X takes E's best places and the perfect run after it and the
leader adds nothing (the margin is exact); it is won only if the leader takes E's
best places and X nothing at E (``countback``: the quoted margin is the safe one,
one point more, and the line before it depends on the places); or it is not won.
Settling at E is possible when the leader's best weekend, with every rival
scoring nothing, leaves no rival able to beat them; ``earliest`` is the first
upcoming event where that holds.

Points left are the caller's to count, against the standings rather than the
clock (``stakes.points_left``): a round the table does not hold yet still counts
as to come, which can only delay a verdict, never bring one early.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from app.data.standings_table import countback

if TYPE_CHECKING:
    from collections.abc import Iterable

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


@dataclass(frozen=True)
class Need:
    """What the leader must do at one event against a rival still able to beat them."""

    rival: Standing
    #: The leader settles it against ``rival`` by outscoring them by at least this (at most 0: by not being outscored by more than -margin).
    margin: float
    #: A finish exactly one point short of ``margin`` turns on the count-back, i.e. on this event's places.
    countback: bool


def total(parts: Iterable[Remaining]) -> Remaining:
    """The sessions of every part, added."""
    parts = tuple(parts)
    return Remaining(sum(p.races for p in parts), sum(p.sprints for p in parts))


def decided(rows: tuple[Standing, ...], remaining: Remaining, scoring: Scoring) -> bool:
    """Whether the title is settled: a table of at least two with no rival able to beat the leader."""
    return len(rows) > 1 and not any(can_still_beat(rows[0], row, remaining, scoring) for row in rows[1:])


def _holds_tie(leader: Standing, rival: Standing, here: tuple[int, ...], run: tuple[int, ...]) -> bool | None:
    """Whether the leader wins a count-back at a finish level on points: True, None (depends on ``here``) or False."""
    if countback(leader.finishes) < countback((*rival.finishes, *here, *run)):
        return True
    if countback((*leader.finishes, *here)) < countback((*rival.finishes, *run)):
        return None
    return False


def _need(leader: Standing, rival: Standing, sessions: tuple[Remaining, Remaining], scoring: Scoring) -> Need:
    at, after = sessions
    here = scoring.race_places * at.races
    holds = _holds_tie(leader, rival, here, scoring.race_places * after.races)
    margin = max_points(after, scoring) - (leader.points - rival.points) + (0 if holds is True else 1)
    return Need(rival, margin, holds is None)


def needs_at(rows: tuple[Standing, ...], at: Remaining, after: Remaining, scoring: Scoring) -> tuple[Need, ...]:
    """One ``Need`` for every rival still able to beat the leader, the hardest first."""
    leader, ahead = rows[0], total((at, after))
    alive = (row for row in rows[1:] if can_still_beat(leader, row, ahead, scoring))
    return tuple(sorted((_need(leader, row, (at, after), scoring) for row in alive), key=lambda n: -n.margin))


def can_settle_at(rows: tuple[Standing, ...], at: Remaining, after: Remaining, scoring: Scoring) -> bool:
    """Whether the leader's best weekend, against rivals who score nothing, decides the title at ``at``."""
    leader = rows[0]
    best = replace(
        leader,
        points=leader.points + max_points(at, scoring),
        finishes=(*leader.finishes, *(scoring.race_places * at.races)),
    )
    return not any(can_still_beat(best, row, after, scoring) for row in rows[1:])


def earliest(rows: tuple[Standing, ...], upcoming: tuple[Remaining, ...], scoring: Scoring) -> int | None:
    """Index of the first upcoming event where the leader can settle the title, or None."""
    for i in range(len(upcoming)):
        if can_settle_at(rows, total(upcoming[: i + 1]), total(upcoming[i + 1 :]), scoring):
            return i
    return None
