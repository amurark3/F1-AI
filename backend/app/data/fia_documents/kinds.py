"""What kind of document an FIA title announces.

Computed from the listed title at read time, never stored, so a fix here
applies to every document already collected. The first matching rule wins, and
the order matters: a lap deletion is published as an "Infringement", a driver
change and a permission to start as a "Decision", and a car's parc fermé
infringement is a penalty even though other parc fermé documents are grid
documents.

A penalty names a car ("Car 81", or "car 98" when a team is summoned over
it): a stewards' decision about reference times, or the technical delegate's
"MGU-K Infringement, Car 30" report, is not one.
"""

from __future__ import annotations

import re

KIND_PENALTY = "penalty"
KIND_GRID = "grid"
KIND_CLASSIFICATION = "classification"
KIND_DELETED_LAPS = "deleted_laps"
KIND_ENTRY_LIST = "entry_list"
KIND_POWER_UNIT = "power_unit"
KIND_PIRELLI = "pirelli"
KIND_TIMETABLE = "timetable"
KIND_OTHER = "other"

# "Doc 44 - Corrected Infringement - …": the number and the correction say nothing about the kind.
_PREFIX = re.compile(r"^\s*(?:Doc\s+\d+\s*-\s*)?(?:Corrected\s+)?", re.IGNORECASE)
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.IGNORECASE))
    for kind, pattern in (
        (KIND_DELETED_LAPS, r"\bdeleted\s+lap"),
        (KIND_ENTRY_LIST, r"\bentry\s+list|\bdriver\s+change"),
        (KIND_GRID, r"\bstarting\s+grid|\bpermission\s+to\s+start"),
        (KIND_PENALTY, r"^(?:infring\w*|summons|decision|offence)\b.*\bcar\s+\d+"),
        (KIND_CLASSIFICATION, r"\bclassification\b"),
        (KIND_GRID, r"\bparc\s+ferm"),
        (KIND_POWER_UNIT, r"\b(?:PU|power\s+unit)\s+elements\b"),
        (KIND_PIRELLI, r"\bpirelli\b"),
        (KIND_TIMETABLE, r"\btimetable\b"),
    )
)


def document_kind(title: str) -> str:
    """One of the ``KIND_*`` values; ``KIND_OTHER`` for notes, reports and procedures."""
    subject = _PREFIX.sub("", title)
    return next((kind for kind, rule in _RULES if rule.search(subject)), KIND_OTHER)
