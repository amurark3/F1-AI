"""Persistent cache for race prediction snapshots."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import threading
import time
from typing import TYPE_CHECKING, Any

import fastf1
import pandas as pd
import structlog

from app.data.predictions import PREDICTION_LOGIC_VERSION
from app.data.store import DOCUMENT_PREDICTION_CACHE, document_store

if TYPE_CHECKING:
    from app.data.store_types import WriteResult

logger = structlog.get_logger()

CACHE_SCHEMA_VERSION = 2
CACHE_POLICY = "stored_until_manual_recompute"

# How long to wait before retrying a failed load. Without a retry, a single
# failed read (a paused database, a network blip) would pin an empty snapshot
# set for the entire process lifetime — which is exactly how a recovered
# database still served "no stored prediction" until the container restarted.
RELOAD_BACKOFF_SECONDS = 30.0


class PredictionCacheUnavailableError(RuntimeError):
    """Raised when the snapshot store cannot be read, so writing is unsafe.

    Persisting on top of a failed load would upload a document containing only
    the entries this process happens to hold, silently destroying every snapshot
    it failed to read.
    """


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _coerce_utc(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _race_datetime(row: Any) -> datetime | None:
    for index in range(1, 6):
        if str(row.get(f"Session{index}", "")).lower() == "race":
            race_date = _coerce_utc(row.get(f"Session{index}DateUtc"))
            if race_date:
                return race_date

    for index in range(5, 0, -1):
        session_date = _coerce_utc(row.get(f"Session{index}DateUtc"))
        if session_date:
            return session_date

    return _coerce_utc(row.get("EventDate"))


def next_race_start(year: int) -> datetime | None:
    """Return the next race start for the season, if the calendar is available."""

    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("prediction_cache.schedule_unavailable", year=year, error=str(exc))
        return None

    now = _utc_now()
    upcoming: list[datetime] = []
    for _, row in schedule.iterrows():
        race_date = _race_datetime(row)
        if race_date and race_date > now:
            upcoming.append(race_date)

    return min(upcoming) if upcoming else None


class PredictionSnapshotCache:
    """Small JSON-backed cache keyed by season and round.

    Race prediction outputs are intentionally stable snapshots. They are
    reused until a user explicitly asks the model to compute or recompute,
    so old calls remain available for post-race review.
    """

    def __init__(self) -> None:
        self._loaded = False
        self._entries: dict[str, dict[str, Any]] = {}
        self._next_load_attempt = 0.0
        self._lock = threading.RLock()

    def get(self, year: int, round_num: int) -> dict | None:
        self._ensure_loaded()
        key = self._key(year, round_num)
        with self._lock:
            entry = self._entries.get(key)
        if not entry or not self._has_prediction(entry):
            return None

        if self._is_stale(entry):
            # Snapshot was produced by superseded prediction logic. Treat it as a
            # miss so callers recompute; never surface outdated predictions.
            logger.info(
                "prediction_cache.stale",
                year=year,
                round=round_num,
                snapshot_version=self._snapshot_logic_version(entry),
                current_version=PREDICTION_LOGIC_VERSION,
            )
            return None

        logger.info("prediction_cache.hit", year=year, round=round_num)
        return self._with_metadata(entry, status="hit")

    def _snapshot_logic_version(self, entry: dict[str, Any]) -> int:
        snapshot = self._active_snapshot(self._normalise_entry(entry))
        result = (snapshot or {}).get("result") or {}
        # Snapshots stored before logic-versioning existed default to 0 (stale).
        return int(result.get("logic_version") or 0)

    def _is_stale(self, entry: dict[str, Any]) -> bool:
        return self._snapshot_logic_version(entry) != PREDICTION_LOGIC_VERSION

    def set(self, year: int, round_num: int, result: dict, *, reason: str = "manual_compute") -> dict:
        if not self._ensure_loaded():
            raise PredictionCacheUnavailableError(
                "Prediction store is unreachable; refusing to overwrite stored "
                "snapshots with an incomplete set. Try again shortly."
            )

        key = self._key(year, round_num)
        stored_result = copy.deepcopy(result)
        stored_result.pop("cache", None)

        with self._lock:
            previous = self._normalise_entry(self._entries.get(key))
            snapshots = list(previous.get("snapshots") or [])
            stored_at = _iso(_utc_now())
            snapshot = {
                "id": f"v{len(snapshots) + 1}-{stored_at}",
                "stored_at": stored_at,
                "reason": reason,
                "result": stored_result,
            }
            snapshots.append(snapshot)

            entry = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "stored_at": previous.get("stored_at") or stored_at,
                "updated_at": stored_at,
                "policy": CACHE_POLICY,
                "active_snapshot_id": snapshot["id"],
                "snapshots": snapshots,
            }
            self._entries[key] = entry
            write = self._save()

        logger.info(
            "prediction_cache.stored",
            year=year,
            round=round_num,
            snapshot_id=snapshot["id"],
            reason=reason,
            durable=write.durable,
        )
        # A failed write is queued by the store and retried, and the snapshot is
        # live in memory either way — so the caller still gets its prediction,
        # with the durability caveat stated rather than hidden.
        return self._with_metadata(entry, status="stored", durable=write.durable)

    def _with_metadata(self, entry: dict[str, Any], status: str, durable: bool = True) -> dict:
        normalised = self._normalise_entry(entry)
        snapshot = self._active_snapshot(normalised)
        result = copy.deepcopy((snapshot or {}).get("result") or {})
        result["cache"] = {
            "status": status,
            "stored_at": (snapshot or {}).get("stored_at") or normalised.get("stored_at"),
            "updated_at": normalised.get("updated_at") or normalised.get("stored_at"),
            "valid_until": None,
            "policy": normalised.get("policy", CACHE_POLICY),
            "snapshot_id": (snapshot or {}).get("id"),
            "snapshot_count": len(normalised.get("snapshots") or []),
            "recompute_count": max(0, len(normalised.get("snapshots") or []) - 1),
            "reason": (snapshot or {}).get("reason"),
            "durable": durable,
        }
        return result

    def _has_prediction(self, entry: dict[str, Any]) -> bool:
        snapshot = self._active_snapshot(self._normalise_entry(entry))
        result = (snapshot or {}).get("result") or {}
        # `bool(...)`, not the list itself: the return type is part of the
        # contract, and an empty-but-present `predictions` list means the same
        # thing as a missing one — no prediction to serve.
        return bool(result.get("predictions"))

    def _active_snapshot(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        snapshots = entry.get("snapshots") or []
        if not snapshots:
            return None
        active_id = entry.get("active_snapshot_id")
        for snapshot in snapshots:
            if snapshot.get("id") == active_id:
                return snapshot
        return snapshots[-1]

    def _normalise_entry(self, entry: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {
                "schema_version": CACHE_SCHEMA_VERSION,
                "policy": CACHE_POLICY,
                "snapshots": [],
            }

        if entry.get("schema_version") == CACHE_SCHEMA_VERSION:
            normalised = copy.deepcopy(entry)
            normalised["policy"] = normalised.get("policy") or CACHE_POLICY
            normalised["snapshots"] = [
                snapshot
                for snapshot in normalised.get("snapshots", [])
                if isinstance(snapshot, dict) and isinstance(snapshot.get("result"), dict)
            ]
            return normalised

        legacy_result = entry.get("result")
        if isinstance(legacy_result, dict):
            stored_at = entry.get("stored_at") or legacy_result.get("generated_at") or _iso(_utc_now())
            snapshot = {
                "id": f"v1-{stored_at}",
                "stored_at": stored_at,
                "reason": "legacy_cache",
                "result": copy.deepcopy(legacy_result),
            }
            return {
                "schema_version": CACHE_SCHEMA_VERSION,
                "stored_at": stored_at,
                "updated_at": stored_at,
                "policy": CACHE_POLICY,
                "active_snapshot_id": snapshot["id"],
                "snapshots": [snapshot],
            }

        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "policy": CACHE_POLICY,
            "snapshots": [],
        }

    def load(self) -> bool:
        """Read the snapshot document from the store. Returns success.

        Called on startup warm-up and lazily on first use. A failure is left
        unloaded so a later call retries; it is never recorded as "loaded and
        empty".
        """
        with self._lock:
            self._next_load_attempt = time.monotonic() + RELOAD_BACKOFF_SECONDS
            read = document_store.read(DOCUMENT_PREDICTION_CACHE)

            if not read.ok:
                logger.error("prediction_cache.load_failed", error=read.error)
                return False

            payload = read.payload
            if payload is None:
                # The store answered and holds nothing yet — a real empty cache.
                self._entries = {}
                self._loaded = True
                return True

            schema_version = payload.get("schema_version")
            if schema_version not in {1, CACHE_SCHEMA_VERSION}:
                logger.warning("prediction_cache.unsupported_schema", schema_version=schema_version)
                self._entries = {}
                self._loaded = True
                return True

            self._entries = {
                str(key): self._normalise_entry(value)
                for key, value in (payload.get("entries") or {}).items()
                if isinstance(value, dict)
            }
            self._loaded = True
            logger.info("prediction_cache.loaded", entries=len(self._entries))
            return True

    def _ensure_loaded(self) -> bool:
        """Load on first use, retrying a previous failure after a backoff."""
        with self._lock:
            if self._loaded:
                return True
            if time.monotonic() < self._next_load_attempt:
                return False
            return self.load()

    def _save(self) -> WriteResult:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": self._entries,
        }
        return document_store.write(DOCUMENT_PREDICTION_CACHE, payload)

    @staticmethod
    def _key(year: int, round_num: int) -> str:
        return f"{year}:{round_num}"


prediction_snapshot_cache = PredictionSnapshotCache()
