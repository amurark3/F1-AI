"""Repair: reset each race's graded call in prediction history from its stored calls.

Until P0b.9, ``save_prediction`` set a race's top-level ``predicted_positions``
(with ``risk_predictions``, ``prediction_phase``, ``generated_at`` and
``data_sources``) to whichever call was computed last, of either phase, so R20
São Paulo was graded on a pre-qualifying call (VER P2) instead of the
post-qualifying one the site showed (VER P8). This sets those fields to each
race's graded call (``app.data.predictions.graded``: the latest
post-qualifying call when the race has one, else its latest pre-qualifying
call), and touches nothing else: the stored calls and the recorded results stay
exactly as they are.

    cd backend
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.repair_graded_predictions          # dry run
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.repair_graded_predictions --apply  # writes

A dry run lists every race whose graded call changes, with its phase before
and after and the drivers that move. ``--apply`` copies the history document
to ``--backup-dir`` first, reads it again and writes only if nothing changed
in between. A second run finds nothing to repair.

``DATABASE_URL`` comes from the environment only. Unlike the older scripts
this one never reads ``backend/.env``, which points at production, so a write
always goes where it was deliberately aimed. ``--local`` aims it at the file
store instead (``PREDICTION_HISTORY_PATH``, default
``data/prediction_history.json``), and only with no ``DATABASE_URL``:

    DATABASE_URL= PREDICTION_HISTORY_PATH=/tmp/copy.json .venv/bin/python -m scripts.repair_graded_predictions --local

Exit status: 0 done, nothing to repair, or a dry run; 1 the write failed (the
backup holds the document as it was); 2 the history could not be read or
backed up, or it changed during the run; 3 no ``DATABASE_URL``; 4 the store is
not the one asked for.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from app.config import PREDICTION_HISTORY_PATH
from app.data.predictions.graded import CALL_FIELDS, with_graded_fields
from app.data.store import BACKEND_POSTGRES, DOCUMENT_PREDICTION_HISTORY, document_store

EXIT_OK = 0
EXIT_WRITE_FAILED = 1
EXIT_STORE_ERROR = 2
EXIT_NO_DATABASE = 3
EXIT_WRONG_STORE = 4

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


@dataclass(frozen=True)
class RaceChange:
    """One race whose top-level call fields change: before and after."""

    key: str
    before: dict
    after: dict


def _race_order(key: str) -> tuple[int, int, int, str]:
    """Calendar order for ``"(year,round)"`` keys; anything else sorts last."""
    try:
        year, round_num = (int(part) for part in key.strip("()").split(","))
    except ValueError:
        return (1, 0, 0, key)
    return (0, year, round_num, key)


def _call_fields(entry: dict) -> dict:
    return {field: entry.get(field) for field in CALL_FIELDS}


def plan(history: dict) -> tuple[dict, list[RaceChange]]:
    """The repaired document, and the races whose graded call changes in it."""
    repaired = {key: with_graded_fields(entry) if isinstance(entry, dict) else entry for key, entry in history.items()}
    changes = [
        RaceChange(key=key, before=_call_fields(history[key]), after=_call_fields(repaired[key]))
        for key in sorted(history, key=_race_order)
        if isinstance(history[key], dict) and _call_fields(history[key]) != _call_fields(repaired[key])
    ]
    return repaired, changes


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


def _backup(history: dict, backup_dir: Path) -> Path | None:
    """Copy the history document to a timestamped file; None on failure."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"prediction_history-{stamp}.json"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history, default=str), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: backup failed, nothing written: {exc}")
        return None
    return path


def _apply(history: dict, repaired: dict, changes: int, backup_dir: Path) -> int:
    """Back up, check the document is unchanged, then write the repair."""
    backup = _backup(history, backup_dir)
    if backup is None:
        return EXIT_STORE_ERROR

    again = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not again.ok or again.payload != history:
        print("ERROR: the history changed while the repair was planned (or could not be read again); nothing written.")
        print("Run it again.")
        return EXIT_STORE_ERROR

    write = document_store.write(DOCUMENT_PREDICTION_HISTORY, repaired)
    if not write.ok:
        print(f"ERROR: write failed: {write.error}. The document as it was is in {backup}.")
        return EXIT_WRITE_FAILED
    print(f"\nrepaired {changes} race(s); backup: {backup}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="back up the history document, then write the repair")
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

    read = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not read.ok:
        print(f"ERROR reading the prediction history: {read.error}")
        return EXIT_STORE_ERROR
    history = read.payload
    if not history:
        print("no prediction history; nothing to repair.")
        return EXIT_OK

    repaired, changes = plan(history)
    if not changes:
        print(f"{len(history)} race(s): every graded call is already right; nothing to repair.")
        return EXIT_OK

    print(f"{len(changes)} of {len(history)} race(s) change their graded call:")
    for change in changes:
        print("\n".join(describe(change)))

    if not args.apply:
        print("\ndry run — re-run with --apply to back up the document and write.")
        return EXIT_OK

    return _apply(history, repaired, len(changes), args.backup_dir)


if __name__ == "__main__":
    raise SystemExit(main())
