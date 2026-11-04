"""Tests for app.data.canonical_names — what every emit point prints for a driver or team.

The emit points read feeds that spell people their own way (FastF1's "Andrea
Kimi Antonelli", OpenF1's "Ryo HIRAKAWA") and hand pandas cells that can be
NaN. What they rely on here:

* f1db's ``driver.name`` / ``last_name`` and constructor name when the row resolves;
* NaN, numpy and float cells are keys like any other, never a ``TypeError``;
* an unresolved row keeps the feed's words, display-cased, never a guess;
* an unreadable f1db prints the feed's words and says so in the log, the way
  every emit point printed them before the resolver.

Feed spellings are the real ones: FastF1's results for 2026 (snapshot rows of the
R19/R20 predictions) and OpenF1's Mexico City entry list.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest
import structlog

from app.data import f1db_source
from app.data.canonical_names import driver_identity, feed_number, feed_text, team_display_name
from app.data.identity import CanonicalDriver

pytestmark = pytest.mark.integration

NAN = float("nan")


def _break_f1db(monkeypatch: pytest.MonkeyPatch) -> None:
    def connect() -> None:
        raise sqlite3.OperationalError("database disk image is malformed")

    monkeypatch.setattr(f1db_source, "connect", connect)


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ({"code": "ANT", "number": "12", "name": "Andrea Kimi Antonelli"}, ("Kimi Antonelli", "Antonelli")),
        ({"code": "SAI", "number": "55", "name": "Carlos Sainz"}, ("Carlos Sainz Jr.", "Sainz Jr.")),
        ({"code": "HIR", "number": 50, "name": "Ryo HIRAKAWA"}, ("Ryō Hirakawa", "Hirakawa")),
        ({"code": "HUL", "number": 27, "name": "Nico HULKENBERG"}, ("Nico Hülkenberg", "Hülkenberg")),
    ],
    ids=["fastf1-antonelli", "fastf1-sainz", "openf1-hirakawa", "openf1-hulkenberg"],
)
def test_a_feed_row_prints_f1dbs_name_and_surname(identity_f1db, keys, expected):
    driver = driver_identity(2026, **keys)

    assert (driver.name, driver.last_name) == expected
    assert driver.resolved


def test_a_nan_code_is_no_key_so_the_name_still_resolves(identity_f1db):
    """FastF1 had no abbreviation for Hirakawa at Mexico City; the R19 snapshot stored it as "NAN"."""
    driver = driver_identity(2026, code=NAN, number=NAN, name="Ryo Hirakawa")

    assert driver == CanonicalDriver(name="Ryō Hirakawa", last_name="Hirakawa", code="HIR", id="ryo-hirakawa")


@pytest.mark.parametrize("number", [50, "50", " 50 ", 50.0, np.int64(50), np.float64(50.0)])
def test_a_car_number_resolves_however_the_feed_typed_it(identity_f1db, number):
    assert driver_identity(2026, number=number).id == "ryo-hirakawa"


@pytest.mark.parametrize("value", [None, NAN, 50.5, True, "", "car 50", object()])
def test_a_cell_that_is_not_a_car_number_is_no_number(value):
    assert feed_number(value) is None


@pytest.mark.parametrize(("value", "expected"), [("HIR", "HIR"), (" HIR ", " HIR "), ("", None), ("  ", None)])
def test_text_cells_pass_through_and_blanks_are_none(value, expected):
    assert feed_text(value) == expected


@pytest.mark.parametrize("value", [None, NAN, 50, np.float64("nan")])
def test_a_cell_that_is_not_text_is_no_text(value):
    assert feed_text(value) is None


def test_an_unresolved_driver_keeps_the_feeds_words_display_cased(identity_f1db):
    """Mick Schumacher drove no 2026 session, so nothing is guessed for him."""
    driver = driver_identity(2026, code="MSC", number=47, name="Mick SCHUMACHER")

    assert driver == CanonicalDriver(name="Mick Schumacher", last_name="Schumacher", code="MSC", id=None)


def test_an_unreadable_f1db_prints_the_feeds_words_and_logs_why(monkeypatch):
    _break_f1db(monkeypatch)

    with structlog.testing.capture_logs() as logs:
        driver = driver_identity(2026, code="HIR", number=50, name="Ryo HIRAKAWA")

    assert driver == CanonicalDriver(name="Ryo Hirakawa", last_name="Hirakawa", code="HIR", id=None)
    assert [(log["event"], log["log_level"], log["year"]) for log in logs] == [
        ("canonical_names.f1db_unreadable", "warning", 2026)
    ]
    assert "malformed" in logs[0]["error"]


@pytest.mark.parametrize(
    ("feed", "expected"),
    [
        ("RB F1 Team", "Racing Bulls"),
        ("Visa Cash App RB", "Racing Bulls"),
        ("Haas F1 Team", "Haas"),
        ("Red Bull Racing", "Red Bull"),
        ("Alpine F1 Team", "Alpine"),
        ("Cadillac F1 Team", "Cadillac"),
        ("Racing Bulls", "Racing Bulls"),
    ],
)
def test_a_feeds_team_spelling_prints_f1dbs_team_name(identity_f1db, feed, expected):
    assert team_display_name(2026, feed) == expected


def test_a_team_not_on_the_seasons_grid_keeps_the_feeds_spelling(identity_f1db):
    """Sauber raced as Audi in 2026; its old name names no 2026 team."""
    assert team_display_name(2026, "Sauber") == "Sauber"


@pytest.mark.parametrize("value", [None, NAN, "", "   "])
def test_a_blank_team_is_blank_without_reading_f1db(monkeypatch, value):
    _break_f1db(monkeypatch)

    with structlog.testing.capture_logs() as logs:
        assert team_display_name(2026, value) == ""
    assert logs == []


def test_an_unreadable_f1db_keeps_the_feeds_team_spelling_and_logs_why(monkeypatch):
    _break_f1db(monkeypatch)

    with structlog.testing.capture_logs() as logs:
        assert team_display_name(2026, "RB F1 Team") == "RB F1 Team"

    assert [(log["event"], log["team"]) for log in logs] == [("canonical_names.f1db_unreadable", "RB F1 Team")]
