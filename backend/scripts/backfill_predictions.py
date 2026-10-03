"""Backfill: compute and store every prediction of a season up to the current race.

A stored snapshot is only served while its ``logic_version`` matches
``PREDICTION_LOGIC_VERSION``, so each logic change leaves the season's earlier
races with predictions in the database that the UI can no longer show. This
recomputes them under the current logic.

Each round gets a pre-qualifying call and, once qualifying has run, a
post-qualifying call. Rounds run oldest first, pre-qualifying before
post-qualifying — the order the calls are made live — so each race's adaptive
correction learns from the backfilled calls for the races before it. Every
input is taken as of the race (standings going into it, adaptive corrections
from earlier races only), so a backfilled call never sees its own result.

Snapshots are stored with reason ``backfill``; their ``generated_at`` postdates
the race. Both documents are copied to ``--backup-dir`` before the first write.

    cd backend
    python -m scripts.backfill_predictions                    # dry run, prints the plan
    python -m scripts.backfill_predictions --apply
    python -m scripts.backfill_predictions --apply --through-round 12 --recompute

By default a phase that already holds a current-version snapshot is skipped,
so an interrupted run resumes where it stopped. ``--recompute`` redoes those.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Must run before anything under ``app`` is imported: the document store picks
# its backend from ``DATABASE_URL`` at import time, and without it this would
# "backfill" the local JSON file while production kept serving stale snapshots.
load_dotenv()

import fastf1

from app.data.predictions import (
    PHASE_POST_QUALIFYING,
    PHASE_PRE_QUALIFYING,
    should_use_qualifying,
)
from app.data.store import (
    DOCUMENT_PREDICTION_CACHE,
    DOCUMENT_PREDICTION_HISTORY,
    document_store,
)
from app.services.prediction_cache import prediction_snapshot_cache
from app.services.predictions import compute_and_store_race_prediction
from app.utils.fastf1_cache import enable_fastf1_cache

REASON = "backfill"
DEFAULT_BACKUP_DIR = Path("data/backups")


@dataclass(frozen=True)
class PlannedCall:
    round_num: int
    grand_prix: str
    phase: str
    existing: bool


def _first_session(row) -> datetime | None:
    stamps = [row.get(f"Session{i}DateUtc") for i in range(1, 6)]
    valid = [stamp for stamp in stamps if stamp is not None and str(stamp) != "NaT"]
    if not valid:
        return None
    first = min(valid).to_pydatetime()
    return first.replace(tzinfo=timezone.utc) if first.tzinfo is None else first


def _current_round(schedule) -> int:
    """The latest round whose weekend has started — the current race."""
    now = datetime.now(timezone.utc)
    started = [
        int(row["RoundNumber"])
        for _, row in schedule.iterrows()
        if (first := _first_session(row)) is not None and first <= now
    ]
    return max(started, default=0)


def _plan(year: int, through_round: int | None, recompute: bool) -> list[PlannedCall]:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    last_round = through_round or _current_round(schedule)

    calls: list[PlannedCall] = []
    for _, row in schedule.sort_values("RoundNumber").iterrows():
        round_num = int(row["RoundNumber"])
        if round_num > last_round:
            break
        phases = [PHASE_PRE_QUALIFYING]
        if should_use_qualifying(row, forced_pre_qualifying=False):
            phases.append(PHASE_POST_QUALIFYING)
        for phase in phases:
            existing = prediction_snapshot_cache.get(year, round_num, phase=phase) is not None
            if existing and not recompute:
                continue
            calls.append(PlannedCall(round_num, str(row["EventName"]), phase, existing))
    return calls


def _backup(backup_dir: Path) -> Path | None:
    """Copy both prediction documents to a timestamped file; None on failure."""
    documents = {}
    for name in (DOCUMENT_PREDICTION_CACHE, DOCUMENT_PREDICTION_HISTORY):
        read = document_store.read(name)
        if not read.ok:
            print(f"ERROR reading {name} for backup: {read.error}")
            return None
        documents[name] = read.payload

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"predictions-{stamp}.json"
    path.write_text(json.dumps(documents, default=str), encoding="utf-8")
    return path


def _describe(result: dict) -> str:
    predictions = result.get("predictions") or []
    if not predictions:
        return f"FAILED — {result.get('error') or 'no predictions'}"
    sources = set(result.get("data_sources") or [])
    grid = next((s for s in ("qualifying", "practice") if s in sources), "history")
    model = "model" if "trained_ml_model" in sources else "NO MODEL (heuristic only)"
    durable = (result.get("cache") or {}).get("durable", True)
    return (
        f"P1 {predictions[0]['driver_code']}, {len(predictions)} drivers, "
        f"grid from {grid}, {model}{'' if durable else ', NOT DURABLE'}"
    )


def _run(year: int, calls: list[PlannedCall]) -> int:
    failures = 0
    for call in calls:
        result = compute_and_store_race_prediction(
            year, call.round_num, reason=REASON, phase=call.phase
        )
        summary = _describe(result)
        failures += summary.startswith("FAILED") or "NOT DURABLE" in summary
        print(f"  R{call.round_num:>2} {call.phase:<16} {summary}", flush=True)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument(
        "--through-round", type=int, help="last round to compute (default: the current race)"
    )
    parser.add_argument(
        "--recompute", action="store_true", help="also redo phases with a current snapshot"
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--apply", action="store_true", help="compute and write")
    args = parser.parse_args()

    enable_fastf1_cache()
    if not prediction_snapshot_cache.load():
        print("ERROR: prediction store unreachable; refusing to write.")
        return 1

    calls = _plan(args.year, args.through_round, args.recompute)
    print(f"store: {type(document_store).__name__}")
    print(f"{args.year}: {len(calls)} call(s) to compute")
    for call in calls:
        note = " (replaces a current-version snapshot)" if call.existing else ""
        print(f"  R{call.round_num:>2} {call.grand_prix:<28} {call.phase}{note}")

    if not calls:
        return 0
    if not args.apply:
        print("\ndry run — re-run with --apply to compute and write.")
        return 0

    backup = _backup(args.backup_dir)
    if backup is None:
        return 1
    print(f"\nbacked up both documents to {backup}\n")

    failures = _run(args.year, calls)
    print(f"\ndone. {len(calls) - failures}/{len(calls)} stored.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
