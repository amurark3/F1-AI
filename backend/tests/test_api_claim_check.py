"""Tests for app.api.claim_check — driver↔team claims checked against the rows.

The model attaches teams to drivers in prose, and got it wrong in ways the
rows contradicted: "Kimi Antonelli (Alfa Romeo)", "Mercedes drivers (Russell
three times, Norris once)", Norris's race win folded into a Mercedes total.
The checker's reference is the tables the tools returned in this conversation
— never a fixed roster — so an answer about another season is not "corrected"
against this one. Precision matters more than recall: a flag costs a repair
request and a false one invites the model to break a true sentence.
"""

from __future__ import annotations

import pytest

from app.api.claim_check import Misattribution, find_misattributions, roster_from_tables

_SESSION_TABLE = """### Sprint Race Results: Miami Grand Prix 2026
| Pos | Driver | Team | Time/Status | Pts |
| :-- | :----- | :--- | :---------- | :-- |
| 1 | Lando Norris (NOR) | McLaren | 29:15.045 | 8 |
| 2 | Andrea Kimi Antonelli (ANT) | Mercedes | 00:03.766 | 7 |
| 3 | Max Verstappen (VER) | Red Bull Racing | 00:05.100 | 6 |"""

_SQL_TABLE = """Returned 2 row(s).

| round | sprint_winner | sprint_team | race_winner | race_team |
| --- | --- | --- | --- | --- |
| 4 | Lando Norris | McLaren | Kimi Antonelli | Mercedes |
| 12 | George Russell | Mercedes | Lando Norris | McLaren |

Tallies, counted in code from the rows above (quote these; do not recount):
- race_winner: Kimi Antonelli (Mercedes) ×1; Lando Norris (McLaren) ×1"""

_TEAMS = ["Mercedes", "McLaren", "Red Bull", "Ferrari", "Alfa Romeo", "Williams"]


def _roster():
    return roster_from_tables([_SESSION_TABLE, _SQL_TABLE])


def _flags(answer: str) -> list[tuple[str, str]]:
    return [(m.driver, m.claimed_team) for m in find_misattributions(answer, _roster(), _TEAMS)]


# ---------------------------------------------------------------------------
# Reading the roster out of tool tables
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_session_table_maps_last_name_and_code_to_the_team():
    roster = roster_from_tables([_SESSION_TABLE])

    assert roster["Antonelli"] == frozenset({"Mercedes"})
    assert roster["ANT"] == frozenset({"Mercedes"})
    assert roster["Verstappen"] == frozenset({"Red Bull Racing"})


@pytest.mark.unit
def test_every_name_column_in_a_sql_table_pairs_with_the_team_column_after_it():
    roster = roster_from_tables([_SQL_TABLE])

    assert roster["Norris"] == frozenset({"McLaren"})
    assert roster["Russell"] == frozenset({"Mercedes"})
    assert roster["Antonelli"] == frozenset({"Mercedes"})


@pytest.mark.unit
def test_a_driver_seen_with_two_teams_keeps_both():
    """A mid-season switch, or two seasons in one conversation."""
    other = "| driver | team |\n| --- | --- |\n| Lando Norris | Racing Bulls |"

    assert roster_from_tables([_SQL_TABLE, other])["Norris"] == frozenset({"McLaren", "Racing Bulls"})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cell", "key"),
    [("george-russell", "Russell"), ("Carlos Sainz Jr.", "Sainz"), ("Nico Hülkenberg", "Hülkenberg")],
)
def test_slugs_and_name_suffixes_resolve_to_the_family_name(cell, key):
    table = f"| driver | team |\n| --- | --- |\n| {cell} | Williams |"

    assert roster_from_tables([table])[key] == frozenset({"Williams"})


@pytest.mark.unit
def test_tables_without_a_team_column_and_non_table_text_add_nothing():
    plain = "| round | winner |\n| --- | --- |\n| 4 | Lando Norris |\n\nLando Norris (Mercedes) said hello."

    assert roster_from_tables([plain]) == {}


@pytest.mark.unit
def test_an_empty_team_cell_is_skipped():
    table = "| driver | team |\n| --- | --- |\n| Lando Norris |  |"

    assert roster_from_tables([table]) == {}


# ---------------------------------------------------------------------------
# Finding claims that contradict it
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_team_in_brackets_after_a_driver_is_checked():
    """The original failure: a team from memory, attached to a driver the rows place elsewhere."""
    [flag] = find_misattributions("Kimi Antonelli (Alfa Romeo) won in Miami.", _roster(), _TEAMS)

    assert flag == Misattribution(
        driver="Antonelli",
        claimed_team="Alfa Romeo",
        actual_teams=("Mercedes",),
        excerpt="Kimi Antonelli (Alfa Romeo) won in Miami.",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "answer",
    [
        "Lando Norris (McLaren) took the sprint.",
        "**Max Verstappen** – Red Bull won.",  # FastF1 says "Red Bull Racing"; the short name is the same team
        "| 4 | Lando Norris | McLaren |",
        "ANT (Mercedes) converted.",
        "McLaren's Lando Norris won the sprint.",
        "Norris won the race for McLaren.",
    ],
)
def test_a_claim_the_rows_support_is_not_flagged(answer):
    assert _flags(answer) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("| 4 | Lando Norris | Mercedes |", [("Norris", "Mercedes")]),
        ("**Lando Norris** – Mercedes", [("Norris", "Mercedes")]),
        ("NOR (Mercedes) won.", [("NOR", "Mercedes")]),
        ("Mercedes' Lando Norris won.", [("Norris", "Mercedes")]),
        ("Norris won the race for Mercedes.", [("Norris", "Mercedes")]),
    ],
)
def test_a_claim_the_rows_contradict_is_flagged(answer, expected):
    assert _flags(answer) == expected


@pytest.mark.unit
def test_drivers_listed_under_a_team_are_each_checked():
    """Verbatim from production: the count was right, the membership was not."""
    answer = "Four of six sprint wins went to Mercedes drivers (Russell three times, Norris once)."

    assert _flags(answer) == [("Norris", "Mercedes")]


@pytest.mark.unit
def test_another_driver_between_the_name_and_for_team_breaks_the_claim():
    """Here "for Mercedes" belongs to Russell, not to Norris."""
    assert _flags("Norris finished ahead of Russell for Mercedes' benefit.") == []


@pytest.mark.unit
def test_a_comma_after_the_name_does_not_make_a_claim():
    """ "Norris, Mercedes and Ferrari all scored" is a list, not an attribution."""
    assert _flags("Norris, Mercedes and Ferrari all scored points.") == []


@pytest.mark.unit
def test_a_driver_absent_from_the_rows_is_never_flagged():
    """An answer about another season must not be "corrected" against this one."""
    assert _flags("Lewis Hamilton (Mercedes) won seven titles.") == []


@pytest.mark.unit
def test_the_same_wrong_claim_is_reported_once():
    answer = "Lando Norris (Mercedes) won. Later, Lando Norris (Mercedes) won again."

    assert _flags(answer) == [("Norris", "Mercedes")]


@pytest.mark.unit
def test_the_excerpt_is_the_sentence_holding_the_claim():
    answer = "Russell won in China. Then Lando Norris (Mercedes) won in Miami. Antonelli won Canada."

    [flag] = find_misattributions(answer, _roster(), _TEAMS)

    assert flag.excerpt == "Then Lando Norris (Mercedes) won in Miami."


@pytest.mark.unit
def test_with_no_roster_nothing_is_checked():
    assert find_misattributions("Lando Norris (Mercedes) won.", {}, _TEAMS) == []


@pytest.mark.unit
def test_a_driver_code_is_never_read_as_a_team():
    """Verbatim from the eval: f1db's constructors include LEC (a 1977 team), which
    is also Leclerc's code — so "Charles Leclerc (LEC) | Ferrari" read as a claim."""
    roster = roster_from_tables(["| Driver | Team |\n| --- | --- |\n| Charles Leclerc (LEC) | Ferrari |"])

    assert (
        find_misattributions("| 3 | Charles Leclerc (LEC) | Ferrari | +00:16.871 |", roster, ["LEC", "Ferrari"]) == []
    )


@pytest.mark.unit
def test_a_code_after_the_name_does_not_hide_the_team_that_follows():
    """The model copies the tools' "Name (CODE) | Team" cells into its own tables."""
    assert _flags("| 1 | Lando Norris (NOR) | Mercedes | 29:15.045 |") == [("Norris", "Mercedes")]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("claimed", "actual", "same"),
    [
        ("RB F1 Team", "Racing Bulls", True),  # FastF1's name for the team f1db calls Racing Bulls
        ("RB", "Racing Bulls", True),
        ("Red Bull", "Red Bull Racing", True),
        ("Haas F1 Team", "Haas", True),
        ("Red Bull", "Racing Bulls", False),  # sister teams, not the same one
        ("Mercedes", "McLaren", False),
    ],
)
def test_team_names_from_different_sources_are_matched_without_merging_rivals(claimed, actual, same):
    roster = roster_from_tables([f"| Driver | Team |\n| --- | --- |\n| Liam Lawson (LAW) | {actual} |"])

    flagged = find_misattributions(f"Liam Lawson ({claimed}) scored.", roster, [claimed])

    assert (flagged == []) is same
