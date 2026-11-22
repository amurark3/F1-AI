"""Where a tool's answer came from: a subject, source chips and an optional chart.

Every figure here is read from the data the tool itself read, never written by the model.
A ``Sourced`` is the tool's text as a plain ``str`` with that provenance attached, so every
caller that reads the text (the model, the claim checker, the eval) is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

from app.data.f1db_source import installed_version

if TYPE_CHECKING:
    from collections.abc import Iterable

SOURCE_NAMES = {
    "f1db": "f1db",
    "fia-final-classification": "FIA final classification",
    "openf1-session-result": "OpenF1 session results",
    "jolpica-qualifying": "Jolpica qualifying",
}
CHIP_SEPARATOR = " · "


@dataclass(frozen=True)
class ReachRow:
    key: str
    name: str
    team: str
    points: float
    #: ``points`` plus the most the row can still score.
    max: float


@dataclass(frozen=True)
class ReachChart:
    title: str
    championship: Literal["drivers", "constructors"]
    year: int
    rows: tuple[ReachRow, ...]
    kind: Literal["reach"] = "reach"


@dataclass(frozen=True)
class Provenance:
    sources: tuple[str, ...]
    subject: str | None = None
    chart: ReachChart | None = None


class Sourced(str):
    """A tool's text with its provenance attached; it reads as the plain text everywhere else."""

    provenance: Provenance

    def __new__(cls, text: str, provenance: Provenance) -> Self:
        instance = super().__new__(cls, text)
        instance.provenance = provenance
        return instance


def chip(source: str, *details: str | None, version: str | None = None) -> str:
    """One source chip: the source's name (and version), then each detail given."""
    name = SOURCE_NAMES.get(source, source)
    head = f"{name} {version}" if version else name
    return CHIP_SEPARATOR.join([head, *(detail for detail in details if detail)])


def f1db_chip(*details: str | None) -> str:
    return chip("f1db", *details, version=installed_version())


def classification_chips(sources: Iterable[dict], *, final: bool) -> tuple[str, ...]:
    """One chip per source of a session result; a provisional table says so."""
    return tuple(
        chip(
            source["source"],
            f"doc {source['document']}" if source.get("document") else None,
            None if final else "provisional",
            version=source.get("version") or (installed_version() if source["source"] == "f1db" else None),
        )
        for source in sources
    )
