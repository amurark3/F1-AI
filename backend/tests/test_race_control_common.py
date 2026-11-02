"""Tests for app.services.race_control_common — the shared data layer.

Every Race Control screen is assembled from this module: the drivers list,
driver lookup, and the "how far into the season are we?" counters that the
championship forecast divides by. Three risks are worth guarding.

* **Coercion silently inventing values.** ``safe_*`` turn NaN-riddled frames
  into numbers. A wrong default here does not crash — it shows a confident
  ``0`` where the truth is "unknown".
* **The drivers list reads the computed table.** ``get_driver_options`` serves
  ``current_standings`` (f1db's last round plus later rounds' OpenF1 points),
  with its freshness, and turns a failure into an error payload.
* **Season counters.** ``completed_race_rounds`` gates the forecast maths;
  counting an unrun race would inflate every rate on that screen.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.services import race_control_common as module
from tests.standings_support import f1db_only, standings_from_rows

_NOW = datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _schedule(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _race_row(round_number: int, when: datetime) -> dict:
    """One schedule row whose fifth session is the Grand Prix itself."""
    return {"RoundNumber": round_number, "Session5": "Race", "Session5DateUtc": pd.Timestamp(when)}


# ---------------------------------------------------------------------------
# scalar coercion
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), (float("nan"), 0), (3, 3), (3.9, 3), ("7", 7), (True, 1)],
    ids=["none", "nan", "int", "truncated-float", "numeric-string", "bool"],
)
def test_safe_int_falls_back_only_for_missing_values(value, expected):
    assert module.safe_int(value) == expected


@pytest.mark.unit
def test_safe_int_returns_the_supplied_default_including_none():
    """Callers pass ``default=None`` to mean "unclassified", not "position 0"."""
    assert module.safe_int(None, None) is None
    assert module.safe_int(float("nan"), None) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0.0), (float("nan"), 0.0), (18, 18.0), ("2.5", 2.5)],
    ids=["none", "nan", "int", "numeric-string"],
)
def test_safe_float_falls_back_only_for_missing_values(value, expected):
    assert module.safe_float(value) == expected


@pytest.mark.unit
def test_safe_float_honours_a_custom_default():
    assert module.safe_float(None, -1.0) == -1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [("Max Verstappen", "MAXVERSTAPPEN"), ("max_verstappen", "MAXVERSTAPPEN"), ("VER", "VER"), ("", "")],
    ids=["spaced", "underscored-id", "code", "empty"],
)
def test_normalise_driver_lookup_strips_everything_but_alphanumerics(value, expected):
    assert module.normalise_driver_lookup(value) == expected


# ---------------------------------------------------------------------------
# team identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Red Bull Racing", "red-bull"),
        ("Haas F1 Team", "haas"),
        ("Alpine Team", "alpine"),
        ("Aston Martin", "aston-martin"),
    ],
    ids=["racing-suffix", "f1-team-suffix", "team-suffix", "no-suffix"],
)
def test_team_slug_strips_the_sponsor_suffixes_f1_entry_names_carry(name, expected):
    assert module.team_slug(name) == expected


@pytest.mark.unit
def test_team_color_returns_the_liveried_colour_for_a_known_entrant():
    assert module.team_color("Red Bull Racing") == module.TEAM_COLORS["red-bull"]
    assert module.team_color("Ferrari") == module.TEAM_COLORS["ferrari"]


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Racing Bulls", "RB"])
def test_team_color_gives_racing_bulls_its_livery_under_both_names(name):
    """Racing Bulls used to fall through to grey: its slug was missing."""
    assert module.team_color(name) == "#6692FF"


@pytest.mark.unit
def test_team_color_returns_a_neutral_grey_for_an_unmapped_entrant():
    """A new entrant must render neutral rather than borrow another team's colour."""
    colour = module.team_color("Brawn GP")

    assert colour == "#6B7280"
    assert colour not in module.TEAM_COLORS.values()


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(25.0, "25"), (25.5, "25.5"), (0.0, "0"), (-3.0, "-3")],
    ids=["whole", "half-point", "zero", "negative"],
)
def test_format_points_value_drops_the_trailing_zero_on_whole_points(value, expected):
    assert module.format_points_value(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "singular", "plural", "expected"),
    [
        (1, "win", None, "1 win"),
        (0, "win", None, "0 wins"),
        (3, "win", None, "3 wins"),
        (2, "podium", "podia", "2 podia"),
    ],
    ids=["one", "zero", "many", "irregular-plural"],
)
def test_pluralise_matches_the_noun_to_the_count(value, singular, plural, expected):
    assert module.pluralise(value, singular, plural) == expected


# ---------------------------------------------------------------------------
# get_driver_options
# ---------------------------------------------------------------------------

AFTER_ROUND_18 = {"as_of_round": 18, "provisional": False, "sources": [{"source": "f1db", "role": "base"}]}


def _serve_table(monkeypatch: pytest.MonkeyPatch, drivers: list[dict]) -> None:
    standings = standings_from_rows(
        drivers, [], as_of_round=AFTER_ROUND_18["as_of_round"], sources=tuple(AFTER_ROUND_18["sources"])
    )
    monkeypatch.setattr(module, "current_standings", lambda _year: standings)


@pytest.mark.integration
def test_driver_options_read_f1db_through_the_computed_table(fake_f1db, monkeypatch):
    f1db_only(monkeypatch)

    options = module.get_driver_options(2026)

    assert [(row["code"], row["name"], row["position"]) for row in options["drivers"]] == [
        ("VER", "Verstappen", 1),
        ("LEC", "Leclerc", 2),
    ]
    assert (options["as_of_round"], options["provisional"]) == (2, False)


@pytest.mark.unit
def test_driver_options_carry_the_rows_the_hub_reads_and_the_tables_freshness(monkeypatch):
    _serve_table(
        monkeypatch,
        [{"position": 1, "code": "VER", "driver": "Max Verstappen", "team": "Red Bull", "points": 77.5, "wins": 2}],
    )

    options = module.get_driver_options(2026)

    assert options["source"] == "computed-standings"
    assert options["drivers"] == [
        {"code": "VER", "name": "Max Verstappen", "team": "Red Bull", "position": 1, "points": 77.5, "wins": 2}
    ]
    assert {key: options[key] for key in AFTER_ROUND_18} == AFTER_ROUND_18
    assert options["error"] is None


@pytest.mark.unit
def test_driver_options_explains_an_empty_season_rather_than_returning_a_bare_list(monkeypatch):
    _serve_table(monkeypatch, [])

    options = module.get_driver_options(2030)

    assert options["drivers"] == []
    assert options["error"] == "No driver standings found for this season yet."


@pytest.mark.unit
def test_driver_options_swallows_a_feed_failure_into_an_error_payload(monkeypatch, capsys):
    def _boom(_year):
        raise ConnectionError("standings feed down")

    monkeypatch.setattr(module, "current_standings", _boom)

    options = module.get_driver_options(2026)

    assert options["drivers"] == []
    assert (options["as_of_round"], options["provisional"], options["sources"]) == (None, False, [])
    assert options["error"] == "Driver standings are unavailable right now."
    assert "race_control.driver_options.failed" in capsys.readouterr().out
    # The upstream exception text must not reach the client payload.
    assert "standings feed down" not in options["error"]


# ---------------------------------------------------------------------------
# find_driver
# ---------------------------------------------------------------------------


_ROSTER = [
    {"code": "VER", "name": "Max Verstappen"},
    {"code": "LEC", "name": "Charles Leclerc"},
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("query", "expected_code"),
    [
        ("VER", "VER"),
        ("ver", "VER"),
        ("max_verstappen", "VER"),
        ("Max Verstappen", "VER"),
        ("leclerc", "LEC"),
        ("verstappen", "VER"),
        ("Charles", "LEC"),
    ],
    ids=["code", "lowercase-code", "id-shaped-name", "full-name", "surname", "surname-substring", "given-name"],
)
def test_find_driver_accepts_codes_and_full_or_partial_names(query, expected_code):
    """An f1db-style id ("max_verstappen") is the full name once normalised."""
    assert module.find_driver(_ROSTER, query)["code"] == expected_code


@pytest.mark.unit
@pytest.mark.parametrize(
    "query", ["", "   ", "!!!", "Hamilton"], ids=["blank", "whitespace", "punctuation-only", "not-in-roster"]
)
def test_find_driver_returns_none_rather_than_guessing(query):
    assert module.find_driver(_ROSTER, query) is None


@pytest.mark.unit
def test_find_driver_prefers_an_exact_code_over_an_earlier_substring_match():
    """A code query must not be hijacked by a name that happens to contain it."""
    roster = [
        {"code": "PER", "name": "Sergio Perez"},
        {"code": "LEC", "name": "Charles Leclerc"},
    ]

    assert module.find_driver(roster, "LEC")["code"] == "LEC"


# ---------------------------------------------------------------------------
# completed_race_rounds
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_completed_race_rounds_returns_the_round_numbers_and_the_full_calendar_size(monkeypatch):
    monkeypatch.setattr(
        module.fastf1,
        "get_event_schedule",
        lambda **_kwargs: _schedule(
            [
                _race_row(1, _NOW - timedelta(days=30)),
                _race_row(2, _NOW - timedelta(days=10)),
                _race_row(3, _NOW + timedelta(days=10)),
            ]
        ),
    )

    assert module.completed_race_rounds(2026) == ([1, 2], 3)


@pytest.mark.unit
def test_completed_race_rounds_degrades_to_an_empty_season_when_the_calendar_fails(monkeypatch, capsys):
    def _boom(**_kwargs):
        raise ConnectionError("schedule unreachable")

    monkeypatch.setattr(module.fastf1, "get_event_schedule", _boom)

    assert module.completed_race_rounds(2026) == ([], 0)
    assert "race_control.completed_rounds.failed" in capsys.readouterr().out
