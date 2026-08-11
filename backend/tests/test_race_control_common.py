"""Tests for app.services.race_control_common — the shared data layer.

Every Race Control screen is assembled from this module: standings snapshots,
driver lookup, and the "how far into the season are we?" counters that the
championship forecast divides by. Three risks are worth guarding.

* **Coercion silently inventing values.** ``safe_*`` and ``first_value`` turn
  NaN-riddled Ergast frames into strings and numbers. A wrong default here does
  not crash — it shows a confident ``0`` where the truth is "unknown".
* **The f1db-vs-Ergast fallback.** f1db is preferred because it is local and
  rate-limit free; Ergast is only reached when the season is not in the local
  dataset. Tests cover both sides and the failure of each.
* **Season counters.** ``completed_race_count`` gates the points-per-race maths
  on the battle and teams screens; counting an unrun race would inflate every
  rate on those screens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.services import race_control_common as module

_NOW = datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _StandingsResponse:
    """Stand-in for the object ``Ergast.get_*_standings`` returns."""

    def __init__(self, content: list):
        self.content = content


def _stub_ergast(monkeypatch: pytest.MonkeyPatch, **feeds) -> None:
    """Swap the Ergast client for one serving fixed frames or raising.

    ``feeds`` accepts ``drivers=`` / ``constructors=``; each value is either a
    list of DataFrames (the real ``.content`` shape) or an exception to raise.
    """

    def _serve(value):
        if isinstance(value, BaseException):
            raise value
        return _StandingsResponse(list(value or []))

    class _Client:
        def get_driver_standings(self, season):
            return _serve(feeds.get("drivers"))

        def get_constructor_standings(self, season):
            return _serve(feeds.get("constructors"))

    monkeypatch.setattr(module, "Ergast", _Client)


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
    ("row", "expected"),
    [
        ({"familyName": "Verstappen"}, "Verstappen"),
        ({"familyName": None}, ""),
        ({"familyName": float("nan")}, ""),
        ({}, ""),
        ({"familyName": 12}, "12"),
    ],
    ids=["present", "null", "nan", "absent", "non-string"],
)
def test_safe_str_blanks_missing_cells_rather_than_printing_none(row, expected):
    assert module.safe_str(row, "familyName") == expected


@pytest.mark.unit
def test_safe_str_uses_the_default_for_an_absent_key():
    assert module.safe_str({}, "constructorName", "Unknown") == "Unknown"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (float("nan"), ""),
        (["Red Bull", "RB"], "Red Bull"),
        (("Ferrari",), "Ferrari"),
        ([], ""),
        ("McLaren", "McLaren"),
    ],
    ids=["null", "nan", "list-takes-first", "tuple", "empty-list", "scalar"],
)
def test_first_value_unwraps_ergast_list_cells(value, expected):
    """Ergast returns constructor cells as lists for drivers who changed team."""
    assert module.first_value(value) == expected


@pytest.mark.unit
def test_first_value_uses_the_default_when_the_list_is_empty():
    assert module.first_value([], "Unknown") == "Unknown"


# ---------------------------------------------------------------------------
# row readers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_constructor_name_prefers_the_singular_column_when_present():
    row = {"constructorName": "Ferrari", "constructorNames": ["McLaren"]}

    assert module.constructor_name_from_row(row) == "Ferrari"


@pytest.mark.unit
def test_constructor_name_falls_back_to_the_plural_column():
    assert module.constructor_name_from_row({"constructorNames": ["McLaren", "Alpine"]}) == "McLaren"


@pytest.mark.unit
def test_constructor_name_defaults_when_neither_column_exists():
    assert module.constructor_name_from_row({}) == "Unknown"
    assert module.constructor_name_from_row({}, "No team") == "No team"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"givenName": "Max", "familyName": "Verstappen"}, "Max Verstappen"),
        ({"familyName": "Verstappen"}, "Verstappen"),
        ({}, ""),
    ],
    ids=["full", "surname-only", "empty"],
)
def test_driver_full_name_never_leaves_stray_whitespace(row, expected):
    assert module.driver_full_name(row) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"driverCode": "ver"}, "VER"),
        ({"driverCode": " lec "}, "LEC"),
        ({"familyName": "Hamilton"}, "HAM"),
        ({"familyName": "Ho", "driverId": "kevin_ho"}, "KEV"),
        ({"driverId": "de_vries"}, "DEV"),
        ({}, "TBC"),
    ],
    ids=["code", "padded-code", "from-surname", "surname-too-short", "from-driver-id", "nothing-known"],
)
def test_driver_code_falls_back_through_surname_then_id(row, expected):
    """A driver with no three-letter code still needs a stable board label."""
    assert module.driver_code_from_row(row) == expected


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
# get_standings_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_standings_snapshot_reads_the_local_f1db_dataset_first(fake_f1db, monkeypatch):
    """f1db has no rate limit, so Ergast must not be touched when it has the season."""
    _stub_ergast(monkeypatch, drivers=RuntimeError("Ergast must not be called"))

    drivers, constructors = module.get_standings_snapshot(2026)

    assert [row["code"] for row in drivers] == ["VER", "LEC"]
    # The snapshot re-keys the f1db row (``name`` -> ``driver``) and drops the
    # detail columns the command center does not render; the team string itself
    # is whatever f1db resolved for a driver who switched teams mid-season.
    assert set(drivers[0]) == {"position", "code", "driver", "team", "points", "wins"}
    assert (drivers[0]["position"], drivers[0]["driver"], drivers[0]["points"], drivers[0]["wins"]) == (
        1,
        "Verstappen",
        50.0,
        2,
    )
    assert [(row["team"], row["points"]) for row in constructors] == [("Red Bull", 50.0), ("Ferrari", 44.0)]


@pytest.mark.unit
def test_standings_snapshot_falls_back_to_ergast_when_f1db_lacks_the_season(monkeypatch):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    monkeypatch.setattr(module, "constructor_standings_detailed", lambda _year: [])
    _stub_ergast(
        monkeypatch,
        drivers=[
            pd.DataFrame(
                [
                    {
                        "position": 1,
                        "driverCode": "VER",
                        "givenName": "Max",
                        "familyName": "Verstappen",
                        "constructorNames": ["Red Bull"],
                        "points": 310.0,
                        "wins": 9,
                    }
                ]
            )
        ],
        constructors=[pd.DataFrame([{"position": 1, "constructorName": "Red Bull", "points": 500.0, "wins": 9}])],
    )

    drivers, constructors = module.get_standings_snapshot(2019)

    assert drivers == [
        {"position": 1, "code": "VER", "driver": "Max Verstappen", "team": "Red Bull", "points": 310.0, "wins": 9}
    ]
    assert constructors == [{"position": 1, "team": "Red Bull", "points": 500.0, "wins": 9}]


@pytest.mark.unit
def test_standings_snapshot_numbers_rows_by_order_when_ergast_omits_position(monkeypatch):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    monkeypatch.setattr(module, "constructor_standings_detailed", lambda _year: [])
    _stub_ergast(
        monkeypatch,
        drivers=[pd.DataFrame([{"driverCode": "VER"}, {"driverCode": "LEC"}])],
        constructors=[pd.DataFrame([{"constructorName": "Red Bull"}, {"constructorName": "Ferrari"}])],
    )

    drivers, constructors = module.get_standings_snapshot(2019)

    assert [row["position"] for row in drivers] == [1, 2]
    assert [row["position"] for row in constructors] == [1, 2]
    assert [row["points"] for row in constructors] == [0.0, 0.0]


@pytest.mark.unit
def test_standings_snapshot_returns_empty_sides_when_ergast_has_no_content(monkeypatch):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    monkeypatch.setattr(module, "constructor_standings_detailed", lambda _year: [])
    _stub_ergast(monkeypatch)

    assert module.get_standings_snapshot(1962) == ([], [])


@pytest.mark.unit
def test_standings_snapshot_degrades_each_side_independently_when_ergast_fails(monkeypatch, capsys):
    """A dead driver feed must not blank the constructor table as well."""
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    monkeypatch.setattr(module, "constructor_standings_detailed", lambda _year: [])
    _stub_ergast(
        monkeypatch,
        drivers=ConnectionError("ergast down"),
        constructors=[pd.DataFrame([{"constructorName": "Ferrari", "points": 100.0, "wins": 2}])],
    )

    drivers, constructors = module.get_standings_snapshot(2019)

    assert drivers == []
    assert [row["team"] for row in constructors] == ["Ferrari"]
    assert "race_control.driver_snapshot.failed" in capsys.readouterr().out


@pytest.mark.unit
def test_standings_snapshot_logs_a_failing_constructor_feed(monkeypatch, capsys):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    monkeypatch.setattr(module, "constructor_standings_detailed", lambda _year: [])
    _stub_ergast(monkeypatch, constructors=ConnectionError("ergast down"))

    assert module.get_standings_snapshot(2019) == ([], [])
    assert "race_control.constructor_snapshot.failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# load_driver_standings
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_load_driver_standings_returns_the_detailed_f1db_rows(fake_f1db):
    standings = module.load_driver_standings(2026)

    assert [row["code"] for row in standings] == ["VER", "LEC"]
    assert standings[0]["driver_id"] == "max-verstappen"


@pytest.mark.unit
def test_load_driver_standings_maps_the_ergast_frame_when_f1db_is_empty(monkeypatch):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    _stub_ergast(
        monkeypatch,
        drivers=[
            pd.DataFrame(
                [
                    {
                        "position": 2,
                        "driverCode": "LEC",
                        "givenName": "Charles",
                        "familyName": "Leclerc",
                        "constructorNames": ["Ferrari"],
                        "points": 200.0,
                        "wins": 1,
                        "driverNationality": "Monegasque",
                        "driverId": "leclerc",
                    }
                ]
            )
        ],
    )

    assert module.load_driver_standings(2019) == [
        {
            "code": "LEC",
            "name": "Charles Leclerc",
            "team": "Ferrari",
            "position": 2,
            "points": 200.0,
            "wins": 1,
            "nationality": "Monegasque",
            "driver_id": "leclerc",
        }
    ]


@pytest.mark.unit
def test_load_driver_standings_is_empty_when_ergast_has_no_content(monkeypatch):
    monkeypatch.setattr(module, "driver_standings_detailed", lambda _year: [])
    _stub_ergast(monkeypatch)

    assert module.load_driver_standings(1962) == []


# ---------------------------------------------------------------------------
# get_driver_options
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_driver_options_reports_the_source_and_no_error_when_populated(monkeypatch):
    monkeypatch.setattr(module, "load_driver_standings", lambda _year: [{"code": "VER"}])

    options = module.get_driver_options(2026)

    assert options["source"] == "f1db-driver-standings"
    assert options["drivers"] == [{"code": "VER"}]
    assert options["error"] is None


@pytest.mark.unit
def test_driver_options_explains_an_empty_season_rather_than_returning_a_bare_list(monkeypatch):
    monkeypatch.setattr(module, "load_driver_standings", lambda _year: [])

    options = module.get_driver_options(2030)

    assert options["drivers"] == []
    assert options["error"] == "No driver standings found for this season yet."


@pytest.mark.unit
def test_driver_options_swallows_a_feed_failure_into_an_error_payload(monkeypatch, capsys):
    def _boom(_year):
        raise ConnectionError("standings feed down")

    monkeypatch.setattr(module, "load_driver_standings", _boom)

    options = module.get_driver_options(2026)

    assert options["drivers"] == []
    assert options["error"] == "Driver standings are unavailable right now."
    assert "race_control.driver_options.failed" in capsys.readouterr().out
    # The upstream exception text must not reach the client payload.
    assert "standings feed down" not in options["error"]


# ---------------------------------------------------------------------------
# find_driver
# ---------------------------------------------------------------------------


_ROSTER = [
    {"code": "VER", "name": "Max Verstappen", "driver_id": "max_verstappen"},
    {"code": "LEC", "name": "Charles Leclerc", "driver_id": "leclerc"},
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
    ids=["code", "lowercase-code", "driver-id", "full-name", "id-and-surname", "surname-substring", "given-name"],
)
def test_find_driver_accepts_codes_ids_and_partial_names(query, expected_code):
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
        {"code": "PER", "name": "Sergio Perez", "driver_id": "perez"},
        {"code": "LEC", "name": "Charles Leclerc", "driver_id": "leclerc"},
    ]

    assert module.find_driver(roster, "LEC")["code"] == "LEC"


# ---------------------------------------------------------------------------
# completed_race_count / completed_race_rounds
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_completed_race_count_only_counts_races_finished_more_than_three_hours_ago(monkeypatch):
    """The +3h buffer is race duration: a race that started 1h ago is not done."""
    monkeypatch.setattr(
        module.fastf1,
        "get_event_schedule",
        lambda **_kwargs: _schedule(
            [
                _race_row(1, _NOW - timedelta(days=7)),
                _race_row(2, _NOW - timedelta(hours=1)),
                _race_row(3, _NOW + timedelta(days=7)),
            ]
        ),
    )

    assert module.completed_race_count(2026) == 1


@pytest.mark.unit
def test_completed_race_count_ignores_rows_with_no_dated_race_session(monkeypatch):
    monkeypatch.setattr(
        module.fastf1,
        "get_event_schedule",
        lambda **_kwargs: _schedule(
            [
                {"RoundNumber": 1, "Session5": "Race", "Session5DateUtc": pd.NaT},
                {"RoundNumber": 2, "Session5": "Sprint", "Session5DateUtc": pd.Timestamp(_NOW - timedelta(days=3))},
            ]
        ),
    )

    assert module.completed_race_count(2026) == 0


@pytest.mark.unit
def test_completed_race_count_is_none_when_the_calendar_cannot_be_loaded(monkeypatch, capsys):
    """``None`` means "unknown", which callers must not confuse with zero races run."""

    def _boom(**_kwargs):
        raise ConnectionError("schedule unreachable")

    monkeypatch.setattr(module.fastf1, "get_event_schedule", _boom)

    assert module.completed_race_count(2026) is None
    assert "race_control.completed_races.failed" in capsys.readouterr().out


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
