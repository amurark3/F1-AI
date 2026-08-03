"""One-time backfill: stamp ``logic_version`` onto pre-versioning snapshots.

Snapshots stored before ``PREDICTION_LOGIC_VERSION`` existed carry no version,
which ``PredictionSnapshotCache._is_stale`` reads as version 0 — so they are
treated as superseded and never served.  For 2026 rounds 1-10 that means ten
completed races whose stored predictions exist in the database but can never be
displayed, because the snapshot endpoint the UI uses never recomputes.

These snapshots were produced by older logic, so this stamp is a decision to
serve them, not a claim that current logic generated them.  Every affected
snapshot therefore also gets ``logic_version_backfilled: true`` recording that
provenance, which rides along in the API response.

    cd backend
    python -m scripts.backfill_logic_version          # dry run, prints a plan
    python -m scripts.backfill_logic_version --apply  # writes

By default only snapshots with a missing/zero version are touched; snapshots
from a genuinely older *numbered* version are left alone unless ``--include-old``
is passed, since those were versioned deliberately.
"""

from __future__ import annotations

import argparse
import copy

from app.data.predictions import PREDICTION_LOGIC_VERSION
from app.data.store import DOCUMENT_PREDICTION_CACHE, document_store

BACKFILL_MARKER = "logic_version_backfilled"


def _snapshot_version(snapshot: dict) -> int:
    result = snapshot.get("result") or {}
    return int(result.get("logic_version") or 0)


def _should_stamp(snapshot: dict, include_old: bool) -> bool:
    version = _snapshot_version(snapshot)
    if version == PREDICTION_LOGIC_VERSION:
        return False
    return version == 0 or include_old


def _stamp(snapshot: dict) -> dict:
    """Return a copy of ``snapshot`` with the version and provenance recorded."""
    stamped = copy.deepcopy(snapshot)
    result = stamped.get("result")
    if not isinstance(result, dict):
        return stamped
    result["logic_version"] = PREDICTION_LOGIC_VERSION
    result[BACKFILL_MARKER] = True
    result["logic_version_backfilled_from"] = _snapshot_version(snapshot)
    return stamped


def _active_index(entry: dict) -> int | None:
    """Index of the snapshot the cache serves, mirroring ``_active_snapshot``."""
    snapshots = entry.get("snapshots") or []
    if not snapshots:
        return None
    active_id = entry.get("active_snapshot_id")
    for index, snapshot in enumerate(snapshots):
        if isinstance(snapshot, dict) and snapshot.get("id") == active_id:
            return index
    return len(snapshots) - 1


def _plan(entries: dict, include_old: bool) -> tuple[dict, list[str]]:
    """Return the rewritten entries and a human-readable list of changes.

    Only the active snapshot of each entry is stamped. The others are superseded
    revisions kept for history; the cache never serves them, and rewriting them
    would edit a record of what was predicted at the time for no benefit.
    """
    updated: dict = {}
    changes: list[str] = []

    for key, entry in entries.items():
        if not isinstance(entry, dict):
            updated[key] = entry
            continue

        index = _active_index(entry)
        snapshots = entry.get("snapshots") or []
        if index is None:
            updated[key] = entry
            continue

        active = snapshots[index]
        if not isinstance(active, dict) or not _should_stamp(active, include_old):
            updated[key] = entry
            continue

        new_snapshots = list(snapshots)
        new_snapshots[index] = _stamp(active)
        changes.append(
            f"{key}: active snapshot {active.get('id')} "
            f"(v{_snapshot_version(active)} -> v{PREDICTION_LOGIC_VERSION})"
        )
        updated[key] = {**entry, "snapshots": new_snapshots}

    return updated, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument(
        "--include-old",
        action="store_true",
        help="also stamp snapshots from an older numbered logic version",
    )
    args = parser.parse_args()

    read = document_store.read(DOCUMENT_PREDICTION_CACHE)
    if not read.ok:
        print(f"ERROR reading prediction cache: {read.error}")
        return 1
    if read.payload is None:
        print("No prediction cache document stored — nothing to backfill.")
        return 0

    payload = read.payload
    entries = payload.get("entries") or {}
    updated, changes = _plan(entries, args.include_old)

    print(f"target logic_version: {PREDICTION_LOGIC_VERSION}")
    print(f"entries scanned:      {len(entries)}")
    if not changes:
        print("nothing to backfill.")
        return 0

    print(f"entries to stamp:     {len(changes)}")
    for change in sorted(changes):
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

    print(f"\napplied. {len(changes)} entry/entries updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
