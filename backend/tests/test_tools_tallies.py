"""Tests for app.api.tools.tallies — the counting the model must not do itself.

Given the right six rows, the model still wrote "Mercedes (Russell ×3, Norris
×1)", priced a team at 132 points instead of 107, and called Norris's split
weekend a "double". Each is a group-by the model attempted in prose. These
tests pin the counts the tool now does in code:

* **Each driver is paired with the team in their own row** — never a team
  that merely shares the row with them.
* **Counts and points sums are per value**, most frequent first.
* **Same-value rows across two columns are listed** — a real "double" — and
  an explicit "no row" when there is none.
* **Nothing is said when there is nothing to count**, so the note never pads
  an answer with ×1 lists.
"""

from __future__ import annotations

import pytest

from app.api.tools.tallies import tally_lines

# The six rows behind the production answers that went wrong.
_COLUMNS = ["round", "sprint_winner", "sprint_team", "sprint_points", "race_winner", "race_team", "race_points"]
_SEASON = [
    (2, "George Russell", "Mercedes", 8, "Kimi Antonelli", "Mercedes", 25),
    (4, "Lando Norris", "McLaren", 8, "Kimi Antonelli", "Mercedes", 25),
    (5, "George Russell", "Mercedes", 8, "Kimi Antonelli", "Mercedes", 25),
    (9, "Kimi Antonelli", "Mercedes", 8, "Charles Leclerc", "Ferrari", 25),
    (12, "George Russell", "Mercedes", 8, "Lando Norris", "McLaren", 25),
    (17, "Max Verstappen", "Red Bull", 8, "Max Verstappen", "Red Bull", 25),
]
_ROWS = [dict(zip(_COLUMNS, values, strict=True)) for values in _SEASON]


@pytest.mark.unit
def test_each_driver_is_paired_with_the_team_in_their_own_row():
    """Norris shares both his rows with a Mercedes driver; he is still McLaren."""
    lines = tally_lines(_COLUMNS, _ROWS)

    assert (
        "sprint_winner: George Russell (Mercedes) ×3, 24 pts; Lando Norris (McLaren) ×1, 8 pts; "
        "Kimi Antonelli (Mercedes) ×1, 8 pts; Max Verstappen (Red Bull) ×1, 8 pts"
    ) in lines
    assert (
        "race_winner: Kimi Antonelli (Mercedes) ×3, 75 pts; Charles Leclerc (Ferrari) ×1, 25 pts; "
        "Lando Norris (McLaren) ×1, 25 pts; Max Verstappen (Red Bull) ×1, 25 pts"
    ) in lines


@pytest.mark.unit
def test_team_columns_are_counted_with_their_points():
    """The model summed Mercedes to 132 by folding in a McLaren win."""
    lines = tally_lines(_COLUMNS, _ROWS)

    assert "sprint_team: Mercedes ×4, 32 pts; McLaren ×1, 8 pts; Red Bull ×1, 8 pts" in lines
    assert "race_team: Mercedes ×3, 75 pts; Ferrari ×1, 25 pts; McLaren ×1, 25 pts; Red Bull ×1, 25 pts" in lines


@pytest.mark.unit
def test_a_driver_in_two_columns_of_the_same_row_is_listed():
    """Only Verstappen won both on one weekend; Norris's wins were two weekends apart."""
    assert "sprint_winner = race_winner in 1 of 6 rows: 17 (Max Verstappen)" in tally_lines(_COLUMNS, _ROWS)


@pytest.mark.unit
def test_two_columns_that_share_values_but_never_a_row_say_so():
    rows = [
        {"round": 1, "sprint_winner": "Lando Norris", "race_winner": "George Russell"},
        {"round": 2, "sprint_winner": "George Russell", "race_winner": "Lando Norris"},
    ]

    assert "sprint_winner = race_winner in no row" in tally_lines(["round", "sprint_winner", "race_winner"], rows)


@pytest.mark.unit
def test_columns_with_no_shared_value_are_not_compared():
    """A driver column and a circuit column never hold the same thing."""
    rows = [{"gp": "Miami", "winner": "Lando Norris"}, {"gp": "Monaco", "winner": "Lando Norris"}]

    assert not any("=" in line for line in tally_lines(["gp", "winner"], rows))


@pytest.mark.unit
def test_a_column_where_every_value_is_unique_is_not_tallied():
    """Six distinct Grand Prix names counted ×1 each would only pad the answer."""
    lines = tally_lines(_COLUMNS, _ROWS)

    assert not any(line.startswith("round:") for line in lines)


@pytest.mark.unit
def test_a_driver_who_switched_teams_lists_both():
    rows = [
        {"winner": "Liam Lawson", "team": "Racing Bulls"},
        {"winner": "Liam Lawson", "team": "Red Bull"},
    ]

    assert tally_lines(["winner", "team"], rows) == ["winner: Liam Lawson (Racing Bulls/Red Bull) ×2"]


@pytest.mark.unit
def test_a_points_column_with_a_gap_is_not_summed():
    """A NULL among the points would make any total a guess."""
    rows = [{"winner": "Lando Norris", "points": 25}, {"winner": "Lando Norris", "points": None}]

    assert tally_lines(["winner", "points"], rows) == ["winner: Lando Norris ×2"]


@pytest.mark.unit
def test_a_points_column_is_only_attached_up_to_the_next_name_column():
    """race_points belongs to race_winner, not to the sprint_winner before it."""
    rows = [
        {"sprint_winner": "George Russell", "race_winner": "Kimi Antonelli", "race_points": 25},
        {"sprint_winner": "George Russell", "race_winner": "Kimi Antonelli", "race_points": 25},
    ]

    lines = tally_lines(["sprint_winner", "race_winner", "race_points"], rows)

    assert "sprint_winner: George Russell ×2" in lines
    assert "race_winner: Kimi Antonelli ×2, 50 pts" in lines


@pytest.mark.unit
def test_half_points_keep_their_fraction():
    rows = [{"winner": "Lewis Hamilton", "points": 12.5}, {"winner": "Lewis Hamilton", "points": 25}]

    assert tally_lines(["winner", "points"], rows) == ["winner: Lewis Hamilton ×2, 37.5 pts"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"winner": "Lando Norris", "team": "McLaren"}],
    ],
)
def test_fewer_than_two_rows_have_nothing_to_tally(rows):
    assert tally_lines(["winner", "team"], rows) == []


@pytest.mark.unit
def test_numeric_and_null_cells_are_not_treated_as_names():
    rows = [{"year": 2025, "note": None}, {"year": 2025, "note": None}]

    assert tally_lines(["year", "note"], rows) == []


@pytest.mark.unit
def test_the_list_is_capped_so_a_wide_result_cannot_flood_the_answer():
    columns = [f"c{i}" for i in range(12)]
    rows = [dict.fromkeys(columns, "same"), dict.fromkeys(columns, "same")]

    assert len(tally_lines(columns, rows)) == 8
