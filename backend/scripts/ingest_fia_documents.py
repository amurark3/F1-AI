"""Collect every FIA document of a season into the FIA document store.

    cd backend
    python -m scripts.ingest_fia_documents                       # this season
    python -m scripts.ingest_fia_documents --year 2026 --all-events
    python -m scripts.ingest_fia_documents --max-new-events 2    # backfill two past events per run
    python -m scripts.ingest_fia_documents --cache-dir ~/fia-pdfs
    python -m scripts.ingest_fia_documents --require-database    # a scheduled job

A run reads the current event's page, plus the page of each event with nothing
collected yet, and downloads only the PDFs it does not already hold, ten
seconds apart as fia.com's robots.txt asks. A full season from nothing is
about 1,800 documents, five hours; ``--max-new-events`` spreads that backfill
over several runs. ``--all-events`` re-walks every event page of the season,
which is how a document the FIA takes back after its weekend is noticed.

Writes wherever ``DATABASE_URL`` points: the ``fia_documents`` Postgres table,
or one JSON file per season under ``FIA_DOCUMENTS_DIR`` when it is unset.
``--require-database`` refuses that fallback, as the power-unit job does (see
``scripts.ingest_power_units`` for why a runner's disk is a trap).

Exit status: 0 when every document was collected and read; 1 when any could
not be (they are kept without text and tried again later); 2 when the store or
the FIA site could not be reached, in which case this event's work was not
written; 3 when ``--require-database`` finds no usable database.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# Must run before anything under ``app`` is imported: the store picks its
# backend from ``DATABASE_URL`` at import time.
load_dotenv()

from app.data.fia_documents.ingest import IngestReport, ingest_season
from app.data.fia_documents.kinds import document_kind
from app.data.fia_documents.listing import IngestError
from app.data.fia_documents.site import FetchError, PoliteFetcher
from app.data.fia_documents.store import FiaStoreError
from scripts.ingest_power_units import (
    EXIT_DOCUMENT_FAILURES,
    EXIT_NO_DATABASE,
    EXIT_OK,
    EXIT_UNREACHABLE,
    database_problem,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect every FIA document of a season into the store.")
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--all-events", action="store_true", help="re-walk every event page of the season")
    parser.add_argument(
        "--max-new-events",
        type=int,
        default=None,
        help="start at most this many events with nothing collected yet (default: all)",
    )
    parser.add_argument("--cache-dir", type=Path, default=None, help="serve PDFs already downloaded to this folder")
    parser.add_argument(
        "--require-database",
        action="store_true",
        help="refuse to run unless DATABASE_URL points at a Postgres this machine can reach",
    )
    return parser.parse_args(argv)


def _print_report(report: IngestReport) -> None:
    print(f"{report.year}: checked {len(report.events_checked)} event(s): {', '.join(report.events_checked) or '-'}")
    print(f"  added {len(report.added)} document(s)")
    for title in report.added:
        print(f"    + [{document_kind(title)}] {title}")
    for failure in report.failed:
        print(f"    ! {failure}")
    for title in report.withdrawn:
        print(f"    - withdrawn by the FIA: {title}")
    if report.deferred:
        print(f"  left for a later run (nothing collected yet): {', '.join(report.deferred)}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    problem = database_problem() if args.require_database else None
    if problem:
        print(f"Ingest refused: {problem}")
        return EXIT_NO_DATABASE
    fetcher = PoliteFetcher(cache_dir=args.cache_dir)
    try:
        report = ingest_season(args.year, fetcher, all_events=args.all_events, max_new_events=args.max_new_events)
    except (FiaStoreError, IngestError, FetchError) as exc:
        print(f"Ingest aborted: {exc}")
        return EXIT_UNREACHABLE
    _print_report(report)
    print(f"  {fetcher.requests_made} request(s) to fia.com")
    return EXIT_OK if report.ok else EXIT_DOCUMENT_FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
