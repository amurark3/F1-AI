"""Clean-up helpers for text extracted from FIA PDFs.

pypdf reproduces the FIA's documents faithfully enough to parse, with two
habits every parser here has to survive:

* words split by a stray space — "Geor ge Russell", "Racin g Bulls",
  "Hülkenber g" — so a name is never matched as printed; :func:`compact`
  gives a key that ignores the damage;
* sentences broken across lines at arbitrary points, so every parser matches
  phrases with ``\\s+`` between words rather than single spaces.
"""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# The cover pages are typeset with non-breaking and other fixed-width spaces,
# which defeat any pattern written with an ordinary one ("GRAND PRIX").
_ODD_SPACES = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")
_ZERO_WIDTH = re.compile("[\u200b-\u200d\ufeff]")


class DocumentParseError(ValueError):
    """A power-unit document whose text does not have the shape its type promises.

    Raised rather than returning a partial result: a report read halfway would
    undercount someone's engines without anything on screen saying so. The
    caller records the document as unread instead, which the screen shows.
    """


def clean(text: str) -> str:
    """Ordinary spaces for typographic ones, and no zero-width characters."""
    return _ZERO_WIDTH.sub("", _ODD_SPACES.sub(" ", text))


def compact(text: str) -> str:
    """Lower-case letters and digits only, accents folded.

    ``compact("Ser gio Pérez") == compact("Sergio Perez") == "sergioperez"``.
    """
    folded = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return _NON_ALNUM.sub("", stripped.lower())


def squash(text: str) -> str:
    """Collapse every run of whitespace, line breaks included, to one space."""
    return " ".join(text.split())
