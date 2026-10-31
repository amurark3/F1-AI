"""Tests for app.data.openf1_stints: tyre stints from OpenF1.

OpenF1 became the primary stint source when F1's live-timing archive started
answering 401 without an F1 TV token, which left FastF1 with no lap data on
Render's always-cold cache. The risks asserted here are the ways OpenF1's shape
differs from FastF1's lap frame:

* **Red flags have no per-lap status.** A suspension is a race-control message
  stamped with the *leader's* lap, so a lapped car's free tyre change has to be
  placed from its own lap start times. Steward notes that merely mention a red
  flag ("... RED FLAG INFRINGEMENT") must not count.
* **Sessions are picked by name.** ``session_type`` is "Race" for a sprint too.
* **404 means "no rows", not an outage.** OpenF1 answers a filter that matches
  nothing with ``404 {"detail": "No results found."}``.

HTTP is served by ``httpx.MockTransport``; the network is blocked.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest

from app.data import openf1_stints as module
from app.data.openf1_stints import (
    OpenF1UnavailableError,
    laps_in_progress,
    openf1_race_stints,
    red_flag_moments,
    stints_from_openf1,
)

RED_FLAG_AT = datetime(2026, 9, 6, 13, 7, 43, tzinfo=UTC)
LEC, HAM = 16, 44
DRIVERS = {
    LEC: {"driver_number": LEC, "name_acronym": "LEC", "team_name": "Ferrari"},
    HAM: {"driver_number": HAM, "name_acronym": "HAM", "team_name": "Ferrari"},
}


def _stint_row(number: int, stint: int, start: int, end: int, compound="MEDIUM", age=0) -> dict:
    return {
        "driver_number": number,
        "stint_number": stint,
        "lap_start": start,
        "lap_end": end,
        "compound": compound,
        "tyre_age_at_start": age,
    }


def _message(text: str, flag: str | None = None, at: datetime = RED_FLAG_AT) -> dict:
    return {"date": at.isoformat(), "message": text, "flag": flag, "lap_number": 3}


def _lap(number: int, lap: int, start: str | None) -> dict:
    return {"driver_number": number, "lap_number": lap, "date_start": start}


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_red_flag_is_read_from_the_flag_field_used_up_to_2025():
    assert red_flag_moments([_message("RED FLAG", flag="RED")]) == (RED_FLAG_AT,)


@pytest.mark.unit
def test_a_red_flag_is_read_from_the_suspension_message_used_since_2026():
    # 2026 sends no flag value, only the message (Monza, Zandvoort, Monaco).
    assert red_flag_moments([_message("RED FLAG - RACE SUSPENDED")]) == (RED_FLAG_AT,)


@pytest.mark.unit
def test_steward_notes_and_aborted_starts_are_not_red_flags():
    notes = [
        _message("INCIDENT INVOLVING CAR 6 (HAD) NOTED - RED FLAG INFRINGEMENT"),
        _message("ABORTED START"),
        _message("CHEQUERED FLAG", flag="CHEQUERED"),
    ]

    assert red_flag_moments(notes) == ()


@pytest.mark.unit
def test_an_undated_red_flag_cannot_be_placed_and_is_skipped():
    assert red_flag_moments([{"message": "RED FLAG", "flag": "RED", "date": None}]) == ()


@pytest.mark.unit
def test_a_lapped_car_is_placed_on_its_own_lap_not_the_leaders():
    laps = [
        _lap(LEC, 67, "2026-09-06T13:05:00+00:00"),
        _lap(LEC, 68, "2026-09-06T13:06:15+00:00"),
        # A lap down: still on lap 66 when the flag came out.
        _lap(HAM, 66, "2026-09-06T13:06:30+00:00"),
        _lap(HAM, 67, "2026-09-06T13:08:00+00:00"),
    ]

    assert laps_in_progress(laps, (RED_FLAG_AT,)) == {LEC: frozenset({68}), HAM: frozenset({66})}


@pytest.mark.unit
def test_a_flag_before_any_timed_lap_start_falls_on_lap_one():
    # OpenF1 leaves lap 1's start undated, and lap 1 red flags happen (Suzuka 2024).
    laps = [_lap(LEC, 1, None), _lap(LEC, 2, "2026-09-06T13:09:00+00:00")]

    assert laps_in_progress(laps, (RED_FLAG_AT,)) == {LEC: frozenset({1})}


@pytest.mark.unit
def test_lap_rows_missing_a_driver_or_lap_number_are_ignored():
    laps = [{"driver_number": None, "lap_number": 3, "date_start": "2026-09-06T13:05:00+00:00"}]

    assert laps_in_progress(laps, (RED_FLAG_AT,)) == {}


# ---------------------------------------------------------------------------
# Building stints
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_stint_row_becomes_a_stint_with_the_drivers_code_and_team():
    (stint,) = stints_from_openf1([_stint_row(LEC, 1, 4, 28, "HARD", age=0)], DRIVERS, {})

    assert stint.driver_code == "LEC"
    assert stint.team == "Ferrari"
    assert (stint.stint, stint.compound, stint.start_lap, stint.end_lap, stint.laps) == (1, "HARD", 4, 28, 25)
    assert (stint.tyre_life_start, stint.fresh, stint.ended_under_red_flag) == (0, True, False)


@pytest.mark.unit
def test_a_set_with_laps_on_it_is_scrubbed_not_fresh():
    (stint,) = stints_from_openf1([_stint_row(LEC, 1, 1, 20, age=3)], DRIVERS, {})

    assert (stint.tyre_life_start, stint.fresh) == (3, False)


@pytest.mark.unit
def test_an_unrecorded_tyre_age_is_unknown_rather_than_new():
    (stint,) = stints_from_openf1([_stint_row(LEC, 1, 1, 20, age=None)], DRIVERS, {})

    assert (stint.tyre_life_start, stint.fresh) == (None, None)


@pytest.mark.unit
def test_an_unknown_compound_is_null_rather_than_a_label():
    (stint,) = stints_from_openf1([_stint_row(LEC, 1, 1, 20, compound="UNKNOWN")], DRIVERS, {})

    assert stint.compound is None


@pytest.mark.unit
def test_a_stint_ending_on_the_cars_red_flag_lap_is_marked():
    rows = [_stint_row(LEC, 1, 1, 3), _stint_row(LEC, 2, 4, 53), _stint_row(HAM, 1, 1, 2)]

    stints = stints_from_openf1(rows, DRIVERS, {LEC: frozenset({3}), HAM: frozenset({2})})

    assert [(s.driver_code, s.stint, s.ended_under_red_flag) for s in stints] == [
        ("HAM", 1, True),
        ("LEC", 1, True),
        ("LEC", 2, False),
    ]


@pytest.mark.unit
def test_a_pit_lane_pass_on_the_same_set_is_one_stint():
    # OpenF1 opens a stint on every pit-lane pass. "All cars through the pit
    # lane" under a safety car split 15 drivers at R15 2026 without a tyre
    # changing: the next "stint" carries on the same compound at the age the
    # last one reached.
    rows = [_stint_row(LEC, 1, 1, 35, "MEDIUM", age=0), _stint_row(LEC, 2, 36, 50, "MEDIUM", age=35)]

    (stint,) = stints_from_openf1(rows, DRIVERS, {LEC: frozenset({35})})

    assert (stint.stint, stint.start_lap, stint.end_lap, stint.laps, stint.tyre_life_start) == (1, 1, 50, 50, 0)
    assert stint.ended_under_red_flag is False, "keeping the set through a red flag changed nothing"


@pytest.mark.unit
def test_stints_are_renumbered_after_a_merge():
    rows = [
        _stint_row(LEC, 1, 1, 10, "MEDIUM", age=0),
        _stint_row(LEC, 2, 11, 20, "MEDIUM", age=10),
        _stint_row(LEC, 3, 21, 50, "HARD", age=0),
    ]

    assert [(s.stint, s.compound) for s in stints_from_openf1(rows, DRIVERS, {})] == [(1, "MEDIUM"), (2, "HARD")]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("compound", "age"),
    [("MEDIUM", 0), ("HARD", 35), ("MEDIUM", None)],
    ids=["fresh-set-same-compound", "other-compound", "unrecorded-age"],
)
def test_a_real_or_unprovable_tyre_change_stays_a_new_stint(compound, age):
    rows = [_stint_row(LEC, 1, 1, 35, "MEDIUM", age=0), _stint_row(LEC, 2, 36, 50, compound, age=age)]

    assert len(stints_from_openf1(rows, DRIVERS, {})) == 2


@pytest.mark.unit
def test_rows_missing_a_lap_range_are_skipped():
    rows = [{**_stint_row(LEC, 1, 1, 20), "lap_end": None}, _stint_row(HAM, 1, 1, 20)]

    assert [s.driver_code for s in stints_from_openf1(rows, DRIVERS, {})] == ["HAM"]


@pytest.mark.unit
def test_a_driver_missing_from_the_entry_list_keeps_their_number():
    (stint,) = stints_from_openf1([_stint_row(99, 1, 1, 20)], DRIVERS, {})

    assert (stint.driver_code, stint.team) == ("99", "")


# ---------------------------------------------------------------------------
# The OpenF1 boundary
# ---------------------------------------------------------------------------

MEETINGS = [
    {"meeting_key": 1292, "location": "Zandvoort", "date_start": "2026-08-21T10:30:00+00:00"},
    {"meeting_key": 1293, "location": "Monza", "date_start": "2026-09-04T10:30:00+00:00"},
]
SESSIONS = [
    {"session_key": 11355, "session_name": "Sprint", "session_type": "Race"},
    {"session_key": 11361, "session_name": "Race", "session_type": "Race"},
]


class FakeOpenF1:
    """Serves OpenF1 paths from a dict and records what was asked for.

    A route is the JSON rows to serve, a fixed response, or a function of the
    request for a route whose answer changes between calls.
    """

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path.removeprefix("/v1/"))
        if route is None:
            return httpx.Response(404, json={"detail": "No results found."})
        if callable(route):
            return route(request)
        return route if isinstance(route, httpx.Response) else httpx.Response(200, json=route)

    def paths(self) -> list[str]:
        return [request.url.path.removeprefix("/v1/") for request in self.requests]


@pytest.fixture
def openf1(monkeypatch):
    """Wire the module to a fake OpenF1 and a Monza 2026 calendar entry."""

    def install(routes: dict) -> FakeOpenF1:
        fake = FakeOpenF1(routes)
        monkeypatch.setattr(module, "_new_client", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
        return fake

    schedule = pd.DataFrame([{"RoundNumber": 13, "Location": "Monza", "EventDate": pd.Timestamp("2026-09-06")}])
    monkeypatch.setattr(module.fastf1, "get_event_schedule", lambda *_args, **_kwargs: schedule)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return install


def _monza(**overrides) -> dict:
    routes = {
        "meetings": MEETINGS,
        "sessions": SESSIONS,
        "stints": [_stint_row(LEC, 1, 1, 3), _stint_row(LEC, 2, 4, 53)],
        "drivers": list(DRIVERS.values()),
        "race_control": [],
    }
    return {**routes, **overrides}


@pytest.mark.unit
def test_the_race_is_found_by_circuit_and_session_name_not_the_sprint(openf1):
    fake = openf1(_monza())

    stints = openf1_race_stints(2026, 13)

    assert [(s.driver_code, s.stint) for s in stints] == [("LEC", 1), ("LEC", 2)]
    stint_request = next(r for r in fake.requests if r.url.path.endswith("/stints"))
    assert stint_request.url.params["session_key"] == "11361"


@pytest.mark.unit
def test_lap_timings_are_fetched_only_when_the_race_was_red_flagged(openf1):
    quiet = openf1(_monza())
    openf1_race_stints(2026, 13)
    assert "laps" not in quiet.paths()

    flagged = openf1(
        _monza(
            race_control=[_message("RED FLAG - RACE SUSPENDED")],
            laps=[_lap(LEC, 3, "2026-09-06T13:06:00+00:00"), _lap(LEC, 4, "2026-09-06T13:40:00+00:00")],
        )
    )
    stints = openf1_race_stints(2026, 13)

    assert "laps" in flagged.paths()
    assert [s.ended_under_red_flag for s in stints] == [True, False]


@pytest.mark.unit
def test_a_race_not_yet_run_has_no_stints(openf1):
    openf1(_monza(stints=httpx.Response(404, json={"detail": "No results found."})))

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_stints_without_an_entry_list_are_refused_rather_than_shown_by_number(openf1):
    # Persisted, a numbers-only answer would outlive the gap that caused it.
    openf1(_monza(drivers=httpx.Response(404, json={"detail": "No results found."})))

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_a_round_missing_from_the_calendar_has_no_stints(openf1):
    fake = openf1(_monza())

    assert openf1_race_stints(2026, 99) == ()
    assert fake.requests == []


@pytest.mark.unit
def test_an_unmatched_meeting_has_no_stints(openf1):
    openf1(_monza(meetings=[{"meeting_key": 1, "location": "Imola", "date_start": "2026-05-17T10:00:00+00:00"}]))

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_a_weekend_without_a_race_session_has_no_stints(openf1):
    openf1(_monza(sessions=[SESSIONS[0]]))

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_a_refusal_during_a_live_session_is_no_stints_not_a_crash(openf1):
    refusal = httpx.Response(401, json={"detail": "Live F1 session in progress, restricted to authenticated users"})
    openf1(_monza(stints=refusal))

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_a_failing_calendar_lookup_is_no_stints(openf1, monkeypatch):
    def broken(*_args, **_kwargs):
        raise ValueError("schedule backend down")

    openf1(_monza())
    monkeypatch.setattr(module.fastf1, "get_event_schedule", broken)

    assert openf1_race_stints(2026, 13) == ()


@pytest.mark.unit
def test_a_rate_limited_request_is_retried_after_the_advertised_wait(openf1, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", waits.append)
    answers = iter([httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, json=MEETINGS)])
    openf1(_monza(meetings=lambda _request: next(answers)))

    assert len(openf1_race_stints(2026, 13)) == 2
    assert waits == [3.0]


# ---------------------------------------------------------------------------
# One request
# ---------------------------------------------------------------------------


def _get(handler) -> list[dict]:
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return module._get_json(client, "stints", {"session_key": 1})


@pytest.mark.unit
def test_a_request_that_stays_rate_limited_gives_up(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(module.time, "sleep", waits.append)

    with pytest.raises(OpenF1UnavailableError, match="rate limited"):
        _get(lambda request: httpx.Response(429))

    assert waits == [module.DEFAULT_RETRY_AFTER_SECONDS] * module.RATE_LIMIT_ATTEMPTS


@pytest.mark.unit
@pytest.mark.parametrize(("header", "expected"), [("120", 10.0), ("soon", 2.0), ("-4", 0.0)])
def test_the_advertised_wait_is_bounded(header, expected):
    assert module._retry_after(httpx.Response(429, headers={"retry-after": header})) == expected


@pytest.mark.unit
def test_an_unreachable_openf1_is_unavailable():
    def refuse(request):
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(OpenF1UnavailableError, match="unreachable"):
        _get(refuse)


@pytest.mark.unit
def test_a_server_error_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="HTTP 503"):
        _get(lambda request: httpx.Response(503))


@pytest.mark.unit
def test_a_page_that_is_not_json_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="not JSON"):
        _get(lambda request: httpx.Response(200, content=b"<html>maintenance</html>"))


@pytest.mark.unit
def test_an_object_where_a_list_belongs_is_unavailable():
    with pytest.raises(OpenF1UnavailableError, match="detail"):
        _get(lambda request: httpx.Response(200, json={"detail": "restricted"}))


@pytest.mark.unit
def test_the_default_client_carries_the_configured_timeout():
    with module._new_client() as client:
        assert client.timeout.read == module.OPENF1_HTTP_TIMEOUT_SECONDS
