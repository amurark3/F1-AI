"""Persistent cache for race prediction snapshots."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fastf1
import pandas as pd
import structlog

from app.config import PREDICTION_CACHE_PATH

logger = structlog.get_logger()

CACHE_SCHEMA_VERSION = 1
CACHE_POLICY = "stable_until_next_race"


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
    reused until the next race starts, then regenerated so standings and
    recent-form inputs can move forward.
    """

    def __init__(self, path: str = PREDICTION_CACHE_PATH) -> None:
        self.path = Path(path)
        self._loaded = False
        self._entries: dict[str, dict[str, Any]] = {}

    def get(self, year: int, round_num: int) -> dict | None:
        self._ensure_loaded()
        key = self._key(year, round_num)
        entry = self._entries.get(key)
        if not entry or not self._is_valid(entry):
            return None

        logger.info("prediction_cache.hit", year=year, round=round_num)
        return self._with_metadata(entry, status="hit")

    def set(self, year: int, round_num: int, result: dict) -> dict:
        self._ensure_loaded()
        key = self._key(year, round_num)
        stored_result = copy.deepcopy(result)
        stored_result.pop("cache", None)

        entry = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "stored_at": _iso(_utc_now()),
            "valid_until": _iso(next_race_start(year)),
            "policy": CACHE_POLICY,
            "result": stored_result,
        }
        self._entries[key] = entry
        self._save()

        logger.info(
            "prediction_cache.stored",
            year=year,
            round=round_num,
            valid_until=entry["valid_until"],
        )
        return self._with_metadata(entry, status="stored")

    def _with_metadata(self, entry: dict[str, Any], status: str) -> dict:
        result = copy.deepcopy(entry.get("result") or {})
        result["cache"] = {
            "status": status,
            "stored_at": entry.get("stored_at"),
            "valid_until": entry.get("valid_until"),
            "policy": entry.get("policy", CACHE_POLICY),
        }
        return result

    def _is_valid(self, entry: dict[str, Any]) -> bool:
        if entry.get("schema_version") != CACHE_SCHEMA_VERSION:
            return False
        result = entry.get("result") or {}
        if not result.get("predictions"):
            return False

        valid_until = entry.get("valid_until")
        if not valid_until:
            return True

        try:
            expiry = datetime.fromisoformat(valid_until)
        except ValueError:
            return False
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        return _utc_now() < expiry.astimezone(timezone.utc)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        if not self.path.exists():
            self._entries = {}
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("prediction_cache.load_failed", path=str(self.path), error=str(exc))
            self._entries = {}
            return

        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            self._entries = {}
            return

        self._entries = {
            str(key): value
            for key, value in (payload.get("entries") or {}).items()
            if isinstance(value, dict)
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": self._entries,
        }
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)

    @staticmethod
    def _key(year: int, round_num: int) -> str:
        return f"{year}:{round_num}"


prediction_snapshot_cache = PredictionSnapshotCache()
