"""Race Rewind's inputs for R19, served from the real fixtures: every car's laps, positions, overtakes and pit rows."""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

from app.data import f1db_source
from app.data.analysis_cache import AnalysisCache
from app.data.openf1.laps import laps_from_openf1
from app.data.openf1.race_control import neutralised_windows
from app.data.openf1.session_laps import SessionLaps
from app.services import race_grid, race_rewind
from tests import fia_documents_support, race_results_support
from tests.debrief_r19_support import entries, race_session, rows

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

FIXTURE_BY_PATH = {
    "position": "openf1_position.json",
    "overtakes": "openf1_overtakes.json",
    "pit": "openf1_pit_settled.json",
}


def full_session_laps() -> SessionLaps:
    """The race with all 22 cars' laps, the entry list and race control's windows."""
    return SessionLaps(
        session=race_session(),
        year=2026,
        round=19,
        drivers=entries(),
        laps=laps_from_openf1(rows("openf1_laps.json")),
        windows=neutralised_windows(rows("openf1_race_control.json")),
    )


def serve_mexico(monkeypatch: pytest.MonkeyPatch, root: Path) -> AnalysisCache:
    """R19 as the rewind reads it: FIA documents, f1db results and OpenF1 rows from the fixtures."""
    fia_documents_support.hold(monkeypatch, root / "fia")
    monkeypatch.setattr(f1db_source, "DB_PATH", race_results_support.build_race_results_db(root / "f1db.db"))
    monkeypatch.setattr(race_grid, "starting_grid", lambda *_args: ())
    cache = AnalysisCache(None, 64)
    monkeypatch.setattr(race_rewind, "analysis_cache", cache)
    monkeypatch.setattr(race_rewind, "load_session_laps", lambda *_args: full_session_laps())
    monkeypatch.setattr(race_rewind, "new_client", nullcontext)
    monkeypatch.setattr(race_rewind, "find_session", lambda *_args: race_session())
    monkeypatch.setattr(race_rewind, "get_json", lambda _client, path, _params: rows(FIXTURE_BY_PATH[path]))
    return cache
