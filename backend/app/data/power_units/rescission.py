"""Documents the FIA takes back, and documents that say they do.

The FIA withdraws a document in one of four ways, and the collection notices
each:

1. it takes the document off the event page — :mod:`.ingest` records the
   stored copy as withdrawn the next time it reads the page;
2. it keeps the listing but marks it — a title carrying "Withdrawn" or
   "Rescinded" — which :func:`marks_withdrawn` recognises;
3. it publishes a document saying so — "Document 44 is withdrawn", "This
   decision replaces Document 37", "the decisions in Documents 51 and 52 are
   rescinded" — whose referenced numbers :func:`withdrawn_numbers` reads, so
   the referenced documents of the same event stop counting;
4. it reissues a decision as "Corrected …" without saying what it replaces —
   matched to the original where decisions are compared
   (:mod:`app.services.power_units.evidence`).

None of these deletes anything: a withdrawn document is kept, excluded from
every count, and listed on the screen with the reason.
"""

from __future__ import annotations

import re

# Inflected forms only: "replacement driver" is everyday B8.2.7 vocabulary and
# must not read as "replaces".
_VERB = (
    r"(?:withdr[ae]w(?:n|s|al|ing)?|rescind(?:s|ed|ing)?|revok(?:es|ed|ing)|revocation"
    r"|cancel(?:s|led|ed|ling|ing)?|annul(?:s|led|ment)?|replac(?:es|ed|ing)|supersed(?:es|ed|ing)|void(?:s|ed)?)\b"
)
_DOCUMENTS = re.compile(
    r"\bDoc(?:ument)?s?\.?\s*(?:No\.?\s*)?(?P<numbers>\d{1,3}(?:\s*(?:,|and|&)\s*\d{1,3})*)",
    re.IGNORECASE,
)
_WITHDRAWING = re.compile(r"\b" + _VERB, re.IGNORECASE)
# A competitor withdrawing its own petition, request or appeal (Mercedes at
# Monaco 2026: "withdrawing the petition for Review in respect of the decisions
# of the Stewards") takes back nothing the FIA published.
_PETITION = re.compile(
    r"\bwithdr[ae]w\w*\s+(?:(?:the|its|their|a)\s+)?(?:petition|request|appeal|notice\s+of\s+appeal|right\s+of\s+review)",
    re.IGNORECASE,
)
# How far either side of a reference a verb may sit and still be about it.
_REACH = 80
_TITLE_MARK = re.compile(r"\b(?:withdrawn|rescinded|revoked|cancell?ed|annulled|void(?:ed)?)\b", re.IGNORECASE)
_TITLE_NOTICE = re.compile(r"\b(?:withdraw\w*|rescind\w*|revoc\w*|revok\w*|annul\w*)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d{1,3}")


def marks_withdrawn(title: str) -> bool:
    """Whether an event-page title marks its document as taken back."""
    return bool(_TITLE_MARK.search(title))


def is_withdrawal_notice_title(title: str) -> bool:
    """Whether a title announces a withdrawal, so the document is worth reading."""
    return bool(_TITLE_NOTICE.search(title))


def _withdrawing_nearby(flat: str, start: int, end: int) -> bool:
    """Whether a withdrawal verb sits in the same sentence as ``flat[start:end]``."""
    sentence_start = flat.rfind(".", 0, start) + 1
    sentence_end = flat.find(".", end)
    before = _PETITION.sub(" ", flat[max(sentence_start, start - _REACH) : start])
    after = _PETITION.sub(" ", flat[end : min(len(flat) if sentence_end < 0 else sentence_end, end + _REACH)])
    return bool(_WITHDRAWING.search(before) or _WITHDRAWING.search(after))


def withdrawn_numbers(text: str, own_number: int | None) -> frozenset[int]:
    """Document numbers ``text`` withdraws, rescinds or replaces.

    Every "Document N" reference is judged on its own sentence, in either
    order — "Document 44 is withdrawn", "this decision replaces Document 37" —
    so a reference beside another cannot hide it. Only numbers below the
    document's own count: a document can take back an earlier one, and
    "Document 45 replaces Document 37" must not read as 45 withdrawing itself.
    """
    flat = " ".join(text.split())
    found = {
        int(number)
        for match in _DOCUMENTS.finditer(flat)
        if _withdrawing_nearby(flat, match.start(), match.end())
        for number in _NUMBER.findall(match["numbers"])
    }
    return frozenset(number for number in found if own_number is None or number < own_number)
