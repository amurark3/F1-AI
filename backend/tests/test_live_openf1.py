"""Tests for app.api.live.openf1 — the unauthenticated third-party live feed.

OpenF1 is a free, best-effort endpoint polled every few seconds from inside a
WebSocket loop, so its failure modes are the whole risk surface:

* **A bad feed must never reach the socket.** Timeouts, 5xx bodies, HTML error
  pages and half-written JSON all have to come back as ``None``, ``0`` or an
  empty mapping — anything that raises would propagate into ``live_timing`` and
  drop every client in the room.
* **Driver metadata is cached per session in a process global.** A failed fetch
  must not be cached as an empty roster, or the room shows bare car numbers for
  the rest of the race.
* **Partial data is still useful.** A missing intervals feed degrades the gap
  column alone; it does not cost the running order.

Every request is answered by a scripted ``httpx.AsyncClient``; conftest blocks
real sockets, so an unmocked call fails loudly rather than reaching the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json

import httpx
import pytest

from app.api.live import openf1

SESSION_KEY = "9999"


class _FakeResponse:
    """A scripted HTTP answer.

    ``payload`` may be an exception, which ``json()`` raises — that is how a
    truncated or non-JSON body (an nginx error page, say) behaves.
    """

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise httpx.HTTPStatusError(
                f"server error {self.status_code}",
                request=httpx.Request("GET", "https://api.openf1.org/v1/"),
                response=httpx.Response(self.status_code),
            )


@dataclass
class _Boundary:
    """What the module asked the network for."""

    calls: list[dict] = field(default_factory=list)
    client_kwargs: list[dict] = field(default_factory=list)


def _install_client(monkeypatch, *responses):
    """Replay ``responses`` in request order through a fake ``AsyncClient``.

    An ``Exception`` in the queue is raised instead of returned, which is how a
    transport failure (timeout, connection reset) arrives.
    """
    boundary = _Boundary()
    queue = list(responses)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, url, params=None):
            boundary.calls.append({"url": url, "params": params})
            nxt = queue.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

    def _factory(*_args, **kwargs):
        boundary.client_kwargs.append(kwargs)
        return _Client()

    monkeypatch.setattr(openf1.httpx, "AsyncClient", _factory)
    return boundary


def _malformed_body():
    return json.JSONDecodeError("Expecting value", "<html>502 Bad Gateway</html>", 0)


DRIVERS_OK = _FakeResponse(
    200,
    [
        {"driver_number": 1, "name_acronym": "VER"},
        {"driver_number": 4, "name_acronym": "NOR"},
    ],
)


@pytest.fixture(autouse=True)
def _clear_driver_cache():
    """The roster cache is a process global that outlives a single session."""
    openf1._driver_cache.clear()
    yield
    openf1._driver_cache.clear()


# ---------------------------------------------------------------------------
# _cached_drivers
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_the_driver_roster_is_fetched_once_per_session(monkeypatch):
    boundary = _install_client(monkeypatch, DRIVERS_OK)

    async with openf1.httpx.AsyncClient() as client:
        first = await openf1._cached_drivers(client, SESSION_KEY)
        second = await openf1._cached_drivers(client, SESSION_KEY)

    assert first[1]["name_acronym"] == "VER"
    assert second is first
    assert len(boundary.calls) == 1, "a second poll must not re-fetch the roster"
    assert boundary.calls[0]["params"] == {"session_key": SESSION_KEY}


@pytest.mark.unit
async def test_a_failed_roster_fetch_is_retried_rather_than_cached_empty(monkeypatch):
    _install_client(monkeypatch, _FakeResponse(503, {"error": "unavailable"}), DRIVERS_OK)

    async with openf1.httpx.AsyncClient() as client:
        failed = await openf1._cached_drivers(client, SESSION_KEY)
        recovered = await openf1._cached_drivers(client, SESSION_KEY)

    assert failed == {}
    assert set(recovered) == {1, 4}


@pytest.mark.unit
async def test_a_non_list_roster_body_is_ignored(monkeypatch):
    """OpenF1 answers errors with a JSON object, not the documented array."""
    _install_client(monkeypatch, _FakeResponse(200, {"detail": "rate limited"}))

    async with openf1.httpx.AsyncClient() as client:
        assert await openf1._cached_drivers(client, SESSION_KEY) == {}


@pytest.mark.unit
async def test_roster_entries_without_a_car_number_are_dropped(monkeypatch):
    _install_client(monkeypatch, _FakeResponse(200, [{"name_acronym": "TBD"}, {"driver_number": 1}]))

    async with openf1.httpx.AsyncClient() as client:
        assert await openf1._cached_drivers(client, SESSION_KEY) == {1: {"driver_number": 1}}


# ---------------------------------------------------------------------------
# _latest_by_driver / _format_gap
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_last_entry_for_a_driver_wins():
    """The endpoints are append-only logs, so recency is the only ordering."""
    payload = [
        {"driver_number": 1, "position": 2},
        {"driver_number": 4, "position": 3},
        {"driver_number": 1, "position": 1},
    ]

    assert openf1._latest_by_driver(payload) == {
        1: {"driver_number": 1, "position": 1},
        4: {"driver_number": 4, "position": 3},
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [{"detail": "not found"}, None, "unavailable"],
    ids=["object", "null", "string"],
)
def test_a_non_list_log_indexes_to_nothing(payload):
    assert openf1._latest_by_driver(payload) == {}


@pytest.mark.unit
def test_log_entries_without_a_car_number_are_skipped():
    assert openf1._latest_by_driver([{"position": 1}, {"driver_number": None, "position": 2}]) == {}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("position", "interval", "expected"),
    [
        (1, {"gap_to_leader": 0.0}, "LEADER"),
        (1, {}, "LEADER"),
        (2, {"gap_to_leader": 0.0}, "LEADER"),
        (2, {"gap_to_leader": 1.2345}, "+1.234"),
        (2, {"gap_to_leader": "3.5"}, "+3.500"),
        (2, {"gap_to_leader": None}, "—"),
        (2, {}, "—"),
        (2, {"gap_to_leader": "1 LAP"}, "—"),
        (2, {"gap_to_leader": []}, "—"),
    ],
    ids=[
        "leader-zero-gap",
        "leader-no-interval-row",
        "lapped-field-collapsed-to-zero",
        "rounded-to-milliseconds",
        "numeric-string",
        "explicit-null",
        "missing-key",
        "lapped-marker",
        "wrong-type",
    ],
)
def test_the_gap_column_renders_or_degrades(position, interval, expected):
    assert openf1._format_gap(position, interval) == expected


# ---------------------------------------------------------------------------
# _poll_openf1_positions
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_positions_are_returned_in_running_order_with_names_and_gaps(monkeypatch):
    _install_client(
        monkeypatch,
        DRIVERS_OK,
        _FakeResponse(200, [{"driver_number": 4, "position": 2}, {"driver_number": 1, "position": 1}]),
        _FakeResponse(
            200,
            [{"driver_number": 1, "gap_to_leader": 0.0}, {"driver_number": 4, "gap_to_leader": 2.5}],
        ),
    )

    rows = await openf1._poll_openf1_positions(SESSION_KEY)

    assert [(row["position"], row["driver"], row["gap"]) for row in rows] == [
        (1, "VER", "LEADER"),
        (2, "NOR", "+2.500"),
    ]
    # The positions feed carries no timing or tyre data; those columns are the
    # client's cue to render a placeholder rather than a stale value.
    assert rows[0]["last_lap"] is None
    assert rows[0]["sector1"] is None
    assert rows[0]["tyre"] is None
    assert rows[0]["pit_stops"] is None


@pytest.mark.unit
async def test_a_driver_missing_from_the_roster_falls_back_to_the_car_number(monkeypatch):
    _install_client(
        monkeypatch,
        _FakeResponse(200, []),
        _FakeResponse(200, [{"driver_number": 81, "position": 1}]),
        _FakeResponse(200, []),
    )

    rows = await openf1._poll_openf1_positions(SESSION_KEY)

    assert rows == [
        {
            "position": 1,
            "driver": "81",
            "gap": "LEADER",
            "last_lap": None,
            "sector1": None,
            "sector2": None,
            "sector3": None,
            "tyre": None,
            "pit_stops": None,
        }
    ]


@pytest.mark.unit
async def test_a_lost_intervals_feed_costs_the_gaps_but_not_the_order(monkeypatch):
    _install_client(
        monkeypatch,
        DRIVERS_OK,
        _FakeResponse(200, [{"driver_number": 1, "position": 1}, {"driver_number": 4, "position": 2}]),
        _FakeResponse(500, {"error": "boom"}),
    )

    rows = await openf1._poll_openf1_positions(SESSION_KEY)

    assert [row["driver"] for row in rows] == ["VER", "NOR"]
    assert [row["gap"] for row in rows] == ["LEADER", "—"]


@pytest.mark.unit
async def test_an_entry_without_a_position_sorts_last(monkeypatch):
    """A car with no reported position must not displace the classified field."""
    _install_client(
        monkeypatch,
        DRIVERS_OK,
        _FakeResponse(200, [{"driver_number": 4}, {"driver_number": 1, "position": 1}]),
        _FakeResponse(200, []),
    )

    rows = await openf1._poll_openf1_positions(SESSION_KEY)

    assert [(row["driver"], row["position"]) for row in rows] == [("VER", 1), ("NOR", 0)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("positions_response", "reason"),
    [
        (_FakeResponse(503, None), "upstream-unavailable"),
        (_FakeResponse(200, []), "session-not-live"),
        (_FakeResponse(200, {"detail": "no data"}), "object-instead-of-array"),
        (_FakeResponse(200, _malformed_body()), "truncated-body"),
    ],
    ids=["upstream-unavailable", "session-not-live", "object-instead-of-array", "truncated-body"],
)
async def test_an_unusable_positions_feed_yields_no_update(monkeypatch, positions_response, reason):
    _install_client(monkeypatch, DRIVERS_OK, positions_response, _FakeResponse(200, []))

    assert await openf1._poll_openf1_positions(SESSION_KEY) is None, reason


@pytest.mark.unit
async def test_a_transport_timeout_yields_no_update(monkeypatch):
    _install_client(monkeypatch, httpx.TimeoutException("timed out"))

    assert await openf1._poll_openf1_positions(SESSION_KEY) is None


@pytest.mark.unit
async def test_the_polling_client_is_given_a_timeout(monkeypatch):
    """An untimed request inside the poll loop would wedge the room forever."""
    boundary = _install_client(monkeypatch, DRIVERS_OK, _FakeResponse(200, []), _FakeResponse(200, []))

    await openf1._poll_openf1_positions(SESSION_KEY)

    assert boundary.client_kwargs[0]["timeout"] == openf1.OPENF1_HTTP_TIMEOUT_SECONDS


@pytest.mark.unit
async def test_a_poll_failure_is_logged_with_its_cause(monkeypatch, capsys):
    _install_client(monkeypatch, httpx.ConnectError("name resolution failed"))

    await openf1._poll_openf1_positions(SESSION_KEY)

    logged = capsys.readouterr().out
    assert "openf1.poll_error" in logged
    assert "name resolution failed" in logged


# ---------------------------------------------------------------------------
# _fetch_current_lap
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_the_current_lap_is_the_furthest_car_on_track(monkeypatch):
    _install_client(
        monkeypatch,
        _FakeResponse(
            200,
            [
                {"driver_number": 1, "lap_number": 31},
                {"driver_number": 4, "lap_number": 32},
                {"driver_number": 81, "lap_number": 30},
            ],
        ),
    )

    assert await openf1._fetch_current_lap(SESSION_KEY) == 32


@pytest.mark.unit
@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(404, None),
        _FakeResponse(200, []),
        _FakeResponse(200, [{"driver_number": 1}, {"driver_number": 4, "lap_number": 0}]),
        _FakeResponse(200, _malformed_body()),
        httpx.TimeoutException("timed out"),
    ],
    ids=["not-found", "no-laps-yet", "laps-not-started", "truncated-body", "timeout"],
)
async def test_an_unusable_lap_feed_reads_as_lap_zero(monkeypatch, response):
    """Zero is the endpoint's cue to keep showing the last known lap."""
    _install_client(monkeypatch, response)

    assert await openf1._fetch_current_lap(SESSION_KEY) == 0


# ---------------------------------------------------------------------------
# _find_openf1_session
# ---------------------------------------------------------------------------

MEETINGS_OK = _FakeResponse(
    200,
    [
        {"meeting_key": 200, "meeting_name": "Bahrain Grand Prix", "date_start": "2026-03-08"},
        {"meeting_key": 100, "meeting_name": "Pre-Season Testing", "date_start": "2026-02-20"},
        {"meeting_key": 300, "meeting_name": "Saudi Arabian Grand Prix", "date_start": "2026-03-15"},
    ],
)


@pytest.mark.unit
async def test_a_round_resolves_to_its_race_session_and_distance(monkeypatch):
    boundary = _install_client(
        monkeypatch,
        MEETINGS_OK,
        _FakeResponse(200, [{"session_key": 9876, "total_laps": 50}]),
    )

    assert await openf1._find_openf1_session(2026, 2) == ("9876", 50)
    # Round 2 is the second *race*: testing is excluded and the rest sorted by date.
    assert boundary.calls[1]["params"] == {"meeting_key": 300, "session_type": "Race"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("session", "expected_laps"),
    [
        ({"session_key": 1, "total_laps": 44}, 44),
        ({"session_key": 1, "laps": 44}, 44),
        ({"session_key": 1, "number_of_laps": 44}, 44),
        ({"session_key": 1}, 0),
        ({"session_key": 1, "total_laps": None, "laps": 0, "number_of_laps": 57}, 57),
    ],
    ids=["total_laps", "laps", "number_of_laps", "unknown", "first-truthy-wins"],
)
async def test_race_distance_is_read_from_whichever_field_openf1_supplies(monkeypatch, session, expected_laps):
    _install_client(monkeypatch, MEETINGS_OK, _FakeResponse(200, [session]))

    assert await openf1._find_openf1_session(2026, 1) == ("1", expected_laps)


@pytest.mark.unit
async def test_sessions_without_a_key_are_skipped_until_one_has_it(monkeypatch):
    _install_client(
        monkeypatch,
        MEETINGS_OK,
        _FakeResponse(200, [{"session_name": "Race"}, {"session_key": 4242, "total_laps": 70}]),
    )

    assert await openf1._find_openf1_session(2026, 1) == ("4242", 70)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("round_num", "reason"),
    [(0, "rounds are one-based"), (-1, "negative round"), (3, "beyond the calendar")],
    ids=["zero", "negative", "past-the-end"],
)
async def test_a_round_outside_the_calendar_resolves_to_nothing(monkeypatch, round_num, reason):
    boundary = _install_client(monkeypatch, MEETINGS_OK)

    assert await openf1._find_openf1_session(2026, round_num) is None, reason
    assert len(boundary.calls) == 1, "an impossible round must not trigger a session lookup"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("responses", "reason"),
    [
        ((_FakeResponse(500, None),), "meetings endpoint down"),
        ((_FakeResponse(200, _malformed_body()),), "meetings body truncated"),
        ((httpx.TimeoutException("timed out"),), "meetings timed out"),
        (
            (_FakeResponse(200, [{"meeting_name": "Bahrain Grand Prix", "date_start": "2026-03-08"}]),),
            "meeting has no key",
        ),
        ((MEETINGS_OK, _FakeResponse(502, None)), "sessions endpoint down"),
        ((MEETINGS_OK, _FakeResponse(200, [])), "race session not published yet"),
    ],
    ids=[
        "meetings-down",
        "meetings-malformed",
        "meetings-timeout",
        "meeting-key-missing",
        "sessions-down",
        "no-race-session",
    ],
)
async def test_an_unresolvable_session_yields_none(monkeypatch, responses, reason):
    _install_client(monkeypatch, *responses)

    assert await openf1._find_openf1_session(2026, 1) is None, reason


@pytest.mark.unit
async def test_a_session_lookup_failure_is_logged(monkeypatch, capsys):
    _install_client(monkeypatch, httpx.ConnectError("dns failure"))

    await openf1._find_openf1_session(2026, 1)

    assert "openf1.session_lookup_error" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _fetch_session_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([{"message": "SAFETY CAR DEPLOYED"}], "safety car"),
        ([{"flag": "SAFETY CAR"}], "safety car"),
        ([{"message": "VSC DEPLOYED", "flag": "VIRTUAL SAFETY CAR"}], "vsc"),
        ([{"message": "RED FLAG"}], "red flag"),
        ([{"flag": "RED"}], "red flag"),
        ([{"message": "GREEN LIGHT - PIT EXIT OPEN"}], ""),
        ([{"message": None, "flag": None}], ""),
        ([], ""),
        ([{"message": "SAFETY CAR DEPLOYED"}, {"flag": "CLEAR"}], ""),
    ],
    ids=[
        "safety-car-message",
        "safety-car-flag",
        "vsc-flag",
        "red-flag-message",
        "red-flag-flag",
        "green-flag",
        "null-fields",
        "no-messages",
        "latest-message-wins",
    ],
)
async def test_race_control_is_normalised_to_a_status(monkeypatch, messages, expected):
    _install_client(monkeypatch, _FakeResponse(200, messages))

    assert await openf1._fetch_session_status(9999) == expected


@pytest.mark.unit
async def test_a_virtual_safety_car_message_is_reported_as_a_full_safety_car(monkeypatch):
    """Pins current behaviour, which is wrong — see the note in the report.

    ``"safety car" in msg`` matches inside ``"virtual safety car"``, so the VSC
    branch below it is unreachable for message text; only the ``flag`` field can
    still reach it.
    """
    _install_client(monkeypatch, _FakeResponse(200, [{"message": "VIRTUAL SAFETY CAR DEPLOYED"}]))

    assert await openf1._fetch_session_status(9999) == "safety car"


@pytest.mark.unit
@pytest.mark.parametrize(
    "response",
    [_FakeResponse(503, None), _FakeResponse(200, _malformed_body()), httpx.TimeoutException("timed out")],
    ids=["upstream-down", "truncated-body", "timeout"],
)
async def test_an_unreadable_race_control_feed_reports_no_interruption(monkeypatch, response):
    _install_client(monkeypatch, response)

    assert await openf1._fetch_session_status(9999) == ""


@pytest.mark.unit
async def test_a_race_control_failure_is_logged(monkeypatch, capsys):
    _install_client(monkeypatch, httpx.ReadTimeout("read timed out"))

    await openf1._fetch_session_status(9999)

    assert "commentary.race_control_fetch_error" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _fetch_stint_counts
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_stint_counts_keep_the_highest_stint_per_driver(monkeypatch):
    """Stints arrive in log order, but an out-of-order entry must not rewind."""
    _install_client(
        monkeypatch,
        _FakeResponse(
            200,
            [
                {"driver_number": 1, "stint_number": 1},
                {"driver_number": 1, "stint_number": 3},
                {"driver_number": 1, "stint_number": 2},
                {"driver_number": 4},
            ],
        ),
    )

    assert await openf1._fetch_stint_counts(9999) == {"1": 3, "4": 1}


@pytest.mark.unit
async def test_stints_without_a_car_number_are_dropped(monkeypatch):
    _install_client(monkeypatch, _FakeResponse(200, [{"stint_number": 2}, {"driver_number": 44, "stint_number": 2}]))

    assert await openf1._fetch_stint_counts(9999) == {"44": 2}


@pytest.mark.unit
@pytest.mark.parametrize(
    "response",
    [_FakeResponse(500, None), _FakeResponse(200, _malformed_body()), httpx.TimeoutException("timed out")],
    ids=["upstream-down", "truncated-body", "timeout"],
)
async def test_an_unreadable_stint_feed_reports_no_pit_stops(monkeypatch, response):
    _install_client(monkeypatch, response)

    assert await openf1._fetch_stint_counts(9999) == {}


@pytest.mark.unit
async def test_a_stint_failure_is_logged(monkeypatch, capsys):
    _install_client(monkeypatch, httpx.ConnectError("connection refused"))

    await openf1._fetch_stint_counts(9999)

    assert "commentary.stints_fetch_error" in capsys.readouterr().out
