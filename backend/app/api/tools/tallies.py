"""Counts over a query's rows, done in code so the model does not do them in prose.

Given the right rows, the model still miscounted: it paired a driver with the
team of another driver in the same row ("Norris (Mercedes)"), merged one
driver's wins from two weekends into a "double", and summed a team's points
with a rival's win folded in. Each was a group-by attempted while writing
prose, which a language model does unreliably and this module does exactly.

Columns are read by their headers and values, since the model chooses the
aliases: a header naming a team or constructor marks a team column, one naming
points (with every value numeric) a points column, and any column of strings a
name column. Each name column takes the team and points columns that follow it,
up to the next name column — the order every results query is written in.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
import re

MIN_ROWS = 2
MAX_LINES = 8

_TEAM_HEADER = re.compile(r"team|constructor", re.IGNORECASE)
_POINTS_HEADER = re.compile(r"point|pts", re.IGNORECASE)


@dataclass(frozen=True)
class _Group:
    """A column to tally, with the team and points columns that describe it."""

    column: str
    is_team: bool
    team: str | None
    points: str | None


def _values(rows: list[dict], column: str) -> list[object]:
    return [row.get(column) for row in rows]


def _is_text(rows: list[dict], column: str) -> bool:
    return all(isinstance(value, str) and value for value in _values(rows, column))


def _is_points(rows: list[dict], column: str) -> bool:
    numeric = all(isinstance(v, int | float) and not isinstance(v, bool) for v in _values(rows, column))
    return numeric and bool(_POINTS_HEADER.search(column))


def _groups(columns: list[str], rows: list[dict]) -> list[_Group]:
    """Each string column, with the team and points columns that follow it."""
    text = [c for c in columns if _is_text(rows, c)]
    groups = []
    for index, column in enumerate(columns):
        if column not in text:
            continue
        is_team = bool(_TEAM_HEADER.search(column))
        team = points = None
        for later in columns[index + 1 :]:
            later_is_team = later in text and bool(_TEAM_HEADER.search(later))
            if later in text and (is_team or not later_is_team):
                break  # the next column this one does not own
            if later_is_team and team is None:
                team = later
            elif _is_points(rows, later) and points is None:
                points = later
        groups.append(_Group(column, is_team, team, points))
    return groups


def _entry(rows: list[dict], group: _Group, value: str, count: int) -> str:
    """'George Russell (Mercedes) ×3, 24 pts' for one value of one column."""
    own_rows = [row for row in rows if row[group.column] == value]
    label = value
    if group.team:
        teams = list(dict.fromkeys(row[group.team] for row in own_rows))
        label = f"{value} ({'/'.join(teams)})"
    text = f"{label} ×{count}"
    if group.points:
        text += f", {sum(row[group.points] for row in own_rows):g} pts"
    return text


def _tally(rows: list[dict], group: _Group) -> str | None:
    counts = Counter(row[group.column] for row in rows)
    if max(counts.values()) < MIN_ROWS:
        return None  # every value unique: a ×1 list says nothing the table does not
    # Counter.most_common keeps first-seen order among ties, i.e. row order.
    entries = "; ".join(_entry(rows, group, value, count) for value, count in counts.most_common())
    return f"{group.column}: {entries}"


def _same_row(columns: list[str], rows: list[dict], first: str, second: str) -> str | None:
    """Rows where two name columns hold the same value — a real "double"."""
    if not {row[first] for row in rows} & {row[second] for row in rows}:
        return None  # different kinds of thing; comparing them means nothing
    matches = [row for row in rows if row[first] == row[second]]
    if not matches:
        return f"{first} = {second} in no row"
    key = columns[0]
    labels = [row[first] if key in (first, second) else f"{row[key]} ({row[first]})" for row in matches]
    return f"{first} = {second} in {len(matches)} of {len(rows)} rows: {', '.join(map(str, labels))}"


def tally_lines(columns: list[str], rows: list[dict]) -> list[str]:
    """The counts, pairings, points sums and same-row matches worth stating."""
    if len(rows) < MIN_ROWS:
        return []
    groups = _groups(columns, rows)
    tallies = [line for group in groups if (line := _tally(rows, group))]
    names = [group.column for group in groups if not group.is_team]
    matches = [line for first, second in combinations(names, 2) if (line := _same_row(columns, rows, first, second))]
    return [*tallies, *matches][:MAX_LINES]
