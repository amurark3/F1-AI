"""FastF1 cache setup with corrupted SQLite recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Any

import fastf1
import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = BACKEND_ROOT / "f1_cache"
FASTF1_HTTP_CACHE = "fastf1_http_cache.sqlite"
_PATCHED = False
_ACTIVE_CACHE_DIR = DEFAULT_CACHE_DIR
_ORIGINAL_GET_SESSION: Callable[..., Any] | None = None
_ORIGINAL_GET_EVENT_SCHEDULE: Callable[..., Any] | None = None


def enable_fastf1_cache(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> Path:
    """Enable FastF1's HTTP cache and recover from malformed cache databases.

    FastF1 uses requests-cache with a SQLite backend. If the process is killed
    during a write, that cache can become malformed and later crash unrelated
    requests. The cache is disposable, so we quarantine the broken DB and let
    FastF1 recreate it.
    """

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    _repair_if_malformed(cache_path)

    try:
        fastf1.Cache.enable_cache(str(cache_path))
    except sqlite3.DatabaseError as exc:
        logger.warning("fastf1_cache.enable_failed", cache_dir=str(cache_path), error=str(exc))
        _quarantine_cache_files(cache_path)
        fastf1.Cache.enable_cache(str(cache_path))

    _install_recovery_hooks(cache_path)
    return cache_path


def _install_recovery_hooks(cache_path: Path) -> None:
    """Patch FastF1's public loaders so cache corruption is repaired at runtime."""

    global _PATCHED, _ACTIVE_CACHE_DIR, _ORIGINAL_GET_SESSION, _ORIGINAL_GET_EVENT_SCHEDULE
    _ACTIVE_CACHE_DIR = cache_path

    if _PATCHED:
        return

    _ORIGINAL_GET_SESSION = fastf1.get_session
    _ORIGINAL_GET_EVENT_SCHEDULE = fastf1.get_event_schedule

    def safe_get_event_schedule(*args: Any, **kwargs: Any) -> Any:
        return _with_cache_repair(
            lambda: _ORIGINAL_GET_EVENT_SCHEDULE(*args, **kwargs),  # type: ignore[misc]
            "get_event_schedule",
        )

    def safe_get_session(*args: Any, **kwargs: Any) -> Any:
        session = _with_cache_repair(
            lambda: _ORIGINAL_GET_SESSION(*args, **kwargs),  # type: ignore[misc]
            "get_session",
        )
        _patch_session_load(session, args, kwargs)
        return session

    fastf1.get_event_schedule = safe_get_event_schedule
    fastf1.get_session = safe_get_session
    _PATCHED = True


def _patch_session_load(session: Any, session_args: tuple[Any, ...], session_kwargs: dict[str, Any]) -> None:
    original_load = session.load

    def safe_load(*args: Any, **kwargs: Any) -> Any:
        try:
            return original_load(*args, **kwargs)
        except sqlite3.DatabaseError as exc:
            logger.warning("fastf1_cache.runtime_malformed", operation="session.load", error=str(exc))
            _quarantine_cache_files(_ACTIVE_CACHE_DIR)
            fastf1.Cache.enable_cache(str(_ACTIVE_CACHE_DIR))
            if _ORIGINAL_GET_SESSION is None:
                raise
            new_session = _ORIGINAL_GET_SESSION(*session_args, **session_kwargs)
            result = new_session.load(*args, **kwargs)
            session.__dict__.update(new_session.__dict__)
            return result

    try:
        session.load = safe_load
    except (AttributeError, TypeError):
        logger.warning("fastf1_cache.session_load_patch_failed", session=type(session).__name__)


def _with_cache_repair(operation: Callable[[], Any], label: str) -> Any:
    try:
        return operation()
    except sqlite3.DatabaseError as exc:
        logger.warning("fastf1_cache.runtime_malformed", operation=label, error=str(exc))
        _quarantine_cache_files(_ACTIVE_CACHE_DIR)
        fastf1.Cache.enable_cache(str(_ACTIVE_CACHE_DIR))
        return operation()


def _repair_if_malformed(cache_path: Path) -> None:
    db_path = cache_path / FASTF1_HTTP_CACHE
    if not db_path.exists():
        return

    try:
        with sqlite3.connect(db_path) as con:
            result = con.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError(str(result[0] if result else "quick_check failed"))
    except sqlite3.DatabaseError as exc:
        logger.warning("fastf1_cache.malformed", db_path=str(db_path), error=str(exc))
        _quarantine_cache_files(cache_path)


def _quarantine_cache_files(cache_path: Path) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for path in cache_path.glob(f"{FASTF1_HTTP_CACHE}*"):
        if not path.is_file():
            continue
        target = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            path.replace(target)
            logger.warning("fastf1_cache.quarantined", source=str(path), target=str(target))
        except OSError as exc:
            logger.warning("fastf1_cache.quarantine_failed", source=str(path), error=str(exc))
