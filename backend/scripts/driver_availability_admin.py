"""Record, list and clear per-weekend driver availability adjustments.

Between a withdrawal being announced and the weekend's first session producing
timing data, nothing in this stack knows a driver is out — FastF1 has no entry
list before the cars run and f1db only covers completed rounds. This CLI is the
manual bridge across that window.

Writes go to the shared document store, so pointing ``DATABASE_URL`` at the
production database updates the live grid with no redeploy. Every adjustment
requires a ``--reason`` and a ``--source`` because an unattributed override of
observed data is indistinguishable from invented data.

    cd backend
    python -m scripts.driver_availability_admin list --year 2026 --round 15
    python -m scripts.driver_availability_admin out --year 2026 --round 15 \\
        --driver HAD --reason "wrist injury" --source "<announcement-url>" \\
        --replacement-code <ABC> --replacement-name "<Full Name>" \\
        --replacement-team "Red Bull"

Angle brackets above mark values you must supply. They are rejected on write, so
a command pasted verbatim fails loudly instead of recording a fake stand-in.
    python -m scripts.driver_availability_admin clear --year 2026 --round 15 --driver HAD

An adjustment is superseded automatically once the real entry list exists, so
there is no need to clear it after the weekend runs.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

# The service loads its environment in main.py, which this CLI does not import.
# Without this the script would silently fall back to the local JSON file and
# report success while production kept serving the unadjusted grid.
#
# This must run before anything under ``app`` is imported: the document store
# picks its backend from ``DATABASE_URL`` at import time, so the app imports are
# deliberately deferred into the handlers below.
load_dotenv()


def _print_result(result) -> int:
    if not result.ok:
        print(f"ERROR: write failed: {result.error}")
        return 1
    if not result.durable:
        print("WARNING: write is not durable — it is held in memory and will retry")
        return 1
    print("Written.")
    return 0


def _list(args: argparse.Namespace) -> int:
    from app.data.driver_availability import load_weekend_availability

    availability = load_weekend_availability(args.year, args.round)
    if not availability.ok:
        print(f"ERROR: could not read availability document: {availability.error}")
        return 1
    if not availability.adjustments:
        print(f"No adjustments recorded for {args.year} round {args.round}.")
        return 0
    for adjustment in availability.adjustments:
        print(f"- {adjustment.describe()} (noted {adjustment.noted_at})")
    return 0


def _out(args: argparse.Namespace) -> int:
    from app.data.driver_availability import InvalidAdjustment, record_driver_out

    try:
        result = record_driver_out(
            year=args.year,
            round_num=args.round,
            driver_code=args.driver,
            reason=args.reason,
            source=args.source,
            replacement_code=args.replacement_code,
            replacement_name=args.replacement_name,
            replacement_team=args.replacement_team,
        )
    except InvalidAdjustment as exc:
        print(f"ERROR: {exc}")
        return 1
    return _print_result(result)


def _clear(args: argparse.Namespace) -> int:
    from app.data.driver_availability import InvalidAdjustment, clear_driver_adjustment

    try:
        result = clear_driver_adjustment(args.year, args.round, args.driver)
    except InvalidAdjustment as exc:
        print(f"ERROR: {exc}")
        return 1
    return _print_result(result)


def _add_round_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--round", type=int, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="show adjustments recorded for a round")
    _add_round_args(listing)
    listing.set_defaults(handler=_list)

    out = sub.add_parser("out", help="record a driver as withdrawn for a round")
    _add_round_args(out)
    out.add_argument("--driver", required=True, help="three-letter code, e.g. HAD")
    out.add_argument("--reason", required=True, help="why they are out, e.g. 'wrist injury'")
    out.add_argument("--source", required=True, help="URL or citation for the announcement")
    out.add_argument("--replacement-code", default="", help="three-letter code of the stand-in")
    out.add_argument("--replacement-name", default="")
    out.add_argument("--replacement-team", default="")
    out.set_defaults(handler=_out)

    clear = sub.add_parser("clear", help="remove a driver's adjustment for a round")
    _add_round_args(clear)
    clear.add_argument("--driver", required=True)
    clear.set_defaults(handler=_clear)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    # Which store this lands in decides whether production changes, so say it
    # out loud before doing anything rather than leaving it to be inferred.
    from app.data.store import document_store

    print(f"Document store backend: {document_store.health().backend}")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
