"""Show, pin and unpin the power-unit allowances the screen measures against.

Allowances live in the shared document store, not in code. The ingest job
keeps each element at the latest figure the FIA's own reports state ("the
fifth (5th) of the four (4) new internal combustion engines allowed"), with the
document that stated it. This CLI is for the rare case those reports are wrong
or late: a pinned figure is never overwritten by the job, and the screen shows
any disagreement between it and the FIA's latest statement.

Writes go wherever ``DATABASE_URL`` points, so a pin against the production
database changes the live screen with no redeploy. Every pin requires a
``--note`` saying why: an unattributed override is indistinguishable from an
invented number.

    cd backend
    python -m scripts.power_unit_allowances show --year 2026
    python -m scripts.power_unit_allowances pin --year 2026 --element ICE --allowance 5 \\
        --note "<why, with a citation>"
    python -m scripts.power_unit_allowances unpin --year 2026 --element ICE

Angle brackets above mark a value you must supply; a note still containing
them is refused, so a pasted example cannot land.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from app.data.store_types import WriteResult

# Must run before anything under ``app`` is imported: the document store picks
# its backend from ``DATABASE_URL`` at import time, so the app imports are
# deferred into the handlers below.
load_dotenv()

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_STORE = 2

# More than any season has allowed of any element; a typo guard, not a rule.
MAX_ALLOWANCE = 20


def _written(result: WriteResult) -> int:
    if not result.ok or not result.durable:
        print(f"ERROR: write did not land: {result.error or 'held in memory for retry'}")
        return EXIT_STORE
    print("Written.")
    return EXIT_OK


def _show(args: argparse.Namespace) -> int:
    from app.data.power_units.allowances import load_allowances

    entries = load_allowances(args.year)
    if not entries:
        print(f"No allowances stored for {args.year} yet — the next ingest run records them.")
        return EXIT_OK
    for code, entry in sorted(entries.items()):
        origin = entry.document_title or "—"
        print(f"{code:7} {entry.allowance:>2}  {entry.source:10}  {origin}  (updated {entry.updated_at})")
        if entry.note:
            print(f"        note: {entry.note}")
    return EXIT_OK


def _element(args: argparse.Namespace) -> str | None:
    from app.data.power_units.elements import canonical_code, elements_for

    code = canonical_code(args.element, args.year)
    if code is None:
        known = ", ".join(element.code for element in elements_for(args.year)) or "none"
        print(f"ERROR: {args.element!r} is not a {args.year} element (known: {known})")
    return code


def _pin(args: argparse.Namespace) -> int:
    from app.data.power_units.allowances import pin

    code = _element(args)
    if code is None:
        return EXIT_INVALID
    if not 0 <= args.allowance <= MAX_ALLOWANCE:
        print(f"ERROR: an allowance of {args.allowance} is outside 0–{MAX_ALLOWANCE}")
        return EXIT_INVALID
    note = args.note.strip()
    if not note or "<" in note or ">" in note:
        print("ERROR: --note must say why the figure is pinned, without placeholder brackets")
        return EXIT_INVALID
    return _written(pin(args.year, code, args.allowance, note))


def _unpin(args: argparse.Namespace) -> int:
    from app.data.power_units.allowances import unpin

    code = _element(args)
    if code is None:
        return EXIT_INVALID
    return _written(unpin(args.year, code))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="list the stored allowances and where each came from")
    show.add_argument("--year", type=int, required=True)
    show.set_defaults(handler=_show)

    pinned = sub.add_parser("pin", help="fix one element's allowance by hand")
    pinned.add_argument("--year", type=int, required=True)
    pinned.add_argument("--element", required=True, help="element code, e.g. ICE or PU-CE")
    pinned.add_argument("--allowance", type=int, required=True)
    pinned.add_argument("--note", required=True, help="why, with a citation")
    pinned.set_defaults(handler=_pin)

    unpinned = sub.add_parser("unpin", help="return an element to the FIA's stated figure")
    unpinned.add_argument("--year", type=int, required=True)
    unpinned.add_argument("--element", required=True)
    unpinned.set_defaults(handler=_unpin)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from app.data.power_units.sources import SourcesUnavailableError
    from app.data.store import document_store

    # Which store this lands in decides whether production changes; say so first.
    print(f"Document store backend: {document_store.health().backend}")
    try:
        return int(args.handler(args))
    except SourcesUnavailableError as exc:
        print(f"ERROR: the allowance document could not be read: {exc}")
        return EXIT_STORE


if __name__ == "__main__":
    raise SystemExit(main())
