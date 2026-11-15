"""Tests for app.api.tools.rounds — which round a Grand Prix name means, on f1db's real 2026 calendar."""

from __future__ import annotations

import pytest

from app.api.tools.rounds import resolve_round

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("calendar_f1db")]


@pytest.mark.parametrize(
    ("name", "round_num"),
    [
        ("Mexican Grand Prix", 19),  # the event's own name
        ("Mexico", 19),  # the place, which f1db's event name ("Mexican") does not contain
        ("mexico city", 19),
        ("Madrid", 14),  # a place beats the country Barcelona shares
        ("United States", 18),  # the event's name beats the country Miami and Las Vegas share
        ("Miami", 4),
        ("Spain", 7),  # a country alone is the first round in it
        ("6", 6),
        ("Mexicann Grand Prix", 19),  # a near miss
    ],
)
def test_a_name_resolves_to_its_round(name, round_num):
    assert resolve_round(2026, name) == round_num


@pytest.mark.parametrize("name", ["99", "Grand Prix", "Atlantis"])
def test_a_name_matching_no_round_is_refused(name):
    with pytest.raises(ValueError, match="No 2026 Grand Prix matches"):
        resolve_round(2026, name)
