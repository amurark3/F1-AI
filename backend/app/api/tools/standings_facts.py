"""The facts a standings tool states beside its table: how fresh it is, and where the title stands.

The assistant reads these rather than working them out. Left to itself it
would quote a table without saying it is provisional, or do its own "can still
catch" arithmetic. So each tool result states:

* **the round** the table runs to, and whether f1db has confirmed it
  (``current_standings``);
* **the title state** from the shared rule (``title_rule``, read over the whole
  table by ``table_reach``): decided for whom, or open and who can still finish
  ahead of the leader. Without a calendar nothing is claimed either way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.race_control_common import pluralise

if TYPE_CHECKING:
    from app.data.current_standings import CurrentStandings
    from app.data.standings_table import Standing
    from app.services.race_control.table_reach import TableReach


def _rounds(numbers: list[int]) -> str:
    return f"round {numbers[0]}" if len(numbers) == 1 else f"rounds {', '.join(map(str, numbers))}"


def _provisional_basis(sources: tuple[dict, ...]) -> str:
    """Where a provisional table's points come from: f1db's base (if any) plus OpenF1's later rounds."""
    added = _rounds([source["round"] for source in sources if source["role"] == "points"])
    base = next((source["through_round"] for source in sources if source["role"] == "base"), None)
    if base is None:
        return f"OpenF1's results for {added} (f1db holds none of this season yet)"
    return f"f1db's table through round {base} plus OpenF1's results for {added}"


def freshness_line(standings: CurrentStandings) -> str:
    """The round the table runs to, and whether f1db has confirmed it."""
    as_of = standings.as_of_round
    if not standings.provisional:
        return f"After round {as_of} · confirmed: f1db's published table."
    return (
        f"After round {as_of} · provisional: {_provisional_basis(standings.sources)}. "
        f"f1db has not confirmed round {as_of} yet, so post-race penalties can still change it."
    )


def _who(row: Standing) -> str:
    """A driver by name and code; a team (keyed by its name) by name alone."""
    return row.name if row.name == row.key else f"{row.name} ({row.key})"


def _left(reach: TableReach) -> str:
    remaining = reach.remaining
    return (
        f"with at most {reach.points_on_offer} points left for one entrant "
        f"({pluralise(remaining.races, 'Grand Prix', 'Grands Prix')}, {pluralise(remaining.sprints, 'sprint')})"
    )


def _decided(reach: TableReach) -> str:
    leader, second = reach.rows[0], reach.rows[1]
    return (
        f"decided for {_who(leader)}. Leader: {leader.points:g} points, {leader.points - second.points:g} ahead of "
        f"{_who(second)}, {_left(reach)}: no rival can still finish ahead."
    )


def _open(reach: TableReach, rivals: tuple[Standing, ...]) -> str:
    leader = reach.rows[0]
    chasers = ", ".join(f"{_who(row)} ({row.points:g} points, {leader.points - row.points:g} behind)" for row in rivals)
    return (
        f"still open. Leader: {_who(leader)}, {leader.points:g} points, {_left(reach)}. "
        f"Only these can still finish ahead of {_who(leader)}: {chasers or 'none'}."
    )


def title_line(reach: TableReach, championship: str) -> str:
    """Where ``championship``'s title stands ("Drivers'" or "Constructors'"), by the shared rule."""
    rivals = reach.rivals_in_reach()
    if rivals is None:
        state = (
            "not stated. The season calendar could not be read, so the points still on offer are unknown: "
            "do not say whether the title is decided."
        )
    elif reach.decided():
        state = _decided(reach)
    else:
        state = _open(reach, rivals)
    return f"**{championship} title:** {state}"
