"""Import prediction snapshots captured from a running server into the store.

Written for a specific failure: a deployment whose ``DATABASE_URL`` pointed at
Supabase's IPv6-only direct endpoint could not reach Postgres, so every snapshot
it computed lived only in process memory and on an ephemeral container disk.
Those snapshots are real work and are recoverable through
``/api/predictions/{year}/{round}/snapshot`` for as long as the process lives.

Input is a JSON object mapping ``"<year>:<round>"`` to the endpoint's response::

    {"2026:1": {"year": 2026, "round": 1, "predictions": [...], "cache": {...}}}

Each becomes a new snapshot appended to that round's existing history and marked
active. Nothing already stored is removed — a round that gains an imported
snapshot keeps every earlier revision.

    cd backend
    python -m scripts.import_snapshots harvest.json          # dry run
    python -m scripts.import_snapshots harvest.json --apply
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from app.data.store import DOCUMENT_PREDICTION_CACHE, document_store
from app.services.prediction_cache import CACHE_POLICY, CACHE_SCHEMA_VERSION

# Added by ``enrich_prediction_result`` when a snapshot is served, not by the
# model. Recomputed on every read, so storing them would only bloat the document.
DERIVED_KEYS = (
    "cache",
    "model_summary",
    "model_inputs",
    "model_limitations",
    "prediction_review",
)


def _strip_derived(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in DERIVED_KEYS}


def _snapshot_from(payload: dict, position: int) -> dict:
    """Build a cache snapshot from one endpoint response."""
    cache = payload.get("cache") or {}
    stored_at = cache.get("stored_at") or datetime.now(timezone.utc).isoformat()
    return {
        "id": f"v{position}-{stored_at}",
        "stored_at": stored_at,
        "reason": cache.get("reason") or "manual_compute",
        # Provenance: this snapshot was recovered from a server that could not
        # persist it, not written by the store in the normal course of events.
        "imported_from": "ephemeral_runtime",
        "result": _strip_derived(payload),
    }


def _merge(entries: dict, harvested: dict) -> tuple[dict, list[str]]:
    updated = copy.deepcopy(entries)
    changes: list[str] = []

    for key, payload in sorted(harvested.items()):
        if not payload.get("predictions"):
            continue

        entry = updated.get(key)
        snapshots = list((entry or {}).get("snapshots") or [])
        snapshot = _snapshot_from(payload, len(snapshots) + 1)

        if any(s.get("id") == snapshot["id"] for s in snapshots):
            changes.append(f"{key}: already imported, skipping")
            continue

        snapshots.append(snapshot)
        updated[key] = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "stored_at": (entry or {}).get("stored_at") or snapshot["stored_at"],
            "updated_at": snapshot["stored_at"],
            "policy": (entry or {}).get("policy") or CACHE_POLICY,
            "active_snapshot_id": snapshot["id"],
            "snapshots": snapshots,
        }
        verb = "new round" if entry is None else f"{len(snapshots) - 1} kept"
        changes.append(f"{key}: +1 snapshot ({verb}) -> active {snapshot['id']}")

    return updated, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="JSON file of harvested snapshots")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    harvested = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(harvested, dict):
        print("ERROR: source must be a JSON object keyed by '<year>:<round>'")
        return 1

    read = document_store.read(DOCUMENT_PREDICTION_CACHE)
    if not read.ok:
        print(f"ERROR reading prediction cache: {read.error}")
        return 1

    payload = read.payload or {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
    entries = payload.get("entries") or {}
    updated, changes = _merge(entries, harvested)

    print(f"harvested rounds: {len(harvested)}")
    print(f"stored before:    {len(entries)}")
    print(f"stored after:     {len(updated)}")
    for change in changes:
        print(f"  {change}")

    if not args.apply:
        print("\ndry run — re-run with --apply to write.")
        return 0

    result = document_store.write(
        DOCUMENT_PREDICTION_CACHE, {**payload, "entries": updated}
    )
    if not result.ok:
        print(f"\nERROR writing prediction cache: {result.error}")
        return 1

    print(f"\napplied. {len(changes)} round(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
