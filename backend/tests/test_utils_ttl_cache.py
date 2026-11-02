"""Tests for the expiring cache (app.utils.ttl_cache)."""

from __future__ import annotations

import pytest

from app.utils.ttl_cache import TtlCache

pytestmark = pytest.mark.unit


@pytest.fixture
def clock():
    return {"now": 100.0}


def test_a_value_is_served_within_its_lifetime(clock):
    cache = TtlCache(clock=lambda: clock["now"])
    cache.put("race", "result", 60)
    clock["now"] += 59

    assert cache.get("race") == "result"


def test_a_value_is_forgotten_once_its_lifetime_passes(clock):
    cache = TtlCache(clock=lambda: clock["now"])
    cache.put("race", "result", 60)
    clock["now"] += 60

    assert cache.get("race") is None


def test_a_key_never_kept_is_a_miss():
    assert TtlCache().get("race") is None


def test_each_value_keeps_its_own_lifetime(clock):
    cache = TtlCache(clock=lambda: clock["now"])
    cache.put("found", "result", 600)
    cache.put("empty", "", 60)
    clock["now"] += 120

    assert (cache.get("found"), cache.get("empty")) == ("result", None)
