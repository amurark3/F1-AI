"""Tests for the app.services.race_control package facade.

The package exists so the router can keep importing from one place while the
feature blocks (live, weather, risk, workstreams, strategy context) are split
across files.
The risk it carries is a silent contract break: a re-export that drifts away
from the implementation, or an ``__all__`` that promises a symbol the package
does not actually expose. Both would surface as an ImportError in production
rather than in a unit test, so they are pinned here.
"""

from __future__ import annotations

import importlib

import pytest

from app.services import race_control

# name -> module that defines it. The router imports the five overview
# builders; the rest are what the command-centre tests and callers reach for
# through the package.
_DEFINING_MODULE = {
    "DEFAULT_RACE_LAPS": "app.services.race_control.strategy_context",
    "WEATHER_FEED_LIVE": "app.services.race_control.weather",
    "WEATHER_FEED_OFFLINE": "app.services.race_control.weather",
    "build_live_status": "app.services.race_control.live",
    "build_overview": "app.services.race_control.overview",
    "build_overview_predictions": "app.services.race_control.overview",
    "build_overview_shell": "app.services.race_control.overview",
    "build_overview_strategy": "app.services.race_control.overview",
    "build_overview_weather": "app.services.race_control.overview",
    "build_risk_register": "app.services.race_control.risk",
    "build_strategy_context": "app.services.race_control.strategy_context",
    "focus_for_event": "app.services.race_control.workstreams",
}


@pytest.mark.unit
def test_package_publishes_exactly_the_documented_surface():
    assert set(race_control.__all__) == set(_DEFINING_MODULE)


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_DEFINING_MODULE))
def test_every_exported_name_is_the_object_its_module_defines(name):
    """A rebound copy would make a monkeypatch on the defining module a no-op."""
    module = importlib.import_module(_DEFINING_MODULE[name])

    assert getattr(race_control, name) is getattr(module, name)


@pytest.mark.unit
def test_export_list_is_sorted_so_additions_do_not_churn_the_diff():
    assert race_control.__all__ == sorted(race_control.__all__)
