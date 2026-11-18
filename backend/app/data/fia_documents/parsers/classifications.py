"""Practice, qualifying and race classifications (provisional and final).

A row is two lines, the figures on the second::

    1 3 Max VERSTAPPEN
     Oracle Red Bull Racing 71 2:20:28.772 130.419 1:19.328 50 25
    13 81 Oscar PIASTRI *
     McLaren Mastercard F1 Team 71 2:20:58.247 29.475 0.837 129.964 1:20.690 52
    NOT CLASSIFIED
    41 Arvid LINDBLAD
     Visa Cash App Racing Bulls F1 Team 58 2:01:05.146 DNF 123.582 1:20.555 50
    DISQUALIFIED
    30 Liam LAWSON *
     Visa Cash App Racing Bulls F1 Team
    FASTEST LAP
    44 Lewis HAMILTON
     Scuderia Ferrari HP 1:19.268 on lap 50 195.468
    * PENALTIES
    Car 81 - 10 second time penalty - Causing a collision - Stewards' document no. 79

``*`` marks a car a penalty touched. The columns differ by session (the header
says which) and vary by row: the winner has no gap, P11 onwards no points, a
lapped car prints "1 LAP", a retirement prints ``DNF`` where the gap goes. So
the figures are read as a whole string by one pattern per session, not by
column. A team name may hold digits ("Cadillac Formula 1 Team"), so the team
is whatever precedes the trailing run of figure tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.fia_documents.parsers.fields import RuledNote, document_number, ruled_notes
from app.data.fia_documents.text import DocumentParseError, clean, squash

_TITLE = re.compile(r"^Title\s+(?P<title>.+)$", re.MULTILINE)
_HEADER = re.compile(r"^NO\s+DRIVER\s+NAT\s+ENTRANT\s+(?P<columns>.+)$", re.MULTILINE)
_END = re.compile(r"^(?:Timekeeper|The F1 FORMULA 1 logo)")
_HEADINGS = {
    "NOT CLASSIFIED": "not_classified",
    "DISQUALIFIED": "disqualified",
    "DID NOT START": "did_not_start",
    "FASTEST LAP": "fastest_lap",
    "POLE POSITION LAP": "pole",
    "* PENALTIES": "penalties",
}
_ROW = re.compile(r"^(?:(?P<position>\d+)\s+)?(?P<car>\d+)\s+(?P<driver>\D.*?)(?P<penalised>\s+\*)?$")
_VALUE = re.compile(r"[\d:.]+|D[A-Z]{2}|LAPS?")
_LAP_TIME = r"\d+(?::\d{2}){1,2}\.\d{3}"
_GAP = r"D[A-Z]{2}|\d+ LAPS?|\d+(?::\d{2})?\.\d{3}"
_GAPS = rf"(?:(?P<gap>{_GAP}) (?:(?P<interval>{_GAP}) )?)?"
_TIME_OF_DAY = r"\d+:\d{2}:\d{2}"
_SESSION_FIGURES = {
    "race": re.compile(
        rf"(?P<laps>\d+) (?P<time>{_LAP_TIME}) {_GAPS}\d+\.\d{{3}} (?P<fastest>{_LAP_TIME}) \d+(?: (?P<points>\d+))?"
    ),
    # A car that ran but set no time prints its lap count alone ("Audi Revolut F1 Team 2").
    "practice": re.compile(
        rf"(?:(?P<time>{_LAP_TIME}) (?P<laps>\d+) {_GAPS}\d+\.\d{{3}} {_TIME_OF_DAY}|(?P<untimed_laps>\d+))"
    ),
    "qualifying": re.compile(
        rf"(?P<q1>{_LAP_TIME}) \d+ \d+\.\d{{3}} {_TIME_OF_DAY}"
        rf"(?: (?P<q2>{_LAP_TIME}) \d+ {_TIME_OF_DAY}(?: (?P<q3>{_LAP_TIME}) \d+ {_TIME_OF_DAY})?)?"
    ),
}
_FASTEST = re.compile(rf"^(?P<team>.+?)\s+(?P<time>{_LAP_TIME})(?: on lap (?P<lap>\d+))?\s+\d+\.\d{{3}}(?: KM/H)?$")
_SESSION_WORDS = re.compile(r"\b(?:Provisional|Final|Classification)\b\s*")


@dataclass(frozen=True)
class ClassifiedEntry:
    #: ``None`` for a car with no place: not classified, disqualified, did not start.
    position: int | None
    car: int
    #: As printed: "Max VERSTAPPEN".
    driver: str
    team: str
    #: ``classified``, ``not_classified``, ``disqualified`` or ``did_not_start``.
    status: str
    #: What the gap column printed instead of a gap: "DNF".
    reason: str | None
    #: Practice and race only.
    laps: int | None
    #: Practice: best lap, ``None`` for a car that set no time. Race: total time.
    time: str | None
    gap: str | None
    interval: str | None
    #: Race only; none past P10.
    points: int | None
    #: Race only: the car's fastest lap.
    fastest: str | None
    #: Qualifying only: the time set in each part, ``None`` where the car did not reach it.
    q1: str | None
    q2: str | None
    q3: str | None
    #: Marked ``*``: a penalty touched this car.
    penalised: bool


@dataclass(frozen=True)
class FastestLap:
    car: int
    driver: str
    team: str
    time: str
    #: Race only.
    lap: int | None


@dataclass(frozen=True)
class Classification:
    document: int | None
    #: What the title names: "Free Practice 1", "Qualifying", "Race", "Sprint Race" ….
    session: str
    #: ``Final`` in the title; a provisional classification and a practice one are not final.
    final: bool
    entries: tuple[ClassifiedEntry, ...]
    penalties: tuple[RuledNote, ...]
    fastest_lap: FastestLap | None


def _session_kind(columns: str) -> str:
    if re.search(r"\bQ1\b", columns):
        return "qualifying"
    if columns.startswith("LAPS"):
        return "race"
    if columns.startswith("TIME"):
        return "practice"
    raise DocumentParseError(f"unknown classification columns: {columns!r}")


def _split_figures(line: str) -> tuple[str, str]:
    """``"Cadillac Formula 1 Team 71 2:20:59.467"`` → team and the figure string."""
    tokens = line.split()
    cut = len(tokens)
    while cut and _VALUE.fullmatch(tokens[cut - 1]):
        cut -= 1
    if not cut:
        raise DocumentParseError(f"no team on {line!r}")
    return " ".join(tokens[:cut]), " ".join(tokens[cut:])


def _entry(row: re.Match[str], line: str, kind: str, status: str) -> ClassifiedEntry:
    team, figures = _split_figures(line)
    if figures:
        match = _SESSION_FIGURES[kind].fullmatch(figures)
        if match is None:
            raise DocumentParseError(f"unreadable {kind} figures {figures!r}")
        found = match.groupdict()
    elif status == "classified":
        raise DocumentParseError(f"classified car {row['car']} has no figures")
    else:
        found = {}
    gap = found.get("gap")
    reason = gap if gap and gap.startswith("D") else None
    points = found.get("points")
    laps = found.get("laps") or found.get("untimed_laps")
    return ClassifiedEntry(
        position=int(row["position"]) if row["position"] else None,
        car=int(row["car"]),
        driver=row["driver"],
        team=team,
        status=status,
        reason=reason,
        laps=int(laps) if laps else None,
        time=found.get("time"),
        gap=None if reason else gap,
        interval=found.get("interval"),
        points=int(points) if points else None,
        fastest=found.get("fastest"),
        q1=found.get("q1"),
        q2=found.get("q2"),
        q3=found.get("q3"),
        penalised=bool(row["penalised"]),
    )


def _fastest_lap(driver_line: str, team_line: str) -> FastestLap:
    row = _ROW.match(driver_line)
    figures = _FASTEST.match(team_line)
    if row is None or figures is None:
        raise DocumentParseError(f"unreadable fastest lap {driver_line!r} / {team_line!r}")
    return FastestLap(
        car=int(row["car"]),
        driver=row["driver"],
        team=figures["team"],
        time=figures["time"],
        lap=int(figures["lap"]) if figures["lap"] else None,
    )


def _lines_after_header(text: str, header: re.Match[str]) -> list[str]:
    lines = []
    for line in text[header.end() :].splitlines():
        if _END.match(line):
            break
        if line.strip():
            lines.append(squash(line))
    return lines


def parse_classification(text: str) -> Classification:
    """Read a classification. Raises :class:`DocumentParseError` for any other shape."""
    text = clean(text)
    title = _TITLE.search(text)
    header = _HEADER.search(text)
    if title is None or header is None:
        raise DocumentParseError("not a classification: no title or column header")
    kind = _session_kind(squash(header["columns"]))
    lines = _lines_after_header(text, header)

    entries: list[ClassifiedEntry] = []
    penalty_lines: list[str] = []
    fastest_lap = None
    section = "classified"
    index = 0
    while index < len(lines):
        line = lines[index]
        if line in _HEADINGS:
            section = _HEADINGS[line]
            index += 1
        elif section == "penalties":
            penalty_lines.append(line)
            index += 1
        else:
            row = _ROW.match(line)
            if row is None or index + 1 >= len(lines):
                raise DocumentParseError(f"unreadable row {line!r}")
            team_line = lines[index + 1]
            index += 2
            if section == "fastest_lap":
                fastest_lap = _fastest_lap(line, team_line)
            elif section != "pole":
                entries.append(_entry(row, team_line, kind, section))

    placed = [entry.position for entry in entries if entry.status == "classified"]
    if not placed or placed != list(range(1, len(placed) + 1)):
        raise DocumentParseError(f"classified positions are not 1..N: {placed}")
    return Classification(
        document=document_number(text),
        session=squash(_SESSION_WORDS.sub("", title["title"])),
        final=bool(re.search(r"\bFinal\b", title["title"])),
        entries=tuple(entries),
        penalties=ruled_notes(" ".join(penalty_lines)),
        fastest_lap=fastest_lap,
    )
