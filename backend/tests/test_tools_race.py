"""Tests for app.api.tools.race — classification, head-to-head and anomalies.

Three tools the model reaches for when asked what happened in a race. The risks
are resolution-shaped and status-shaped rather than arithmetic-shaped:

* **A name has to resolve to the right driver.** The lookup is substring based
  so "Max" works, which also means a short or empty query can land on whoever
  happens to be first in the entry list.
* **A retirement must not read as a finishing time.** FastF1 keeps a ``Time``
  on rows that never saw the flag, and rendering it would put a race time next
  to a driver who crashed out.
* **A missing sector is an unknown gap, not a dead heat.** Zero would show as
  the driver being level; the tools render a dash instead.

FastF1 is mocked at the ``get_session`` boundary and the anomaly service at its
import site; the frames and Series are real pandas.
"""

from __future__ import annotations

import fastf1
import pandas as pd
import pytest

from app.api.tools.race import (
    _format_race_time,
    compare_drivers,
    get_race_anomalies,
    get_race_results,
)


class _FakeLaps:
    """``session.laps``: supports the pick_drivers().pick_fastest() chain."""

    def __init__(self, fastest_by_driver: dict[str, pd.Series | None]):
        self._fastest_by_driver = fastest_by_driver
        self._picked: str | None = None

    def pick_drivers(self, code: str) -> _FakeLaps:
        picked = _FakeLaps(self._fastest_by_driver)
        picked._picked = code
        return picked

    def pick_fastest(self) -> pd.Series | None:
        return self._fastest_by_driver.get(self._picked)


class _FakeSession:
    def __init__(self, results: pd.DataFrame, laps: _FakeLaps | None = None):
        self.results = results
        self.laps = laps
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


def _lap(total: str, s1: str, s2: str, s3: str) -> pd.Series:
    def _timing(text: str | None):
        return pd.NaT if text is None else pd.Timedelta(text)

    return pd.Series(
        {
            "LapTime": _timing(total),
            "Sector1Time": _timing(s1),
            "Sector2Time": _timing(s2),
            "Sector3Time": _timing(s3),
        }
    )


# ---------------------------------------------------------------------------
# compare_drivers
# ---------------------------------------------------------------------------


def _entry_list() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"LastName": "Verstappen", "BroadcastName": "M VERSTAPPEN", "Abbreviation": "VER"},
            {"LastName": "Norris", "BroadcastName": "L NORRIS", "Abbreviation": "NOR"},
        ]
    )


def _comparison_session(fastest: dict[str, pd.Series | None] | None = None) -> _FakeSession:
    laps = _FakeLaps(
        fastest
        if fastest is not None
        else {
            "VER": _lap("0 days 00:01:29.100", "0 days 00:00:29.000", "0 days 00:00:30.000", "0 days 00:00:30.100"),
            "NOR": _lap("0 days 00:01:29.400", "0 days 00:00:29.250", "0 days 00:00:29.900", "0 days 00:00:30.250"),
        }
    )
    return _FakeSession(_entry_list(), laps)


@pytest.mark.unit
def test_the_comparison_reads_the_qualifying_session(monkeypatch):
    """Race pace and a qualifying lap are different questions; "Q" is the contract."""
    calls = _install_session(monkeypatch, _comparison_session())

    compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "VER", "driver2": "NOR"})

    assert calls == [(2026, "Bahrain", "Q")]


@pytest.mark.unit
def test_the_comparison_loads_laps_but_not_telemetry(monkeypatch):
    """pick_fastest needs laps; telemetry is a multi-megabyte fetch it never reads."""
    session = _comparison_session()
    _install_session(monkeypatch, session)

    compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "VER", "driver2": "NOR"})

    assert session.load_kwargs == {"telemetry": False, "laps": True, "weather": False}


@pytest.mark.unit
@pytest.mark.parametrize(
    "query",
    [
        "Verstappen",  # exact surname
        "verstappen",  # case insensitive
        "stappen",  # partial surname
        "VER",  # abbreviation
        "ver",  # abbreviation, lowercased
        "M VERSTAPPEN",  # broadcast name
    ],
)
def test_a_driver_resolves_from_any_of_the_name_forms_a_model_might_use(monkeypatch, query):
    """The model passes whatever the user typed; all of these mean the same driver."""
    _install_session(monkeypatch, _comparison_session())

    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": query, "driver2": "NOR"})

    assert "**VER vs NOR**" in table


@pytest.mark.unit
def test_a_name_matching_nobody_is_reported_rather_than_guessed(monkeypatch):
    _install_session(monkeypatch, _comparison_session())

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "Schumacher", "driver2": "NOR"})

    assert result == "Could not find drivers 'Schumacher' or 'NOR' in the entry list for Bahrain 2026."


@pytest.mark.unit
def test_a_driver_who_set_no_lap_is_reported_rather_than_compared(monkeypatch):
    """pick_fastest returns None for a driver who never ran; the gap is undefined."""
    _install_session(monkeypatch, _comparison_session({"VER": _lap("0 days 00:01:29.100", None, None, None)}))

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "VER", "driver2": "NOR"})

    assert result == "No lap data found for VER or NOR."


@pytest.mark.unit
def test_the_comparison_renders_total_and_per_sector_gaps(monkeypatch):
    _install_session(monkeypatch, _comparison_session())

    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "VER", "driver2": "NOR"})

    assert table.splitlines() == [
        "### Telemetry: Bahrain 2026",
        "**VER vs NOR**",
        "",
        "| Sector | Gap (VER to NOR) | Status |",
        "| :--- | :--- | :--- |",
        # VER is 0.3s up the road, so every gap is negative and green.
        # Only the total carries a word; the sector rows are the bare indicator.
        "| **TOTAL** | **-0.300s** | 🟢 Faster |",
        "| Sector 1 | -0.250s | 🟢 |",
        # NOR took a tenth back in sector 2.
        "| Sector 2 | +0.100s | 🔴 |",
        "| Sector 3 | -0.150s | 🟢 |",
    ]


@pytest.mark.unit
def test_a_missing_sector_is_shown_as_unknown_rather_than_level(monkeypatch):
    """A deleted lap subtracts to NaT; rendering 0.000s would claim a dead heat."""
    _install_session(
        monkeypatch,
        _comparison_session(
            {
                "VER": _lap("0 days 00:01:29.100", "0 days 00:00:29.000", None, "0 days 00:00:30.100"),
                "NOR": _lap("0 days 00:01:29.400", "0 days 00:00:29.250", "0 days 00:00:29.900", None),
            }
        ),
    )

    table = compare_drivers.invoke({"year": 2026, "grand_prix": "Bahrain", "driver1": "VER", "driver2": "NOR"})

    assert "| Sector 2 | - | ⚪ |" in table
    assert "| Sector 3 | - | ⚪ |" in table


@pytest.mark.unit
def test_a_comparison_failure_is_reported_rather_than_raised(monkeypatch):
    _install_session(monkeypatch, ValueError("no qualifying session"))

    result = compare_drivers.invoke({"year": 2026, "grand_prix": "Nowhere", "driver1": "VER", "driver2": "NOR"})

    assert result == "Comparison failed: no qualifying session"


# ---------------------------------------------------------------------------
# _format_race_time
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_winners_absolute_time_drops_the_leading_hour_group():
    """FastF1 renders a timedelta; the days and the zero hour are noise."""
    assert _format_race_time("Finished", pd.Timedelta("0 days 01:32:45.123456")) == "01:32:45.123"


@pytest.mark.unit
def test_a_gap_to_the_leader_is_trimmed_to_milliseconds():
    # removeprefix strips one zero group, so a sub-minute gap keeps its minutes field.
    assert _format_race_time("Finished", pd.Timedelta("0 days 00:00:05.123456")) == "00:05.123"


@pytest.mark.unit
def test_a_whole_second_gap_needs_no_trimming():
    assert _format_race_time("Finished", pd.Timedelta("0 days 00:00:05")) == "00:05"


@pytest.mark.unit
def test_a_finisher_with_no_recorded_time_is_shown_as_an_interval():
    assert _format_race_time("Finished", pd.NaT) == "Interval"


@pytest.mark.unit
@pytest.mark.parametrize("status", ["+1 Lap", "+2 Laps"])
def test_a_lapped_car_keeps_its_lap_deficit(status):
    assert _format_race_time(status, pd.NaT) == status


@pytest.mark.unit
@pytest.mark.parametrize("status", ["Accident", "Engine", "Disqualified"])
def test_a_retirement_is_flagged_rather_than_timed(status):
    """A retired driver shown with a race time reads as a valid classification."""
    assert _format_race_time(status, pd.Timedelta("0 days 01:00:00")) == f"❌ {status}"


# ---------------------------------------------------------------------------
# get_race_results
# ---------------------------------------------------------------------------


def _race_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Position": 2.0,
                "Abbreviation": "NOR",
                "TeamName": "McLaren",
                "Points": 18.0,
                "GridPosition": 1.0,
                "Status": "Finished",
                "Time": pd.Timedelta("0 days 00:00:05.123456"),
            },
            {
                "Position": 1.0,
                "Abbreviation": "VER",
                "TeamName": "Red Bull Racing Honda RBPT",
                "Points": 25.0,
                "GridPosition": 3.0,
                "Status": "Finished",
                "Time": pd.Timedelta("0 days 01:32:45.123456"),
            },
            {
                "Position": 3.0,
                "Abbreviation": "LEC",
                "TeamName": "Ferrari",
                "Points": 15.0,
                "GridPosition": 3.0,
                "Status": "Finished",
                "Time": pd.NaT,
            },
            # Pit-lane start: FastF1 records grid position 0.
            {
                "Position": 4.0,
                "Abbreviation": "HAM",
                "TeamName": "Mercedes",
                "Points": 12.0,
                "GridPosition": 0.0,
                "Status": "+1 Lap",
                "Time": pd.NaT,
            },
            # Retired and unclassified.
            {
                "Position": float("nan"),
                "Abbreviation": "ALO",
                "TeamName": "Aston Martin",
                "Points": 0.0,
                "GridPosition": 8.0,
                "Status": "Accident",
                "Time": pd.NaT,
            },
        ]
    )


@pytest.mark.unit
def test_the_classification_reads_the_race_session(monkeypatch):
    calls = _install_session(monkeypatch, _FakeSession(_race_results()))

    get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert calls == [(2026, "Bahrain", "R")]


@pytest.mark.unit
def test_the_classification_is_ordered_by_finishing_position(monkeypatch):
    """FastF1 does not guarantee the order; a shuffled table misreports the result."""
    _install_session(monkeypatch, _FakeSession(_race_results()))

    rows = get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"}).splitlines()
    drivers = [
        line.split("|")[2].strip()
        for line in rows
        if line.startswith("| ") and "Driver" not in line and ":--" not in line
    ]

    assert drivers == ["VER", "NOR", "LEC", "HAM", "ALO"]


@pytest.mark.unit
def test_the_winner_is_marked_with_a_trophy(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_race_results()))

    assert "| 🏆 1 | VER |" in get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"})


@pytest.mark.unit
def test_a_long_team_name_is_truncated_to_keep_the_table_readable(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_race_results()))

    table = get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert "| Red Bull Racing |" in table
    assert "Honda RBPT" not in table


@pytest.mark.unit
def test_whole_points_lose_their_trailing_decimal(monkeypatch):
    """FastF1 stores points as floats; "25.0" in a championship table reads wrong."""
    _install_session(monkeypatch, _FakeSession(_race_results()))

    table = get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"})

    assert table.rstrip().splitlines()[3].endswith("| 25 |")
    assert "25.0" not in table


@pytest.mark.unit
@pytest.mark.parametrize(
    ("driver", "expected"),
    [
        ("VER", "⬆️2"),  # P3 on the grid to the win
        ("NOR", "⬇️1"),  # pole to second
        ("LEC", "➖"),  # started and finished third
    ],
)
def test_the_position_change_from_the_grid_is_shown(monkeypatch, driver, expected):
    _install_session(monkeypatch, _FakeSession(_race_results()))

    row = next(
        line
        for line in get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"}).splitlines()
        if f"| {driver} |" in line
    )

    assert f"| {expected} |" in row


@pytest.mark.unit
def test_a_pit_lane_start_is_shown_instead_of_a_grid_slot(monkeypatch):
    """Grid position 0 is not a front-row start; it means the car left the pits."""
    _install_session(monkeypatch, _FakeSession(_race_results()))

    row = next(
        line
        for line in get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"}).splitlines()
        if "| HAM |" in line
    )

    assert "| PL |" in row
    # No numeric grid slot means the gain/loss cannot be computed either.
    assert "| - |" in row


@pytest.mark.unit
def test_an_unclassified_driver_is_shown_as_nc(monkeypatch):
    _install_session(monkeypatch, _FakeSession(_race_results()))

    row = next(
        line
        for line in get_race_results.invoke({"year": 2026, "grand_prix": "Bahrain"}).splitlines()
        if "| ALO |" in line
    )

    assert row.startswith("| NC |")
    assert "❌ Accident" in row


@pytest.mark.unit
def test_a_race_results_failure_is_reported_rather_than_raised(monkeypatch):
    _install_session(monkeypatch, ValueError("session not available"))

    assert get_race_results.invoke({"year": 2026, "grand_prix": "Nowhere"}) == (
        "Failed to fetch race results: session not available"
    )


# ---------------------------------------------------------------------------
# get_race_anomalies
# ---------------------------------------------------------------------------


def _install_anomalies(monkeypatch, result):
    import app.services.anomaly as anomaly_module

    def _detect(year, round_num):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(anomaly_module, "detect_race_anomalies", _detect)


@pytest.mark.unit
def test_the_notable_stories_are_listed_as_bullets(monkeypatch):
    _install_anomalies(
        monkeypatch,
        {
            "available": True,
            "anomalies": [
                {"detail": "HAM gained 12 places from P18"},
                {"detail": "VER retired from the lead on lap 40"},
            ],
        },
    )

    lines = get_race_anomalies.invoke({"year": 2026, "round_num": 4}).splitlines()

    assert lines == [
        "### Notable stories — 2026 Round 4",
        "",
        "- HAM gained 12 places from P18",
        "- VER retired from the lead on lap 40",
    ]


@pytest.mark.unit
def test_a_race_with_nothing_notable_says_so_rather_than_returning_an_empty_header(monkeypatch):
    """An empty section would invite the model to invent stories to fill it."""
    _install_anomalies(monkeypatch, {"available": True, "anomalies": []})

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 4}) == (
        "### 2026 Round 4: no major anomalies — a clean, orderly race."
    )


@pytest.mark.unit
def test_a_race_that_has_not_run_is_reported_as_having_no_data(monkeypatch):
    _install_anomalies(monkeypatch, {"available": False, "anomalies": []})

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 22}) == (
        "No completed-race data available for 2026 Round 22."
    )


@pytest.mark.unit
def test_an_anomaly_failure_is_reported_rather_than_raised(monkeypatch):
    _install_anomalies(monkeypatch, RuntimeError("f1db is locked"))

    assert get_race_anomalies.invoke({"year": 2026, "round_num": 4}) == "Anomaly analysis failed: f1db is locked"
