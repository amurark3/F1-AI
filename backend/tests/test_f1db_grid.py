"""Tests for the published starting grid reader (app.data.f1db_grid).

The behaviour under test: the grid is read as the grid, not as the qualifying
order. Every case here is one where the two disagree — a places penalty, a
start-from-the-back sanction, a pit-lane release — because those are exactly
the weekends on which showing the qualifying classification as "the grid" puts
the wrong driver in the wrong box.
"""

import sqlite3

import pytest

from app.data import f1db_grid
from app.data.f1db_grid import starting_grid

SCHEMA = """
CREATE TABLE race (id INTEGER PRIMARY KEY, year INTEGER, round INTEGER);
CREATE TABLE driver (id TEXT PRIMARY KEY, name TEXT, abbreviation TEXT);
CREATE TABLE constructor (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE race_data (
    race_id INTEGER,
    type TEXT,
    position_display_order INTEGER,
    position_number INTEGER,
    position_text TEXT,
    driver_id TEXT,
    constructor_id TEXT,
    starting_grid_position_qualification_position_number INTEGER,
    starting_grid_position_grid_penalty TEXT,
    starting_grid_position_grid_penalty_positions INTEGER
);
"""

DRIVERS = [
    ("gasly", "Pierre Gasly", "GAS", "alpine", "Alpine"),
    ("piastri", "Oscar Piastri", "PIA", "mclaren", "McLaren"),
    ("antonelli", "Kimi Antonelli", "ANT", "mercedes", "Mercedes"),
    ("lawson", "Liam Lawson", "LAW", "red-bull", "Red Bull"),
]


@pytest.fixture
def grid_db(monkeypatch):
    """An in-memory f1db shaped like the real one, with a seeded round 13."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO race VALUES (1, 2026, 13)")
    for driver_id, name, code, team_id, team in DRIVERS:
        conn.execute("INSERT INTO driver VALUES (?, ?, ?)", (driver_id, name, code))
        conn.execute("INSERT OR IGNORE INTO constructor VALUES (?, ?)", (team_id, team))

    def add(order, position, position_text, driver_id, qualifying, penalty, penalty_positions):
        team_id = next(row[3] for row in DRIVERS if row[0] == driver_id)
        conn.execute(
            "INSERT INTO race_data VALUES (1, 'STARTING_GRID_POSITION', ?, ?, ?, ?, ?, ?, ?, ?)",
            (order, position, position_text, driver_id, team_id, qualifying, penalty, penalty_positions),
        )

    # Pole with no sanction, a three-place drop, a back-of-grid sanction, and a
    # pit-lane release with no grid slot at all.
    add(1, 1, "1", "gasly", 1, None, None)
    add(6, 6, "6", "piastri", 3, "3", 3)
    add(19, 19, "19", "antonelli", 7, "SFB", None)
    add(22, None, "PL", "lawson", 14, "35", 35)
    conn.commit()

    # ``connect()`` is used as a context manager, which on a sqlite3 connection
    # commits or rolls back but does not close — so one connection serves every
    # call in a test without the in-memory database vanishing between them.
    monkeypatch.setattr(f1db_grid, "connect", lambda: conn)
    yield conn
    conn.close()


def by_code(slots):
    return {slot.driver_code: slot for slot in slots}


def test_reads_the_grid_in_starting_order(grid_db):
    assert [slot.driver_code for slot in starting_grid(2026, 13)] == ["GAS", "PIA", "ANT", "LAW"]


def test_unpenalised_driver_starts_where_they_qualified(grid_db):
    pole = by_code(starting_grid(2026, 13))["GAS"]

    assert (pole.position, pole.qualifying_position) == (1, 1)
    assert pole.penalised is False
    assert pole.places_lost == 0


def test_places_penalty_moves_the_driver_off_their_qualifying_slot(grid_db):
    piastri = by_code(starting_grid(2026, 13))["PIA"]

    assert (piastri.qualifying_position, piastri.position) == (3, 6)
    assert piastri.penalty_positions == 3
    assert piastri.penalised is True
    assert piastri.places_lost == 3


def test_start_from_back_is_flagged_without_a_place_count(grid_db):
    antonelli = by_code(starting_grid(2026, 13))["ANT"]

    assert antonelli.start_from_back is True
    assert antonelli.penalty_positions is None
    assert antonelli.penalised is True
    # Derived from the published positions, not from the absent place count.
    assert antonelli.places_lost == 12


def test_pit_lane_start_holds_no_grid_slot(grid_db):
    lawson = by_code(starting_grid(2026, 13))["LAW"]

    assert lawson.pit_lane is True
    assert lawson.position is None
    assert lawson.penalised is True
    # No slot means no slot delta — not a zero, which would read as "held position".
    assert lawson.places_lost is None


def test_missing_qualifying_position_yields_no_delta(grid_db):
    grid_db.execute(
        "UPDATE race_data SET starting_grid_position_qualification_position_number = NULL "
        "WHERE driver_id = 'gasly'"
    )

    assert by_code(starting_grid(2026, 13))["GAS"].places_lost is None


def test_rows_without_a_driver_code_are_dropped(grid_db):
    grid_db.execute("UPDATE driver SET abbreviation = '' WHERE id = 'gasly'")

    assert "GAS" not in by_code(starting_grid(2026, 13))


def test_round_with_no_published_grid_returns_nothing(grid_db):
    # The normal state for a weekend f1db has not released yet — not an error.
    assert starting_grid(2026, 14) == ()


def test_sprint_grid_is_read_through_the_same_reader(grid_db):
    """A sprint publishes its own grid sheet, in the same column family.

    Reading it through a second implementation would mean sprint grid
    penalties were surfaced by different code — and drift from it.
    """
    grid_db.execute(
        "INSERT INTO race_data VALUES (1, 'SPRINT_STARTING_GRID_POSITION', 1, 6, '6', "
        "'piastri', 'mclaren', 3, '3', 3)"
    )

    sprint = starting_grid(2026, 13, f1db_grid.TYPE_SPRINT_GRID)

    assert [slot.driver_code for slot in sprint] == ["PIA"]
    assert sprint[0].places_lost == 3
    # The Grand Prix grid is untouched by the sprint's sheet.
    assert len(starting_grid(2026, 13)) == 4


def test_a_weekend_without_a_sprint_has_no_sprint_grid(grid_db):
    assert starting_grid(2026, 13, f1db_grid.TYPE_SPRINT_GRID) == ()
