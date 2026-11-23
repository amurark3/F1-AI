"""Tests for app.api.rate_limit: the per-visitor request cap and whose address it counts."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.api.rate_limit import RateLimiter, client_ip

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_each_window_caps_its_own_count_and_frees_up_as_hits_age_out():
    clock = _Clock()
    limiter = RateLimiter(((2, 60.0), (3, 3600.0)), clock=clock)

    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    clock.now = 61.0
    assert limiter.allow("a") is True, "the minute window has room again"
    assert limiter.allow("a") is False, "but the hour window is full"
    clock.now = 3700.0
    assert limiter.allow("a") is True, "every hit has aged out"


def test_visitors_are_counted_apart():
    limiter = RateLimiter(((1, 60.0),), clock=_Clock())

    assert (limiter.allow("a"), limiter.allow("b"), limiter.allow("a")) == (True, True, False)


def _request(headers: dict[str, str], client: tuple[str, int] | None = ("10.0.0.9", 1234)) -> Request:
    raw = [(name.encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw, "client": client})


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"true-client-ip": " 198.51.100.7 ", "cf-connecting-ip": "198.51.100.8"}, "198.51.100.7"),
        ({"cf-connecting-ip": "198.51.100.8"}, "198.51.100.8"),
        # X-Forwarded-For is only appended to on Render, so a client can forge it: never read.
        ({"x-forwarded-for": "1.2.3.4"}, "10.0.0.9"),
    ],
    ids=["true-client-ip", "cf-connecting-ip", "forged-xff"],
)
def test_the_edge_header_names_the_visitor(headers, expected):
    assert client_ip(_request(headers)) == expected


def test_a_request_with_no_peer_still_gets_a_key():
    assert client_ip(_request({}, client=None)) == "unknown"
