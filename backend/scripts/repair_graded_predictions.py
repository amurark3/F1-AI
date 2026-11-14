"""Repair: reset each race's graded call in prediction history, and drop the calls never stored.

Until P0b.9, ``save_prediction`` set a race's top-level ``predicted_positions``
(with ``risk_predictions``, ``prediction_phase``, ``generated_at`` and
``data_sources``) to whichever call was computed last, of either phase, so R20
São Paulo was graded on a pre-qualifying call (VER P2) instead of the
post-qualifying one the site showed (VER P8). This sets those fields to each
race's graded call (``app.data.predictions.graded``: the latest
post-qualifying call when the race has one, else its latest pre-qualifying
call), and touches nothing else: the stored calls and the recorded results stay
exactly as they are.

History also holds calls that never reached the snapshot cache: computes
recorded and then refused or abandoned (P0b.9c). The cache document is read,
never written, to find them. A call is dropped only when it matches no stored
snapshot (``generated_at`` compared as an instant) and is newer than the race's
oldest kept snapshot. The cache trims old snapshots, so an older unmatched call
may have been shown and trimmed since: it is kept, as is every call of a race
the cache keeps nothing for and any call whose timestamp, or a stored one,
cannot be read. Graded fields stay as above: a call never stored that is the
race's graded call refuses the whole run.

    cd backend
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.repair_graded_predictions          # dry run
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.repair_graded_predictions --apply  # writes

A dry run lists every race whose graded call changes, with its phase before
and after and the drivers that move, then every call it drops and every
unmatched call it keeps, each with its reason. ``--apply`` copies the history
and cache documents to ``--backup-dir`` first, reads both again and writes the
history only if neither changed in between. A second run finds nothing to
repair.

``DATABASE_URL`` comes from the environment only. Unlike the older scripts
this one never reads ``backend/.env``, which points at production, so a write
always goes where it was deliberately aimed. ``--local`` aims it at the file
store instead (``PREDICTION_HISTORY_PATH``, default
``data/prediction_history.json``), and only with no ``DATABASE_URL``:

    DATABASE_URL= PREDICTION_HISTORY_PATH=/tmp/copy.json .venv/bin/python -m scripts.repair_graded_predictions --local

Exit status: 0 done, nothing to repair, or a dry run; 1 the write failed (the
backup holds the document as it was); 2 a document could not be read or
backed up, or it changed during the run; 3 no ``DATABASE_URL``; 4 the store is
not the one asked for; 5 dropping a call never stored would change a race's
graded call (nothing written).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from app.config import PREDICTION_HISTORY_PATH
from app.data.predictions.graded import CALL_FIELDS, graded_call, with_graded_fields
from app.data.predictions.phases import SNAPSHOT_HISTORY_LIMIT
from app.data.store import BACKEND_POSTGRES, DOCUMENT_PREDICTION_CACHE, DOCUMENT_PREDICTION_HISTORY, document_store

EXIT_OK = 0
EXIT_WRITE_FAILED = 1
EXIT_STORE_ERROR = 2
EXIT_NO_DATABASE = 3
EXIT_WRONG_STORE = 4
EXIT_GRADED_CALL_WOULD_CHANGE = 5

DEFAULT_BACKUP_DIR = Path("data/backups")

# How many moved drivers a race's line shows, biggest move first.
DRIVERS_SHOWN = 5

NO_DATABASE = (
    "DATABASE_URL is not set. Export the URL of the database to repair; this "
    "script never reads backend/.env, which points at production. Use --local "
    "for the file store."
)
FELL_BACK = (
    "DATABASE_URL is set but the store fell back to the local file (the database "
    "could not be opened), so nothing would reach the database. Check the URL."
)
LOCAL_WITH_DATABASE = "--local repairs the file store, but DATABASE_URL is set. Unset it, or drop --local."

# What happens to a history call that matches no stored snapshot.
DROP, KEEP, REFUSE = "drop", "keep", "refuse"
UNREADABLE_CALL = "its generated_at cannot be read, so no stored snapshot can be matched to it"
UNREADABLE_STORED = "a stored snapshot's generated_at cannot be read, so the cache proves nothing for this race"


@dataclass(frozen=True)
class RaceChange:
    """One race whose top-level call fields change: before and after."""

    key: str
    before: dict
    after: dict


@dataclass(frozen=True)
class CallNote:
    """A history call that matches no stored snapshot: dropped, kept or refused, and why."""

    key: str
    call: dict
    verdict: str
    reason: str


@dataclass(frozen=True)
class RepairPlan:
    """The repaired history, and every race and call the repair changes, drops, keeps or refuses."""

    repaired: dict
    changes: list[RaceChange]
    dropped: list[CallNote]
    kept: list[CallNote]
    refused: list[CallNote]
    # Races the cache keeps no snapshot for, with how many calls each holds.
    uncached: list[tuple[str, int]]


def _race_order(key: str) -> tuple[int, int, int, str]:
    """Calendar order for ``"(year,round)"`` keys; anything else sorts last."""
    try:
        year, round_num = (int(part) for part in key.strip("()").split(","))
    except ValueError:
        return (1, 0, 0, key)
    return (0, year, round_num, key)


def _call_fields(entry: dict) -> dict:
    return {field: entry.get(field) for field in CALL_FIELDS}


def _calls(entry: dict) -> list[dict]:
    return [item for item in entry.get("snapshots") or [] if isinstance(item, dict)]


def _instant(value: object) -> datetime | None:
    """A ``generated_at`` as an instant (a naive one read as UTC), or None when it is not one."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _stored(cache: object, key: str) -> list[tuple[object, datetime | None]]:
    """The ``generated_at`` of each snapshot the cache keeps for a race, oldest stored first, with its instant."""
    order = _race_order(key)
    entries = cache.get("entries") if isinstance(cache, dict) else None
    entry = entries.get(None if order[0] else f"{order[1]}:{order[2]}") if isinstance(entries, dict) else None
    snapshots = entry.get("snapshots") if isinstance(entry, dict) else None
    results = [
        item["result"] for item in snapshots or [] if isinstance(item, dict) and isinstance(item.get("result"), dict)
    ]
    return [(result.get("generated_at"), _instant(result.get("generated_at"))) for result in results]


def _verdict(call: dict, stored: list[tuple[object, datetime | None]], graded: dict) -> tuple[str, str] | None:
    """Whether a history call is dropped, kept or refused, and why; None when the cache stores it."""
    moment = _instant(call.get("generated_at"))
    if moment is None:
        return KEEP, UNREADABLE_CALL
    instants = [instant for _, instant in stored]
    if moment in instants:
        return None
    if None in instants:
        return KEEP, UNREADABLE_STORED
    # The cache keeps a race's last SNAPSHOT_HISTORY_LIMIT snapshots plus the newest of each phase:
    # one pinned from before that window says nothing about what was trimmed after it.
    window = [(stamp, instant) for stamp, instant in stored[-SNAPSHOT_HISTORY_LIMIT:] if instant is not None]
    oldest, oldest_at = min(window, key=lambda pair: pair[1])
    if moment < oldest_at:
        return KEEP, f"predates the oldest kept snapshot ({oldest}); it may have been shown and trimmed since"
    if call is graded:
        phase, stamp = call.get("prediction_phase"), call.get("generated_at")
        return REFUSE, f"never stored, but dropping it changes the race's graded call ({phase} {stamp})"
    return DROP, f"newer than the oldest kept snapshot ({oldest}) and matches none of the {len(stored)} stored"


def _notes(key: str, entry: dict, stored: list[tuple[object, datetime | None]]) -> list[CallNote]:
    """Every call of a race that matches no stored snapshot; none when the cache keeps nothing for it."""
    if not stored:
        return []
    graded = graded_call(entry)
    verdicts = [(call, _verdict(call, stored, graded)) for call in _calls(entry)]
    return [CallNote(key, call, *verdict) for call, verdict in verdicts if verdict is not None]


def _repaired(entry: dict, notes: list[CallNote]) -> dict:
    """The entry with its graded fields reset and its dropped calls gone.

    A dropped call is never the graded call (that one is refused), so dropping it leaves the graded fields alone.
    """
    graded = with_graded_fields(entry)
    dropped = {id(note.call) for note in notes if note.verdict == DROP}
    if not dropped:
        return graded
    return {**graded, "snapshots": [item for item in entry["snapshots"] if id(item) not in dropped]}


def plan(history: dict, cache: object) -> RepairPlan:
    """The repaired history: graded fields reset, and the calls the cache proves were never stored dropped."""
    races = sorted((key for key, entry in history.items() if isinstance(entry, dict)), key=_race_order)
    stored = {key: _stored(cache, key) for key in races}
    notes = {key: _notes(key, history[key], stored[key]) for key in races}
    repaired = {key: _repaired(entry, notes[key]) if key in notes else entry for key, entry in history.items()}
    every = [note for key in races for note in notes[key]]
    return RepairPlan(
        repaired=repaired,
        changes=[
            RaceChange(key=key, before=_call_fields(history[key]), after=_call_fields(repaired[key]))
            for key in races
            if _call_fields(history[key]) != _call_fields(repaired[key])
        ],
        dropped=[note for note in every if note.verdict == DROP],
        kept=[note for note in every if note.verdict == KEEP],
        refused=[note for note in every if note.verdict == REFUSE],
        uncached=[(key, len(_calls(history[key]))) for key in races if _calls(history[key]) and not stored[key]],
    )


def _label(key: str) -> str:
    order = _race_order(key)
    return key if order[0] else f"R{order[2]} {key}"


def _position(value: object) -> str:
    return "-" if value is None else str(value)


def _move(was: object, now: object) -> float:
    """How far a driver moves between two calls; a driver new to the call moves furthest."""
    if isinstance(was, int | float) and isinstance(now, int | float):
        return abs(now - was)
    return float("inf")


def describe(change: RaceChange) -> list[str]:
    """Two lines: the phase and stamp before and after, then the drivers that move."""
    before, after = change.before, change.after
    header = (
        f"  {_label(change.key)}  {before.get('prediction_phase') or '-'} {before.get('generated_at') or '-'}"
        f" -> {after.get('prediction_phase') or '-'} {after.get('generated_at') or '-'}"
    )
    was = before.get("predicted_positions") or {}
    now = after.get("predicted_positions") or {}
    moved = sorted(
        (code for code in now if was.get(code) != now[code]),
        key=lambda code: (-_move(was.get(code), now[code]), code),
    )
    if not moved:
        return [header, "      no driver moves"]
    shown = ", ".join(f"{code} P{_position(was.get(code))} -> P{now[code]}" for code in moved[:DRIVERS_SHOWN])
    return [header, f"      {shown}  ({len(moved)} of {len(now)} drivers move)"]


def _call_line(note: CallNote) -> str:
    call = note.call
    return (
        f"  {_label(note.key)}  {call.get('prediction_phase') or '-'} {call.get('generated_at') or '-'}  {note.reason}"
    )


def _section(header: str, lines: list[str]) -> list[str]:
    return [header, *lines] if lines else []


def report(result: RepairPlan, races: int) -> list[str]:
    """What a run prints about its plan: graded changes, drops, keeps, races the cache lacks, refusals."""
    return [
        *_section(
            f"{len(result.changes)} of {races} race(s) change their graded call:",
            [line for change in result.changes for line in describe(change)],
        ),
        *_section(
            f"{len(result.dropped)} call(s) never reached the snapshot cache and are dropped:",
            [_call_line(note) for note in result.dropped],
        ),
        *_section(
            f"{len(result.kept)} call(s) match no stored snapshot but are kept:",
            [_call_line(note) for note in result.kept],
        ),
        *_section(
            f"{len(result.uncached)} race(s) have no snapshot in the cache, so every call is kept:",
            [f"  {_label(key)}  {count} call(s)" for key, count in result.uncached],
        ),
        *_section(
            f"{len(result.refused)} call(s) never reached the snapshot cache, but dropping them changes a graded call:",
            [_call_line(note) for note in result.refused],
        ),
    ]


def _target_problem(local: bool) -> tuple[int, str] | None:
    """Why the configured store is not the one this run was aimed at, if it is not."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if local:
        return (EXIT_WRONG_STORE, LOCAL_WITH_DATABASE) if database_url else None
    if not database_url:
        return EXIT_NO_DATABASE, NO_DATABASE
    if document_store.health().backend != BACKEND_POSTGRES:
        return EXIT_WRONG_STORE, FELL_BACK
    return None


def _backup(name: str, document: object, backup_dir: Path) -> Path | None:
    """Copy a document to a timestamped file; None on failure."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"{name}-{stamp}.json"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, default=str), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: backup failed, nothing written: {exc}")
        return None
    return path


def _apply(documents: dict[str, object], result: RepairPlan, backup_dir: Path) -> int:
    """Back up both documents, check neither changed since it was read, then write the repaired history."""
    backups = {name: _backup(name, document, backup_dir) for name, document in documents.items()}
    if None in backups.values():
        return EXIT_STORE_ERROR

    for name, document in documents.items():
        again = document_store.read(name)
        if not again.ok or again.payload != document:
            print(f"ERROR: {name} changed while the repair was planned (or could not be read again); nothing written.")
            print("Run it again.")
            return EXIT_STORE_ERROR

    history_backup, cache_backup = backups[DOCUMENT_PREDICTION_HISTORY], backups[DOCUMENT_PREDICTION_CACHE]
    write = document_store.write(DOCUMENT_PREDICTION_HISTORY, result.repaired)
    if not write.ok:
        print(f"ERROR: write failed: {write.error}. The history as it was is in {history_backup}.")
        return EXIT_WRITE_FAILED
    print(
        f"\nrepaired {len(result.changes)} race(s) and dropped {len(result.dropped)} call(s);"
        f" backups: {history_backup}, {cache_backup}"
    )
    return EXIT_OK


def _repair(apply: bool, backup_dir: Path) -> int:
    """Read both documents, print the plan, and write it when asked to."""
    history_read = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not history_read.ok:
        print(f"ERROR reading the prediction history: {history_read.error}")
        return EXIT_STORE_ERROR
    history = history_read.payload
    if not history:
        print("no prediction history; nothing to repair.")
        return EXIT_OK
    cache_read = document_store.read(DOCUMENT_PREDICTION_CACHE)
    if not cache_read.ok:
        print(f"ERROR reading the prediction cache: {cache_read.error}")
        return EXIT_STORE_ERROR

    result = plan(history, cache_read.payload)
    for line in report(result, len(history)):
        print(line)
    if result.refused:
        print("\nREFUSED: a call never stored is its race's graded call; check those races by hand. Nothing written.")
        return EXIT_GRADED_CALL_WOULD_CHANGE
    if not result.changes and not result.dropped:
        print(f"{len(history)} race(s): every graded call is right and no call needs dropping; nothing to repair.")
        return EXIT_OK
    if not apply:
        print("\ndry run — re-run with --apply to back up both documents and write the history.")
        return EXIT_OK
    documents = {DOCUMENT_PREDICTION_HISTORY: history, DOCUMENT_PREDICTION_CACHE: cache_read.payload}
    return _apply(documents, result, backup_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="back up both documents, then write the repaired history")
    parser.add_argument("--local", action="store_true", help="repair the file store (DATABASE_URL must be unset)")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args(argv)

    problem = _target_problem(args.local)
    if problem is not None:
        code, message = problem
        print(f"ERROR: {message}")
        return code

    health = document_store.health()
    target = f"file ({PREDICTION_HISTORY_PATH})" if args.local else f"{health.backend} ({health.host_kind})"
    print(f"store: {target}")
    return _repair(args.apply, args.backup_dir)


if __name__ == "__main__":
    raise SystemExit(main())
