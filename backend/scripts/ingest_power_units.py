"""Collect the FIA's power-unit documents for a season into the shared store.

    cd backend
    python -m scripts.ingest_power_units                     # this season
    python -m scripts.ingest_power_units --year 2026 --all-events
    python -m scripts.ingest_power_units --cache-dir ~/fia-pdfs

A run reads the current event's page, plus the page of any event with nothing
collected yet — so the first run is the backfill — and downloads only the PDFs
it does not already hold, ten seconds apart as fia.com's robots.txt asks.
``--all-events`` re-walks every event page of the season, which is how a
document the FIA takes back after its weekend is noticed (the scheduled job
does this once a day).

Every run records its outcome — including a run that finds nothing new, and
one that cannot reach fia.com — in the ingest status document, which is the
screen's "last checked" line.

Writes wherever ``DATABASE_URL`` points: the shared Postgres document store,
or the local JSON fallback when it is unset — run with ``DATABASE_URL=`` to
collect into the local file without touching production.

Exit status: 0 when every document was collected and read; 1 when any could
not be (they are kept, and listed as unread on the screen); 2 when the store
or the FIA site could not be reached, in which case nothing was written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Must run before anything under ``app`` is imported: the document store picks
# its backend from ``DATABASE_URL`` at import time.
load_dotenv()

from app.data.power_units.fia_site import FetchError, PoliteFetcher
from app.data.power_units.ingest import IngestError, IngestReport, ingest_season
from app.data.power_units.sources import SourcesUnavailableError
from app.data.power_units.status import (
    OUTCOME_ABORTED,
    OUTCOME_DOCUMENT_FAILURES,
    OUTCOME_OK,
    OUTCOME_WRITE_FAILED,
    IngestStatus,
    record_status,
)

EXIT_OK = 0
EXIT_DOCUMENT_FAILURES = 1
EXIT_UNREACHABLE = 2


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect the FIA's power-unit documents into the store.")
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--all-events", action="store_true", help="re-walk every event page of the season")
    parser.add_argument("--cache-dir", type=Path, default=None, help="serve PDFs already downloaded to this folder")
    return parser.parse_args(argv)


def _print_report(report: IngestReport) -> None:
    print(f"{report.year}: checked {len(report.events_checked)} event(s): {', '.join(report.events_checked) or '-'}")
    print(f"  added {len(report.added)} document(s)")
    for title in report.added:
        print(f"    + {title}")
    for failure in report.failed:
        print(f"    ! {failure}")
    for title in report.withdrawn:
        print(f"    - withdrawn by the FIA: {title}")
    if report.allowances_changed:
        print(f"  allowances updated from the FIA's reports: {', '.join(report.allowances_changed)}")
    if report.write_error:
        print(f"  store write FAILED: {report.write_error}")
    elif report.written:
        print("  store updated")
    else:
        print("  nothing new — store unchanged")


def _outcome(report: IngestReport) -> str:
    if report.write_error:
        return OUTCOME_WRITE_FAILED
    return OUTCOME_OK if report.ok else OUTCOME_DOCUMENT_FAILURES


def _record(status: IngestStatus, *, changed: bool) -> None:
    result = record_status(status, changed=changed)
    if not result.ok:
        print(f"  WARNING: the run's status could not be recorded: {result.error}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fetcher = PoliteFetcher(cache_dir=args.cache_dir)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        report = ingest_season(args.year, fetcher, all_events=args.all_events)
    except SourcesUnavailableError as exc:
        # The store itself is down, so there is nowhere to record the run either.
        print(f"Ingest aborted, nothing written: {exc}")
        return EXIT_UNREACHABLE
    except (IngestError, FetchError) as exc:
        print(f"Ingest aborted, nothing written: {exc}")
        _record(
            IngestStatus(args.year, started, OUTCOME_ABORTED, error=f"fia.com could not be read: {exc}"),
            changed=False,
        )
        return EXIT_UNREACHABLE
    _print_report(report)
    print(f"  {fetcher.requests_made} request(s) to fia.com")
    _record(
        IngestStatus(
            args.year,
            started,
            _outcome(report),
            added=len(report.added),
            failed=len(report.failed),
            withdrawn=len(report.withdrawn),
        ),
        changed=report.written,
    )
    return EXIT_OK if report.ok else EXIT_DOCUMENT_FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
