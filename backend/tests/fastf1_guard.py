"""A guard that fails the test when any code asks FastF1 for a session."""

from __future__ import annotations

import fastf1
import pytest


@pytest.fixture
def no_fastf1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any ``fastf1.get_session`` or ``Session.load`` fails the test."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FastF1 was asked for a session")

    monkeypatch.setattr(fastf1, "get_session", refuse)
    monkeypatch.setattr(fastf1.core.Session, "load", refuse)
