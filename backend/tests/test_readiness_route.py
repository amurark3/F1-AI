"""Tests for the dataset freshness report on ``GET /api/ready``.

The behaviour under test: a server whose f1db release check is failing says so.
Production served round-11 data for five rounds while ``/api/ready`` showed only
the installed version — a release tag that looks equally plausible whether the
server is current or stranded on its hardcoded fallback.
"""

import asyncio

import pytest

from app.api.routers import readiness as router_module
from app.data.f1db_source import SyncOutcome

pytestmark = pytest.mark.unit


def _ready(monkeypatch, outcome: SyncOutcome | None) -> dict:
    monkeypatch.setattr(router_module, "installed_version", lambda: "v2026.11.0")
    monkeypatch.setattr(router_module, "last_sync_outcome", lambda: outcome)
    return asyncio.run(router_module.readiness_probe())


def test_ready_reports_a_failing_release_check(monkeypatch):
    stranded = SyncOutcome(
        version="v2026.11.0",
        updated=False,
        reason="release check failed, kept v2026.11.0",
        latest=None,
        checked_at="2026-10-09T16:19:02+00:00",
    )

    payload = _ready(monkeypatch, stranded)

    assert payload["f1db_version"] == "v2026.11.0"
    assert payload["f1db_sync"] == {
        "version": "v2026.11.0",
        "latest": None,
        "up_to_date": False,
        "updated": False,
        "reason": "release check failed, kept v2026.11.0",
        "checked_at": "2026-10-09T16:19:02+00:00",
    }


def test_ready_reports_a_current_dataset(monkeypatch):
    current = SyncOutcome(
        version="v2026.16.1",
        updated=True,
        reason="updated from no dataset to v2026.16.1",
        latest="v2026.16.1",
        checked_at="2026-10-09T16:19:02+00:00",
    )

    assert _ready(monkeypatch, current)["f1db_sync"]["up_to_date"] is True


def test_ready_reports_no_check_before_the_first_one(monkeypatch):
    assert _ready(monkeypatch, None)["f1db_sync"] is None
