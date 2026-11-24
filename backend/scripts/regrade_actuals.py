"""Regrade: re-record the results of races graded before results carried a source (D1.8).

Until D1.8 a race's actuals came from FastF1's session results, which on the
morning after a race are Jolpica's pre-penalty order (Mexico City 2026 graded
Piastri 7th, Colapinto 8th and Gasly 10th; the final classification has them
13th, 15th and 17th), and stored no source. Results recorded from now on carry
``actual_source`` and ``actual_provisional`` and are confirmed by the app itself
(``app.data.predictions.history``). This script re-reads every race recorded
without them from ``race_classification()`` (OpenF1, then Jolpica) and records
it as provisional, so the app confirms it a day later. The stored calls and the
graded call are not touched, and a race the feeds publish no classification for
is left as it is.

    cd backend
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.regrade_actuals          # dry run
    DATABASE_URL='<target database URL>' .venv/bin/python -m scripts.regrade_actuals --apply  # writes

A dry run lists each race it would regrade with the drivers whose place or
status changes. ``--apply`` copies the history to ``--backup-dir`` first, reads
it again and writes only if it did not change in between. A second run finds
nothing to regrade. ``DATABASE_URL`` comes from the environment only, as in
``scripts.repair_graded_predictions``, whose ``--local`` and exit statuses apply
(1 write failed, 2 history unreadable or changed during the run, 3 no
``DATABASE_URL``, 4 wrong store).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.data.predictions.history import actual_fields, reason_fields, reasons_missing
from app.data.race_classification import race_classification
from app.data.store import DOCUMENT_PREDICTION_HISTORY, document_store
from scripts.repair_graded_predictions import (
    DEFAULT_BACKUP_DIR,
    EXIT_OK,
    EXIT_STORE_ERROR,
    EXIT_WRITE_FAILED,
    _backup,
    _label,
    _race_order,
    _target_problem,
)

# How many changed drivers a race's line shows.
DRIVERS_SHOWN = 8


def _year_round(key: str) -> tuple[int, int] | None:
    order = _race_order(key)
    return None if order[0] else (order[1], order[2])


def _legacy(entry: object) -> bool:
    """A race with a recorded result that carries no source: graded before D1.8."""
    return isinstance(entry, dict) and bool(entry.get("actual_positions")) and "actual_provisional" not in entry


def _reasonless(entry: object) -> bool:
    """A race with a recorded result whose retirements carry no reason: graded before f1db published them."""
    return isinstance(entry, dict) and bool(entry.get("actual_positions")) and reasons_missing(entry)


def _changes(entry: dict, fields: dict) -> list[str]:
    """The drivers whose place or status differs between the stored result and ``fields``."""
    old_positions, old_statuses = entry["actual_positions"], entry.get("actual_statuses") or {}
    lines = []
    for code, place in fields["actual_positions"].items():
        before = (old_positions.get(code), old_statuses.get(code))
        after = (place, fields["actual_statuses"][code])
        if before != after:
            lines.append(f"{code} P{before[0] or '-'} {before[1] or '-'} -> P{place} {after[1]}")
    return lines


def _add_reasons(entry: dict, parsed: tuple[int, int], label: str) -> tuple[dict | None, list[str]]:
    """A recorded result with the reasons f1db now publishes, and its report lines.

    The result itself is never replaced: the places, statuses and provenance stay.
    A race whose reasons are still unknown is left out, so a second run lists nothing.
    """
    classification = race_classification(*parsed)
    if not classification.drivers:
        return None, [f"  {label}  no classification published; left as it is"]
    fields = reason_fields(entry, classification)
    if fields is None:
        return None, [f"  {label}  the published result differs from the stored result; reasons not recorded"]
    if fields["actual_reasons"] == entry.get("actual_reasons") and fields["actual_incidents"] == entry.get(
        "actual_incidents"
    ):
        return None, []
    stored = entry.get("actual_reasons") or {}
    added = [
        f"{code} {entry['actual_statuses'][code]} -> {entry['actual_statuses'][code]} · {reason}"
        for code, reason in fields["actual_reasons"].items()
        if reason and stored.get(code) != reason
    ]
    header = f"  {label}  reasons from {classification.source}: {len(added)} driver(s) get a reason"
    return {**entry, **fields}, [header, *(f"      {line}" for line in added[:DRIVERS_SHOWN])]


def plan(history: dict) -> tuple[dict, list[str]]:
    """The regraded history and the report lines for every legacy race and every race missing reasons."""
    regraded, report = dict(history), []
    for key in sorted(history, key=_race_order):
        parsed = _year_round(key)
        if parsed is None:
            continue
        if not _legacy(history[key]):
            if _reasonless(history[key]):
                updated, lines = _add_reasons(history[key], parsed, _label(key))
                regraded[key] = updated or history[key]
                report.extend(lines)
            continue
        classification = race_classification(*parsed)
        if not classification.drivers:
            report.append(f"  {_label(key)}  no classification published; left as it is")
            continue
        fields = actual_fields(history[key], classification)
        regraded[key] = {**history[key], **fields}
        changed = _changes(history[key], fields)
        report.append(f"  {_label(key)}  from {classification.source}: {len(changed)} driver(s) change")
        report.extend(f"      {line}" for line in changed[:DRIVERS_SHOWN])
    return regraded, report


def _apply(history: dict, regraded: dict, backup_dir: Path) -> int:
    backup = _backup(DOCUMENT_PREDICTION_HISTORY, history, backup_dir)
    if backup is None:
        return EXIT_STORE_ERROR
    again = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not again.ok or again.payload != history:
        print("ERROR: the history changed while the regrade was planned (or could not be read again); nothing written.")
        return EXIT_STORE_ERROR
    write = document_store.write(DOCUMENT_PREDICTION_HISTORY, regraded)
    if not write.ok:
        print(f"ERROR: write failed: {write.error}. The history as it was is in {backup}.")
        return EXIT_WRITE_FAILED
    print(f"\nregraded; backup: {backup}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="back up the history, then write the regraded one")
    parser.add_argument("--local", action="store_true", help="regrade the file store (DATABASE_URL must be unset)")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args(argv)

    problem = _target_problem(args.local)
    if problem is not None:
        print(f"ERROR: {problem[1]}")
        return problem[0]
    read = document_store.read(DOCUMENT_PREDICTION_HISTORY)
    if not read.ok:
        print(f"ERROR reading the prediction history: {read.error}")
        return EXIT_STORE_ERROR
    history = read.payload if isinstance(read.payload, dict) else {}
    regraded, report = plan(history)
    if not report:
        print("no race was recorded without a source; nothing to regrade.")
        return EXIT_OK
    print("races recorded without a source:")
    print("\n".join(report))
    if regraded == history:
        print("nothing changes.")
        return EXIT_OK
    if not args.apply:
        print("\ndry run — re-run with --apply to back up the history and write it.")
        return EXIT_OK
    return _apply(history, regraded, args.backup_dir)


if __name__ == "__main__":
    raise SystemExit(main())
