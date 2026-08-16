"""Tests for the app.services.race_control package facade.

The package exists so the router can keep importing one name while the feature
blocks (weather, risk, workstreams, strategy context) are split across files.
The risk it carries is a silent contract break: a re-export that drifts away
from the implementation, or an ``__all__`` that promises a symbol the package
does not actually expose. Both would surface as an ImportError in production
rather than in a unit test, so they are pinned here.
"""

from __future__ import annotations

import pytest

from app.services import race_control
from app.services.race_control import overview


@pytest.mark.unit
def test_package_reexports_the_overview_builder_itself_not_a_copy():
    assert race_control.build_overview is overview.build_overview


@pytest.mark.unit
def test_package_publishes_exactly_the_overview_entry_point():
    """``build_overview`` is the whole public surface — the router imports nothing else."""
    assert race_control.__all__ == ["build_overview"]
    for name in race_control.__all__:
        assert hasattr(race_control, name)
