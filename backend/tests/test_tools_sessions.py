"""Tests for app.api.tools.sessions — sprint, shootout and qualifying tables.

Three tools that all read a FastF1 session and differ only in which session and
which columns. The risks are session-shaped rather than formatting-shaped:

* **The right session is requested.** Asking FastF1 for ``"Q"`` when the user
  said "shootout" returns a real, wrong table that nothing downstream flags.
* **A driver who set no time is not given one.** FastF1 leaves ``NaT`` in the
  segment columns for drivers who did not run, and a row rendered anyway would
  put an invented lap time in front of the model.
* **A non-sprint weekend degrades to a message.** ``get_session(..., "SQ")``
  raises for most weekends, and the tool has to say so rather than propagate.

FastF1 is mocked at the ``get_session`` boundary; the results are real pandas
frames so the sorting and NaN handling under test are the real ones.
"""

from __future__ import annotations

import fastf1
import pandas as pd
import pytest

from app.api.tools.sessions import (
    get_qualifying_results,
    get_sprint_qualifying_results,
    get_sprint_results,
)


class _FakeSession:
    """A loaded FastF1 session; only ``results`` is read by these tools."""

    def __init__(self, results: pd.DataFrame):
        self.results = results
        self.load_kwargs: dict | None = None

    def load(self, **kwargs):
        self.load_kwargs = kwargs


def _install_session(monkeypatch, session) -> list[tuple]:
    """Patch ``fastf1.get_session``; a session that is an exception is raised."""
    calls: list[tuple] = []

    def _get_session(year, grand_prix, identifier):
        calls.append((year, grand_prix, identifier))
        if isinstance(session, Exception):
            raise session
        return session

    monkeypatch.setattr(fastf1, "get_session", _get_session)
    return calls


def _lap(text: str) -> pd.Timedelta:
    return pd.Timedelta(f"0 days 00:0{text}")


# ---------------------------------------------------------------------------
# get_sprint_results
# ---------------------------------------------------------------------------


def _sprint_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Position": 1.0, "Abbreviation": "LEC", "Status": "Finished", "Time": _lap("0:30.000")},
            {"Position": 2.0, "Abbreviation": "VER", "Status": "Finished", "Time": _lap("0:32.418")},
            # Disqualified drivers keep a classified time FastF1 still reports.
            {"Position": 3.0, "Abbreviation": "NOR", "Status": "Disqualified", "Time": _lap("0:35.000")},
            {"Position": 4.0, "Abbreviation": "HAM", "Status": "Accident", "Time": pd.NaT},
        ]
    )


@pytest.mark.unit
def test_the_sprint_tool_asks_fastf1_for_the_saturday_race(monkeypatch):
    """ "S" is what separates this from get_race_results on a sprint weekend."""
    calls = _install_session(monkeypatch, _FakeSession(_sprint_results()))

    get_sprint_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert calls == [(2026, "Bahrain", "S")]


@pytest.mark.unit
def test_a_sprint_classification_renders_positions_drivers_and_times(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_sprint_results()))

    table = get_sprint_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert table.splitlines() == [
        "### Sprint Race Results: Bahrain 2026",
        # Only the leading hour group is stripped, so the minutes field remains.
        "| 1 | LEC | 00:30 |",
        "| 2 | VER | 00:32.418 |",
        "| 3 | NOR | DSQ |",
        "| 4 | HAM | Accident |",
    ]


@pytest.mark.unit
def test_a_disqualification_overrides_the_recorded_time(monkeypatch):
    """A DSQ shown as a finishing time would read as a valid classification."""
    results = pd.DataFrame(
        [{"Position": 1.0, "Abbreviation": "VER", "Status": "DSQ - track limits", "Time": _lap("0:30.000")}]
    )
    _install_session(monkeypatch, _FakeSession(results))

    assert "| 1 | VER | DSQ |" in get_sprint_results.invoke({"year": 2026, "grand_prix": "Bahrain"})


@pytest.mark.unit
def test_a_sprint_lookup_failure_is_reported_rather_than_raised(monkeypatch):
    _install_session(monkeypatch, ValueError("no sprint session for this event"))

    assert get_sprint_results.invoke({"year": 2026, "grand_prix": "Monaco"}) == (
        "Could not fetch Sprint results: no sprint session for this event"
    )


@pytest.mark.unit
def test_the_sprint_load_skips_telemetry_and_weather(monkeypatch):
    """A results table needs neither, and both are slow multi-megabyte fetches."""
    session = _FakeSession(_sprint_results())
    _install_session(monkeypatch, session)

    get_sprint_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert session.load_kwargs == {"telemetry": False, "laps": False, "weather": False}


# ---------------------------------------------------------------------------
# get_sprint_qualifying_results
# ---------------------------------------------------------------------------


def _shootout_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Position": 1.0,
                "Abbreviation": "VER",
                "Q1": _lap("1:29.100"),
                "Q2": _lap("1:28.500"),
                "Q3": _lap("1:27.900"),
                "Time": pd.NaT,
            },
            {
                "Position": 2.0,
                "Abbreviation": "NOR",
                "Q1": _lap("1:29.400"),
                "Q2": _lap("1:28.800"),
                "Q3": pd.NaT,
                "Time": pd.NaT,
            },
            {
                "Position": 3.0,
                "Abbreviation": "LEC",
                "Q1": _lap("1:29.600"),
                "Q2": pd.NaT,
                "Q3": pd.NaT,
                "Time": pd.NaT,
            },
            # Did not run: every segment empty.
            {"Position": 4.0, "Abbreviation": "HAM", "Q1": pd.NaT, "Q2": pd.NaT, "Q3": pd.NaT, "Time": pd.NaT},
        ]
    )


@pytest.mark.unit
def test_the_shootout_tool_asks_fastf1_for_the_sq_session(monkeypatch):
    calls = _install_session(monkeypatch, _FakeSession(_shootout_results()))

    get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert calls == [(2026, "Bahrain", "SQ")]


@pytest.mark.unit
def test_the_shootout_is_split_into_three_segment_tables(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_shootout_results()))

    tables = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert "### SQ1 Results (Bahrain 2026)" in tables
    assert "### SQ2 Results" in tables
    assert "### SQ3 Results (Sprint Pole Position)" in tables


@pytest.mark.unit
def test_each_shootout_segment_lists_only_the_drivers_who_set_a_time(monkeypatch):
    """HAM set nothing; a row for him would invent a lap that was never run."""
    _install_session(monkeypatch, _FakeSession(_shootout_results()))

    tables = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})
    sq1, sq2, sq3 = (block for block in tables.split("\n---\n") if "|" in block)

    assert [line for line in sq1.splitlines() if line.startswith("| 1")] == ["| 1 | VER | 01:29.100 |"]
    assert "HAM" not in sq1
    # Four pipes per line: two driver rows plus the header and its separator.
    assert sq2.count("|") // 4 == 2 + 2
    assert "LEC" not in sq3


@pytest.mark.unit
def test_the_shootout_load_pulls_laps_because_ergast_lacks_the_splits(monkeypatch):
    session = _FakeSession(_shootout_results())
    _install_session(monkeypatch, session)

    get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert session.load_kwargs == {"telemetry": False, "laps": True, "weather": False}


@pytest.mark.unit
def test_a_shootout_with_no_split_data_degrades_to_a_flat_ordered_list(monkeypatch):
    results = pd.DataFrame(
        [
            {"Position": 1.0, "Abbreviation": "VER", "Time": _lap("1:27.900")},
            {"Position": 2.0, "Abbreviation": "NOR", "Time": pd.NaT},
        ]
    )
    _install_session(monkeypatch, _FakeSession(results))

    tables = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert "*(Detailed SQ1/SQ2/SQ3 split data currently unavailable)*" in tables
    assert "| 1.0 | VER | 01:27.900 |" in tables
    # No time set is a dash, never a zero.
    assert "| 2.0 | NOR | - |" in tables


@pytest.mark.unit
def test_a_segment_column_present_but_wholly_empty_is_skipped(monkeypatch):
    results = pd.DataFrame(
        [
            {"Position": 1.0, "Abbreviation": "VER", "Q1": _lap("1:29.100"), "Q2": pd.NaT, "Q3": pd.NaT},
        ]
    )
    _install_session(monkeypatch, _FakeSession(results))

    tables = get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert "### SQ1 Results" in tables
    assert "SQ2 Results" not in tables
    assert "SQ3 Results" not in tables


@pytest.mark.unit
def test_a_non_sprint_weekend_is_explained_rather_than_raised(monkeypatch):
    """The likeliest call: the model tries SQ on a weekend that had none."""
    _install_session(monkeypatch, ValueError("session not found"))

    assert get_sprint_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"}) == (
        "Could not fetch Sprint Qualifying. Note: Monaco 2026 might not be a Sprint weekend. Error: session not found"
    )


# ---------------------------------------------------------------------------
# get_qualifying_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_qualifying_tool_asks_fastf1_for_the_q_session(monkeypatch):
    calls = _install_session(monkeypatch, _FakeSession(_shootout_results()))

    get_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"})

    assert calls == [(2026, "Monaco", "Q")]


@pytest.mark.unit
def test_qualifying_is_split_into_q1_q2_and_q3_ordered_by_time(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_shootout_results()))

    tables = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"})

    assert "### Q1 Results (Monaco 2026)" in tables
    assert "### Q2 Results" in tables
    assert "### Q3 Results (Pole Position)" in tables
    assert "| 1 | VER | 01:27.900 |" in tables.split("### Q3 Results (Pole Position)")[1]


@pytest.mark.unit
def test_a_driver_with_no_q1_time_is_still_listed_with_a_dash(monkeypatch):
    """Q1 lists the whole entry list, so an empty time must read as empty."""
    _install_session(monkeypatch, _FakeSession(_shootout_results()))

    tables = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"})

    assert "| 4 | HAM | - |" in tables


@pytest.mark.unit
def test_a_session_where_nobody_reached_q2_shows_only_the_q1_table(monkeypatch):
    results = pd.DataFrame(
        [{"Position": 1.0, "Abbreviation": "VER", "Q1": _lap("1:29.100"), "Q2": pd.NaT, "Q3": pd.NaT}]
    )
    _install_session(monkeypatch, _FakeSession(results))

    tables = get_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"})

    assert "Q2 Results" not in tables
    assert "Q3 Results" not in tables


@pytest.mark.unit
def test_a_qualifying_lookup_failure_is_reported_rather_than_raised(monkeypatch):
    _install_session(monkeypatch, ConnectionError("ergast unreachable"))

    assert get_qualifying_results.invoke({"year": 2026, "grand_prix": "Monaco"}) == (
        "Failed to fetch qualifying results: ergast unreachable"
    )
