"""Shared builders for the Telemetry Lab tests: a fake OpenF1, a fresh cache, laps and sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.data.analysis_cache import AnalysisCache
from app.data.openf1.laps import Lap
from app.data.openf1.session_laps import SessionLaps
from app.data.openf1.sessions import EntryDriver, OpenF1Session

T0 = datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
NOR = EntryDriver(number=1, code="NOR", name="Lando Norris", team="McLaren", colour="#F47600")
VER = EntryDriver(number=3, code="VER", name="Max Verstappen", team="Red Bull Racing", colour="#4781D7")
NO_RESULTS = {"detail": "No results found."}


class FakeOpenF1:
    """Serves OpenF1 paths from a dict and records what was asked for.

    A route is the JSON rows to serve, a fixed response, or a function of the
    request. A path with no route answers OpenF1's 404 "No results found."
    """

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path.removeprefix("/v1/"))
        if route is None:
            return httpx.Response(404, json=NO_RESULTS)
        if callable(route):
            return route(request)
        return route if isinstance(route, httpx.Response) else httpx.Response(200, json=route)

    def paths(self) -> list[str]:
        return [request.url.path.removeprefix("/v1/") for request in self.requests]


def serve(monkeypatch, module, routes: dict) -> FakeOpenF1:
    """Point ``module.new_client`` at a fake OpenF1 serving ``routes``."""
    fake = FakeOpenF1(routes)
    monkeypatch.setattr(module, "new_client", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    return fake


def fresh_cache(monkeypatch, *modules) -> AnalysisCache:
    """One empty in-memory cache, installed as ``analysis_cache`` in every given module."""
    cache = AnalysisCache(None, 16)
    for module in modules:
        monkeypatch.setattr(module, "analysis_cache", cache)
    return cache


def make_lap(driver: int, number: int, *, start: float | None = None, time: float | None = None, **extra) -> Lap:
    """A lap starting ``start`` seconds after :data:`T0`."""
    return Lap(
        driver=driver,
        number=number,
        start=None if start is None else T0 + timedelta(seconds=start),
        time=time,
        sectors=extra.get("sectors", (None, None, None)),
        traps=extra.get("traps", (None, None, None)),
        pit_out=extra.get("pit_out", False),
        deleted=extra.get("deleted", False),
    )


def make_session(code: str = "Q", *, ended: bool = True, circuit_key: int | None = 9) -> OpenF1Session:
    end = datetime(2020, 1, 1, tzinfo=UTC) if ended else datetime(2999, 1, 1, tzinfo=UTC)
    return OpenF1Session(
        session_key=11392,
        meeting_key=1297,
        circuit_key=circuit_key,
        code=code,
        name="Qualifying" if code == "Q" else "Race",
        date_start=T0,
        date_end=end,
    )


def make_session_laps(
    laps: tuple[Lap, ...], *, code: str = "Q", windows: tuple = (), drivers=(NOR, VER)
) -> SessionLaps:
    return SessionLaps(
        session=make_session(code),
        year=2026,
        round=18,
        drivers={driver.number: driver for driver in drivers},
        laps=laps,
        windows=windows,
    )


def iso(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()
