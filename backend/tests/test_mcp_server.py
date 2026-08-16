"""Tests for mcp_server — the Model Context Protocol tool surface.

This is the second front door to the same F1 data: Claude Desktop and Cursor call
these tools directly, without the FastAPI app or the chat agent in between. It
had no tests at all, and because coverage only *warns* about a module it never
imported, the suite's 100% gate passed straight over it.

Every tool here answers with a **string** and swallows its own exceptions, which
is the right shape for an MCP client but means a broken tool looks like a normal
reply. The cases below therefore pin the failure text as carefully as the happy
path, plus the rendering decisions a reader would otherwise have to trust:

* **A retirement must not read as a finishing time.** FastF1 keeps a ``Time`` on
  rows that never saw the flag; the classification renders the status instead.
* **Grid/finish deltas must not be computed from non-numeric cells.** A pit-lane
  start has no grid number, and subtracting from it would print nonsense.
* **A phase that did not run must produce nothing**, not an empty table with
  headers implying it did.

``@mcp.tool()`` returns the undecorated function, so each tool is called
directly. FastF1 and Ergast are mocked at their module boundary; the frames and
Series are real pandas.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import types
from typing import Any, ClassVar

import fastf1
import pandas as pd
import pytest

# `load_dotenv()` at mcp_server's module scope repopulates the credentials
# conftest cleared, and this import runs during collection — before any test
# body — so the leak would reach the whole session. Same guard, and same reason,
# as the one in test_main_app.py. Restore the environment byte for byte the
# moment the import returns.
_ENV_BEFORE_IMPORT = dict(os.environ)
import mcp_server  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_IMPORT)


class _Ctx:
    """Stand-in for ``mcp.server.fastmcp.Context``: records progress reports."""

    def __init__(self) -> None:
        self.progress: list[tuple[float, float]] = []

    async def report_progress(self, progress: float, total: float) -> None:
        self.progress.append((progress, total))


class _Session:
    def __init__(self, results: pd.DataFrame, laps: Any = None) -> None:
        self.results = results
        self.laps = laps
        self.load_kwargs: dict | None = None

    def load(self, **kwargs: Any) -> None:
        self.load_kwargs = kwargs


class _Laps:
    """``session.laps`` supporting the pick_drivers().pick_fastest() chain."""

    def __init__(self, fastest: dict[str, pd.Series | None]) -> None:
        self._fastest = fastest
        self._picked: str | None = None

    def pick_drivers(self, code: str) -> _Laps:
        picked = _Laps(self._fastest)
        picked._picked = code
        return picked

    def pick_fastest(self) -> pd.Series | None:
        return self._fastest.get(self._picked)


def _install_session(monkeypatch: pytest.MonkeyPatch, session: Any) -> list[tuple]:
    """Patch ``fastf1.get_session``; an Exception instance is raised instead."""
    calls: list[tuple] = []

    def _get_session(year: int, grand_prix: str, identifier: str) -> Any:
        calls.append((year, grand_prix, identifier))
        if isinstance(session, Exception):
            raise session
        return session

    monkeypatch.setattr(fastf1, "get_session", _get_session)
    return calls


def _install_schedule(monkeypatch: pytest.MonkeyPatch, schedule: Any) -> None:
    def _get_event_schedule(year: int, include_testing: bool = True) -> Any:
        if isinstance(schedule, Exception):
            raise schedule
        return schedule

    monkeypatch.setattr(fastf1, "get_event_schedule", _get_event_schedule)


def _install_ergast(monkeypatch: pytest.MonkeyPatch, ergast: Any) -> None:
    monkeypatch.setattr(mcp_server, "Ergast", lambda *a, **k: ergast)


def _fake_module(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


# ---------------------------------------------------------------------------
# _fmt_timedelta
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (pd.NaT, "-"),
        # `0 days 00:01:32.123456` — the day part and a zero hour both go.
        (pd.Timedelta("0 days 00:01:32.123456"), "01:32.123"),
        (pd.Timedelta("0 days 01:32:10.500000"), "01:32:10."),
        # A whole race time under the hour keeps its minutes: `removeprefix`
        # strips one leading `00:`, not every zero group.
        (pd.Timedelta(seconds=5), "00:05"),
        (pd.Timedelta("0 days 01:32:10"), "01:32:10"),
    ],
)
def test_fmt_timedelta_strips_the_day_and_zero_hour_parts(value: Any, expected: str) -> None:
    assert mcp_server._fmt_timedelta(value) == expected


def test_fmt_timedelta_truncates_anything_longer_than_ten_characters() -> None:
    """Keeps a lap time from widening the markdown column with microseconds."""
    assert len(mcp_server._fmt_timedelta(pd.Timedelta("0 days 01:32:10.123456"))) == 9


# ---------------------------------------------------------------------------
# get_season_schedule
# ---------------------------------------------------------------------------
async def test_season_schedule_marks_past_races_completed_and_future_ones_upcoming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_schedule(
        monkeypatch,
        pd.DataFrame(
            {
                "RoundNumber": [1, 2],
                "EventName": ["Bahrain Grand Prix", "Saudi Arabian Grand Prix"],
                "EventDate": [
                    pd.Timestamp("2020-03-15", tz="UTC"),
                    pd.Timestamp("2099-03-15", tz="UTC"),
                ],
            }
        ),
    )
    ctx = _Ctx()

    output = await mcp_server.get_season_schedule(2020, ctx)

    assert "| 1 | Bahrain Grand Prix | 15 Mar | Completed |" in output
    assert "| 2 | Saudi Arabian Grand Prix | 15 Mar | Upcoming |" in output
    # The last *completed* race, not simply the last row.
    assert "**Last completed race:** Bahrain Grand Prix" in output
    assert ctx.progress == [(10, 100), (80, 100), (100, 100)]


async def test_season_schedule_reports_no_completed_race_before_the_season_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_schedule(
        monkeypatch,
        pd.DataFrame(
            {
                "RoundNumber": [1],
                "EventName": ["Bahrain Grand Prix"],
                "EventDate": [pd.Timestamp("2099-03-15", tz="UTC")],
            }
        ),
    )

    output = await mcp_server.get_season_schedule(2099, _Ctx())

    assert "**Last completed race:** None" in output


async def test_season_schedule_says_so_when_the_calendar_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_schedule(monkeypatch, pd.DataFrame())

    assert await mcp_server.get_season_schedule(1949, _Ctx()) == "No schedule data found for 1949."


async def test_season_schedule_returns_the_error_as_text_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An MCP tool answers with a string; an exception would break the client."""
    _install_schedule(monkeypatch, ConnectionError("upstream down"))

    assert await mcp_server.get_season_schedule(2024, _Ctx()) == "Error fetching schedule: upstream down"


# ---------------------------------------------------------------------------
# get_race_results
# ---------------------------------------------------------------------------
_A_RACE_TIME = pd.Timedelta("0 days 01:32:10")


def _race_row(
    position: float,
    abbreviation: str,
    *,
    grid: float = 5.0,
    status: str = "Finished",
    time: Any = _A_RACE_TIME,
    points: float = 25.0,
    team: str = "Red Bull Racing Honda RBPT",
) -> dict:
    return {
        "Position": position,
        "Abbreviation": abbreviation,
        "TeamName": team,
        "Points": points,
        "GridPosition": grid,
        "Status": status,
        "Time": time,
    }


async def test_race_results_renders_position_change_in_both_directions_and_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_session(
        monkeypatch,
        _Session(
            pd.DataFrame(
                [
                    _race_row(1.0, "VER", grid=3.0),  # gained two
                    _race_row(2.0, "NOR", grid=1.0),  # lost one
                    _race_row(3.0, "LEC", grid=3.0),  # level
                ]
            )
        ),
    )

    output = await mcp_server.get_race_results(2024, "Bahrain", _Ctx())

    assert "| 1 | VER |" in output
    assert "| +2 |" in output
    assert "| -1 |" in output
    assert "| = |" in output


async def test_race_results_shows_a_pit_lane_start_as_pl_with_no_computed_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grid 0 is a pit-lane start; there is no grid number to subtract from."""
    _install_session(monkeypatch, _Session(pd.DataFrame([_race_row(8.0, "HUL", grid=0.0)])))

    output = await mcp_server.get_race_results(2024, "Bahrain", _Ctx())

    assert "| PL |" in output
    assert "| - |" in output


async def test_race_results_shows_an_unclassified_driver_as_nc(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(
        monkeypatch,
        _Session(pd.DataFrame([_race_row(float("nan"), "STR", status="Accident", time=pd.NaT, points=0.0)])),
    )

    output = await mcp_server.get_race_results(2024, "Bahrain", _Ctx())

    assert "| NC |" in output
    assert "DNF (Accident)" in output


@pytest.mark.parametrize(
    ("status", "time", "expected"),
    [
        ("Finished", pd.Timedelta("0 days 01:32:10"), "01:32:10"),
        # Finished but no time recorded — the gap is unknown, not zero.
        ("Finished", pd.NaT, "Interval"),
        ("+1 Lap", pd.NaT, "+1 Lap"),
        ("Engine", pd.NaT, "DNF (Engine)"),
    ],
)
async def test_race_results_never_renders_a_retirement_as_a_finishing_time(
    monkeypatch: pytest.MonkeyPatch, status: str, time: Any, expected: str
) -> None:
    _install_session(monkeypatch, _Session(pd.DataFrame([_race_row(10.0, "OCO", status=status, time=time)])))

    assert expected in await mcp_server.get_race_results(2024, "Bahrain", _Ctx())


async def test_race_results_truncates_a_long_team_name_to_the_column_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_session(
        monkeypatch,
        _Session(pd.DataFrame([_race_row(1.0, "VER", team="Red Bull Racing Honda RBPT")])),
    )

    output = await mcp_server.get_race_results(2024, "Bahrain", _Ctx())

    assert "Red Bull Racing" in output
    assert "Honda RBPT" not in output


async def test_race_results_loads_the_race_session_without_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telemetry is the expensive part of a FastF1 load and is not needed here."""
    session = _Session(pd.DataFrame([_race_row(1.0, "VER")]))
    calls = _install_session(monkeypatch, session)

    await mcp_server.get_race_results(2024, "Bahrain", _Ctx())

    assert calls == [(2024, "Bahrain", "R")]
    assert session.load_kwargs == {"telemetry": False, "laps": False, "weather": False}


async def test_race_results_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(monkeypatch, ValueError("no such event"))

    assert await mcp_server.get_race_results(2024, "Nowhere", _Ctx()) == ("Failed to fetch race results: no such event")


# ---------------------------------------------------------------------------
# _qualifying_phase_rows / get_qualifying_results
# ---------------------------------------------------------------------------
def test_a_phase_column_that_is_absent_produces_no_rows() -> None:
    results = pd.DataFrame({"Abbreviation": ["VER"], "Q1": [pd.Timedelta("0 days 00:01:30")]})

    assert mcp_server._qualifying_phase_rows(results, "Q3", "Bahrain", 2024) == []


def test_a_phase_that_ran_but_recorded_no_times_produces_no_rows() -> None:
    """An all-NaN column means the phase did not happen — no empty table for it."""
    results = pd.DataFrame({"Abbreviation": ["VER"], "Q3": [pd.NaT]})

    assert mcp_server._qualifying_phase_rows(results, "Q3", "Bahrain", 2024) == []


def test_q1_keeps_every_entrant_so_a_driver_with_no_time_still_appears_in_order() -> None:
    results = pd.DataFrame(
        {
            "Abbreviation": ["VER", "SAR"],
            "Q1": [pd.Timedelta("0 days 00:01:30"), pd.NaT],
        }
    )

    rows = mcp_server._qualifying_phase_rows(results, "Q1", "Bahrain", 2024)

    assert "### Q1 Results (Bahrain 2024)" in rows[0]
    # SAR set no time, so no data row is rendered for them.
    assert not any("SAR" in row for row in rows)
    assert any("VER" in row for row in rows)


def test_q3_lists_only_the_drivers_who_progressed() -> None:
    results = pd.DataFrame(
        {
            "Abbreviation": ["VER", "NOR", "SAR"],
            "Q3": [pd.Timedelta("0 days 00:01:29"), pd.Timedelta("0 days 00:01:30"), pd.NaT],
        }
    )

    rows = mcp_server._qualifying_phase_rows(results, "Q3", "Bahrain", 2024)
    body = "\n".join(rows)

    assert "| 1 | VER |" in body
    assert "| 2 | NOR |" in body
    assert "SAR" not in body


async def test_qualifying_results_renders_each_phase_that_ran(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(
        monkeypatch,
        _Session(
            pd.DataFrame(
                {
                    "Abbreviation": ["VER", "NOR"],
                    "Q1": [pd.Timedelta("0 days 00:01:31"), pd.Timedelta("0 days 00:01:32")],
                    "Q2": [pd.Timedelta("0 days 00:01:30"), pd.Timedelta("0 days 00:01:31")],
                    "Q3": [pd.Timedelta("0 days 00:01:29"), pd.NaT],
                }
            )
        ),
    )

    output = await mcp_server.get_qualifying_results(2024, "Bahrain", _Ctx())

    assert "### Q1 Results (Bahrain 2024)" in output
    assert "### Q2 Results (Bahrain 2024)" in output
    assert "### Q3 Results (Bahrain 2024)" in output


async def test_qualifying_results_says_so_when_no_phase_has_data(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(monkeypatch, _Session(pd.DataFrame({"Abbreviation": ["VER"]})))

    assert await mcp_server.get_qualifying_results(2024, "Bahrain", _Ctx()) == ("No qualifying data for Bahrain 2024.")


async def test_qualifying_results_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(monkeypatch, ValueError("boom"))

    assert await mcp_server.get_qualifying_results(2024, "Bahrain", _Ctx()) == (
        "Failed to fetch qualifying results: boom"
    )


# ---------------------------------------------------------------------------
# get_sprint_results
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["Disqualified", "DSQ"])
async def test_sprint_results_renders_a_disqualification_as_dsq(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    """A DSQ has a recorded time; showing it would imply the result still stood."""
    _install_session(
        monkeypatch,
        _Session(
            pd.DataFrame(
                [
                    {
                        "Position": 1.0,
                        "Abbreviation": "VER",
                        "Status": status,
                        "Time": pd.Timedelta("0 days 00:30:00"),
                    }
                ]
            )
        ),
    )

    output = await mcp_server.get_sprint_results(2024, "Miami", _Ctx())

    assert "| 1 | VER | DSQ |" in output


async def test_sprint_results_shows_the_time_for_a_finisher_and_the_status_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_session(
        monkeypatch,
        _Session(
            pd.DataFrame(
                [
                    {
                        "Position": 1.0,
                        "Abbreviation": "VER",
                        "Status": "Finished",
                        "Time": pd.Timedelta("0 days 00:30:00"),
                    },
                    {"Position": 2.0, "Abbreviation": "PER", "Status": "Collision", "Time": pd.NaT},
                ]
            )
        ),
    )

    output = await mcp_server.get_sprint_results(2024, "Miami", _Ctx())

    assert "| 1 | VER | 30:00 |" in output
    assert "| 2 | PER | Collision |" in output


async def test_sprint_results_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(monkeypatch, ValueError("not a sprint weekend"))

    assert await mcp_server.get_sprint_results(2024, "Monaco", _Ctx()) == (
        "Could not fetch Sprint results: not a sprint weekend"
    )


# ---------------------------------------------------------------------------
# get_sprint_qualifying_results
# ---------------------------------------------------------------------------
async def test_sprint_qualifying_labels_the_phases_sq_while_reading_the_q_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FastF1 stores shootout times in Q1/Q2/Q3; the client expects SQ labels."""
    _install_session(
        monkeypatch,
        _Session(
            pd.DataFrame(
                {
                    "Abbreviation": ["VER", "NOR"],
                    "Q1": [pd.Timedelta("0 days 00:01:31"), pd.Timedelta("0 days 00:01:32")],
                    "Q2": [pd.NaT, pd.NaT],
                    "Q3": [pd.Timedelta("0 days 00:01:29"), pd.NaT],
                }
            )
        ),
    )

    output = await mcp_server.get_sprint_qualifying_results(2024, "Miami", _Ctx())

    assert "### SQ1 Results (Miami 2024)" in output
    assert "### SQ3 Results (Miami 2024)" in output
    assert "SQ2" not in output


async def test_sprint_qualifying_says_the_split_is_unavailable_when_no_phase_has_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_session(monkeypatch, _Session(pd.DataFrame({"Abbreviation": ["VER"]})))

    output = await mcp_server.get_sprint_qualifying_results(2024, "Miami", _Ctx())

    assert "### Sprint Qualifying Results (Miami 2024)" in output
    assert "unavailable" in output


async def test_sprint_qualifying_error_text_names_the_likely_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The usual failure is asking about a non-sprint weekend, so it says so."""
    _install_session(monkeypatch, ValueError("no SQ session"))

    output = await mcp_server.get_sprint_qualifying_results(2024, "Monaco", _Ctx())

    assert "might not be a Sprint weekend" in output
    assert "no SQ session" in output


# ---------------------------------------------------------------------------
# compare_drivers
# ---------------------------------------------------------------------------
def _entry_list() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Abbreviation": "VER", "LastName": "Verstappen", "BroadcastName": "M VERSTAPPEN"},
            {"Abbreviation": "NOR", "LastName": "Norris", "BroadcastName": "L NORRIS"},
        ]
    )


def _quali_lap(total: str, s1: str, s2: str, s3: str | None) -> pd.Series:
    def _timing(text: str | None) -> Any:
        return pd.NaT if text is None else pd.Timedelta(text)

    return pd.Series(
        {
            "LapTime": _timing(total),
            "Sector1Time": _timing(s1),
            "Sector2Time": _timing(s2),
            "Sector3Time": _timing(s3),
        }
    )


@pytest.mark.parametrize("query", ["Verstappen", "verstappen", "ver", "M VERSTAPPEN"])
async def test_compare_drivers_resolves_a_driver_by_surname_broadcast_name_or_code(
    monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    laps = _Laps(
        {
            "VER": _quali_lap("0 days 00:01:29.500", "0 days 00:00:29", "0 days 00:00:30", "0 days 00:00:30.5"),
            "NOR": _quali_lap("0 days 00:01:30.000", "0 days 00:00:29.2", "0 days 00:00:30.3", "0 days 00:00:30.5"),
        }
    )
    _install_session(monkeypatch, _Session(_entry_list(), laps=laps))

    output = await mcp_server.compare_drivers(2024, "Bahrain", query, "Norris", _Ctx())

    assert "**VER vs NOR**" in output


async def test_compare_drivers_reports_the_signed_total_and_sector_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive means the first driver is slower — the sign carries the meaning."""
    laps = _Laps(
        {
            "VER": _quali_lap("0 days 00:01:30.500", "0 days 00:00:30", "0 days 00:00:30", "0 days 00:00:30.5"),
            "NOR": _quali_lap("0 days 00:01:30.000", "0 days 00:00:29", "0 days 00:00:30", "0 days 00:00:31"),
        }
    )
    _install_session(monkeypatch, _Session(_entry_list(), laps=laps))

    output = await mcp_server.compare_drivers(2024, "Bahrain", "Verstappen", "Norris", _Ctx())

    assert "**+0.500s**" in output
    assert "+1.000s" in output
    assert "-0.500s" in output


async def test_compare_drivers_renders_a_missing_sector_as_a_dash_not_a_dead_heat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    laps = _Laps(
        {
            "VER": _quali_lap("0 days 00:01:29.500", "0 days 00:00:29", "0 days 00:00:30", None),
            "NOR": _quali_lap("0 days 00:01:30.000", "0 days 00:00:29", "0 days 00:00:30", "0 days 00:00:31"),
        }
    )
    _install_session(monkeypatch, _Session(_entry_list(), laps=laps))

    output = await mcp_server.compare_drivers(2024, "Bahrain", "Verstappen", "Norris", _Ctx())

    assert "| Sector 3 | - |" in output


async def test_compare_drivers_names_the_drivers_it_could_not_find(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_session(monkeypatch, _Session(_entry_list(), laps=_Laps({})))

    output = await mcp_server.compare_drivers(2024, "Bahrain", "Schumacher", "Norris", _Ctx())

    assert output == "Could not find drivers 'Schumacher' or 'Norris' in the entry list."


async def test_compare_drivers_reports_when_a_resolved_driver_set_no_lap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    laps = _Laps(
        {
            "VER": _quali_lap("0 days 00:01:29.500", "0 days 00:00:29", "0 days 00:00:30", "0 days 00:00:30.5"),
            "NOR": None,
        }
    )
    _install_session(monkeypatch, _Session(_entry_list(), laps=laps))

    output = await mcp_server.compare_drivers(2024, "Bahrain", "Verstappen", "Norris", _Ctx())

    assert output == "No lap data found for VER or NOR."


async def test_compare_drivers_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_session(monkeypatch, ValueError("session unavailable"))

    assert await mcp_server.compare_drivers(2024, "Bahrain", "VER", "NOR", _Ctx()) == (
        "Comparison failed: session unavailable"
    )


# ---------------------------------------------------------------------------
# get_driver_standings
# ---------------------------------------------------------------------------
class _ErgastResponse:
    def __init__(self, content: list[pd.DataFrame]) -> None:
        self.content = content


class _FakeErgast:
    def __init__(
        self,
        *,
        driver_standings: Any = None,
        constructor_standings: Any = None,
        constructor_info: pd.DataFrame | None = None,
        driver_info: pd.DataFrame | None = None,
    ) -> None:
        self._driver_standings = driver_standings
        self._constructor_standings = constructor_standings
        self._constructor_info = constructor_info
        self._driver_info = driver_info

    def get_driver_standings(self, season: int) -> Any:
        if isinstance(self._driver_standings, Exception):
            raise self._driver_standings
        return self._driver_standings

    def get_constructor_standings(self, season: int) -> Any:
        if isinstance(self._constructor_standings, Exception):
            raise self._constructor_standings
        return self._constructor_standings

    def get_constructor_info(self, season: int) -> pd.DataFrame:
        return self._constructor_info if self._constructor_info is not None else pd.DataFrame()

    def get_driver_info(self, season: int, constructor: str) -> pd.DataFrame:
        return self._driver_info if self._driver_info is not None else pd.DataFrame()


def test_driver_standings_joins_multiple_constructor_names_for_a_driver_who_switched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(
        monkeypatch,
        _FakeErgast(
            driver_standings=_ErgastResponse(
                [
                    pd.DataFrame(
                        [
                            {
                                "position": 1,
                                "driverCode": "VER",
                                "constructorNames": ["Red Bull", "AlphaTauri"],
                                "points": 575.0,
                                "wins": 19,
                            }
                        ]
                    )
                ]
            )
        ),
    )

    output = mcp_server.get_driver_standings(2023)

    assert "| 1 | VER | Red Bull, AlphaTauri | 575.0 | 19 |" in output


def test_driver_standings_accepts_the_singular_constructor_name_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(
        monkeypatch,
        _FakeErgast(
            driver_standings=_ErgastResponse(
                [
                    pd.DataFrame(
                        [
                            {
                                "position": 1,
                                "driverCode": "VER",
                                "constructorName": "Red Bull",
                                "points": 575.0,
                                "wins": 19,
                            }
                        ]
                    )
                ]
            )
        ),
    )

    assert "| 1 | VER | Red Bull |" in mcp_server.get_driver_standings(2023)


def test_driver_standings_falls_back_to_placeholders_for_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ergast is an external contract; a sparse row must still render a table."""
    _install_ergast(
        monkeypatch,
        _FakeErgast(driver_standings=_ErgastResponse([pd.DataFrame([{"position": 1, "points": 0.0, "wins": 0}])])),
    )

    output = mcp_server.get_driver_standings(2024)

    assert "???" in output
    assert "Unknown" in output


def test_driver_standings_builds_an_entry_list_before_the_season_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(
        monkeypatch,
        _FakeErgast(
            driver_standings=_ErgastResponse([]),
            constructor_info=pd.DataFrame([{"constructorId": "red_bull", "constructorName": "Red Bull"}]),
            driver_info=pd.DataFrame([{"givenName": "Max", "familyName": "Verstappen"}]),
        ),
    )

    output = mcp_server.get_driver_standings(2099)

    assert "Season not started" in output
    assert "1. Max Verstappen (Red Bull) — 0 pts" in output


def test_driver_standings_reports_no_data_when_even_the_entry_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(monkeypatch, _FakeErgast(driver_standings=_ErgastResponse([])))

    assert mcp_server.get_driver_standings(2099) == "No driver data found for 2099."


def test_driver_standings_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_ergast(monkeypatch, _FakeErgast(driver_standings=ConnectionError("ergast down")))

    assert mcp_server.get_driver_standings(2024) == "Error fetching standings: ergast down"


# ---------------------------------------------------------------------------
# get_constructor_standings
# ---------------------------------------------------------------------------
def test_constructor_standings_renders_the_championship_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_ergast(
        monkeypatch,
        _FakeErgast(
            constructor_standings=_ErgastResponse(
                [pd.DataFrame([{"position": 1, "constructorName": "Red Bull", "points": 860.0, "wins": 21}])]
            )
        ),
    )

    assert "| 1 | Red Bull | 860.0 | 21 |" in mcp_server.get_constructor_standings(2023)


def test_constructor_standings_builds_an_entry_list_before_the_season_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(
        monkeypatch,
        _FakeErgast(
            constructor_standings=_ErgastResponse([]),
            constructor_info=pd.DataFrame([{"constructorName": "Red Bull"}, {"constructorName": "Ferrari"}]),
        ),
    )

    output = mcp_server.get_constructor_standings(2099)

    assert "1. Red Bull — 0 pts" in output
    assert "2. Ferrari — 0 pts" in output


def test_constructor_standings_reports_no_data_when_the_entry_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_ergast(monkeypatch, _FakeErgast(constructor_standings=_ErgastResponse([])))

    assert mcp_server.get_constructor_standings(2099) == "No constructor data found for 2099."


def test_constructor_standings_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_ergast(monkeypatch, _FakeErgast(constructor_standings=ConnectionError("ergast down")))

    assert mcp_server.get_constructor_standings(2024) == ("Error fetching constructor standings: ergast down")


# ---------------------------------------------------------------------------
# consult_rulebook
#
# NOTE: this tool still reads a local ChromaDB directory. The web service moved
# its rulebook RAG to Supabase/pgvector and `backend/data/chroma/` is gitignored
# as obsolete, so in a clean checkout this tool answers with the "database not
# found" hint. These tests pin the behaviour that exists rather than the
# behaviour that should — see the review note about migrating it to pgvector.
# ---------------------------------------------------------------------------
class _Doc:
    def __init__(self, content: str, metadata: dict) -> None:
        self.page_content = content
        self.metadata = metadata


class _Retriever:
    def __init__(self, docs: list[_Doc]) -> None:
        self.docs = docs
        self.queries: list[str] = []

    def invoke(self, query: str) -> list[_Doc]:
        self.queries.append(query)
        return self.docs


class _Chroma:
    # Records the retriever kwargs so a test can assert which regulation year the
    # tool resolved. Class-level on purpose: the tool constructs its own instance.
    last_kwargs: ClassVar[dict] = {}

    def __init__(self, docs: list[_Doc]) -> None:
        self._docs = docs

    def as_retriever(self, search_kwargs: dict) -> _Retriever:
        type(self).last_kwargs = search_kwargs
        return _Retriever(self._docs)


def _redirect_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, *, with_chroma: bool) -> None:
    """Point the tool's ``data/chroma`` lookup at ``tmp_path``.

    Every rulebook test must do this, including the ones that never get as far as
    querying. ``backend/data/chroma/`` is a gitignored leftover from before the
    pgvector migration: on a developer machine that still has one, a test that
    skips this redirect silently takes the "database present" branch and then
    fails on CI, where the directory does not exist.
    """
    if with_chroma:
        (tmp_path / "data" / "chroma").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mcp_server.os.path, "dirname", lambda _path: str(tmp_path))


def _install_chroma(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, docs: list[_Doc]) -> None:
    """Point the tool at an existing dir and stub the two LangChain imports."""
    _redirect_data_dir(monkeypatch, tmp_path, with_chroma=True)
    monkeypatch.setitem(
        sys.modules, "langchain_chroma", _fake_module("langchain_chroma", Chroma=lambda **kw: _Chroma(docs))
    )
    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        _fake_module("langchain_huggingface", HuggingFaceEmbeddings=lambda **kw: object()),
    )


def test_consult_rulebook_returns_the_setup_hint_when_the_database_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The state of a clean checkout — chroma/ is gitignored as obsolete."""
    _redirect_data_dir(monkeypatch, tmp_path, with_chroma=False)
    monkeypatch.setitem(sys.modules, "langchain_chroma", _fake_module("langchain_chroma", Chroma=lambda **kw: None))
    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        _fake_module("langchain_huggingface", HuggingFaceEmbeddings=lambda **kw: object()),
    )

    output = mcp_server.consult_rulebook("parc ferme", year=2024)

    assert "Rulebook database not found" in output


def test_consult_rulebook_returns_excerpts_with_their_source_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    docs = [_Doc("A driver may not\nrejoin unsafely.", {"filename": "sporting.pdf"})]
    _install_chroma(monkeypatch, tmp_path, docs)

    output = mcp_server.consult_rulebook("unsafe rejoin", year=2024)

    assert "**Source:** sporting.pdf" in output
    # Newlines are flattened so the excerpt stays on one line.
    assert "A driver may not rejoin unsafely." in output


def test_consult_rulebook_labels_an_excerpt_with_no_filename_as_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _install_chroma(monkeypatch, tmp_path, [_Doc("text", {})])

    assert "Unknown PDF" in mcp_server.consult_rulebook("q", year=2024)


def test_consult_rulebook_reports_an_empty_result_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _install_chroma(monkeypatch, tmp_path, [])

    assert mcp_server.consult_rulebook("nonexistent rule", year=2024) == (
        "No regulations found for 'nonexistent rule' in the 2024 rulebook."
    )


@pytest.mark.parametrize(
    ("now", "expected_year"),
    [
        # Mid-December, next season's regulations are what people mean.
        (datetime(2024, 12, 20, tzinfo=timezone.utc), "2025"),
        (datetime(2024, 12, 5, tzinfo=timezone.utc), "2024"),
        (datetime(2024, 6, 1, tzinfo=timezone.utc), "2024"),
    ],
)
def test_consult_rulebook_defaults_to_the_regulation_year_in_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, now: datetime, expected_year: str
) -> None:
    _install_chroma(monkeypatch, tmp_path, [_Doc("text", {"filename": "f.pdf"})])

    class _Now:
        @staticmethod
        def now(_tz: Any = None) -> datetime:
            return now

    monkeypatch.setattr(mcp_server, "datetime", _Now)

    mcp_server.consult_rulebook("q")

    assert _Chroma.last_kwargs["filter"] == {"source_year": expected_year}


def test_consult_rulebook_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """The database has to exist for the query to be reached and to fail."""
    _redirect_data_dir(monkeypatch, tmp_path, with_chroma=True)

    def _boom(**kwargs: Any) -> None:
        raise RuntimeError("embeddings unavailable")

    monkeypatch.setitem(sys.modules, "langchain_chroma", _fake_module("langchain_chroma", Chroma=_boom))
    monkeypatch.setitem(
        sys.modules,
        "langchain_huggingface",
        _fake_module("langchain_huggingface", HuggingFaceEmbeddings=_boom),
    )

    assert mcp_server.consult_rulebook("q", year=2024) == ("Rulebook lookup failed: embeddings unavailable")


# ---------------------------------------------------------------------------
# perform_web_search
# ---------------------------------------------------------------------------
def _install_tavily(monkeypatch: pytest.MonkeyPatch, response: Any) -> None:
    class _Client:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key

        def search(self, query: str, search_depth: str, max_results: int) -> Any:
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setitem(sys.modules, "tavily", _fake_module("tavily", TavilyClient=_Client))


def test_web_search_renders_each_result_with_its_title_snippet_and_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tavily(
        monkeypatch,
        {"results": [{"title": "F1 news", "content": "Something happened.", "url": "https://example.test/a"}]},
    )

    output = mcp_server.perform_web_search("f1 news")

    assert "Source: F1 news" in output
    assert "Snippet: Something happened." in output
    assert "URL: https://example.test/a" in output


def test_web_search_reports_an_empty_result_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tavily(monkeypatch, {"results": []})

    assert mcp_server.perform_web_search("obscure query") == "No search results found."


def test_web_search_returns_the_error_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_tavily(monkeypatch, RuntimeError("rate limited"))

    assert mcp_server.perform_web_search("q") == "Search failed: rate limited"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------
def test_health_check_reports_every_dependency_as_ok_when_all_are_reachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _install_schedule(monkeypatch, pd.DataFrame({"RoundNumber": [1]}))
    _install_ergast(monkeypatch, _FakeErgast(driver_standings=_ErgastResponse([])))
    _redirect_data_dir(monkeypatch, tmp_path, with_chroma=True)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    output = mcp_server.health_check()

    assert "FastF1 API: OK" in output
    assert "Ergast API: OK" in output
    assert "Rulebook DB: OK" in output
    assert "Web Search: OK" in output


def test_health_check_names_each_failing_dependency_rather_than_failing_as_a_whole(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A status probe that raises tells the operator nothing about what broke."""
    _install_schedule(monkeypatch, ConnectionError("fastf1 down"))
    _install_ergast(monkeypatch, _FakeErgast(driver_standings=ConnectionError("ergast down")))
    _redirect_data_dir(monkeypatch, tmp_path, with_chroma=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    output = mcp_server.health_check()

    assert "FastF1 API: ERROR (fastf1 down)" in output
    assert "Ergast API: ERROR (ergast down)" in output
    assert "Rulebook DB: NOT FOUND" in output
    assert "Web Search: NO API KEY" in output


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
async def test_every_documented_tool_is_registered_with_the_mcp_server() -> None:
    """The registry is the contract an MCP client discovers — pin the whole set."""
    registered = {tool.name for tool in await mcp_server.mcp.list_tools()}

    assert registered == {
        "get_season_schedule",
        "get_race_results",
        "get_qualifying_results",
        "get_sprint_results",
        "get_sprint_qualifying_results",
        "compare_drivers",
        "get_driver_standings",
        "get_constructor_standings",
        "consult_rulebook",
        "perform_web_search",
        "health_check",
    }
