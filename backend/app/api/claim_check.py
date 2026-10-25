"""Check the driver↔team claims in an answer against the tables it was built from.

The model attaches teams to drivers while writing, and got it wrong in ways
its own rows contradicted: "Kimi Antonelli (Alfa Romeo)", "Mercedes drivers
(Russell three times, Norris once)". This finds those claims.

The reference is the tables the tools returned in this conversation, never a
fixed roster: an answer about 2008 must not be "corrected" against 2026, so a
driver absent from the rows is never checked. Only shapes that clearly state
an attribution count — "Driver (Team)", "Driver – Team", a table cell,
"Team's Driver", "Driver … for Team", "Team drivers (…)" — because a flag
costs a repair request and a false one invites the model to break a true
sentence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re

_TEAM_HEADER = re.compile(r"team|constructor", re.IGNORECASE)
_ALIGNMENT_CELL = re.compile(r":?-{2,}:?")
_CODE_SUFFIX = re.compile(r"\s*\(([A-Z]{3})\)\s*$")
_SLUG = re.compile(r"[a-z]+(?:-[a-z]+)+")
_NAME_SUFFIXES = frozenset({"Jr.", "Jr", "Sr.", "Sr", "II", "III"})
_SENTENCE_END = ".!?\n"

Roster = Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class Misattribution:
    """A driver the answer places at a team their rows do not."""

    driver: str
    claimed_team: str
    actual_teams: tuple[str, ...]
    excerpt: str


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _tables(text: str) -> Iterable[tuple[list[str], list[list[str]]]]:
    """Each Markdown table in ``text`` as (header cells, row cells)."""
    lines = text.splitlines()
    for index in range(len(lines) - 1):
        header, alignment = lines[index], lines[index + 1]
        if not header.lstrip().startswith("|"):
            continue
        if not all(_ALIGNMENT_CELL.fullmatch(cell) for cell in _cells(alignment)):
            continue
        rows = []
        for line in lines[index + 2 :]:
            if not line.lstrip().startswith("|"):
                break
            rows.append(_cells(line))
        yield _cells(header), rows


def _keys(cell: str) -> set[str]:
    """The family name and the three-letter code a driver cell answers to."""
    name = cell.replace("*", "").strip()
    keys = set()
    code = _CODE_SUFFIX.search(name)
    if code:
        keys.add(code.group(1))
        name = name[: code.start()]
    if _SLUG.fullmatch(name):
        name = " ".join(part.capitalize() for part in name.split("-"))
    tokens = [token for token in name.split() if token not in _NAME_SUFFIXES]
    if tokens and tokens[-1][:1].isupper():
        keys.add(tokens[-1])
    return keys


def _pairs(header: list[str], rows: list[list[str]]) -> Iterable[tuple[str, str]]:
    """(driver cell, team cell) for each team column and the column to its left."""
    for team_index, title in enumerate(header):
        name_index = team_index - 1
        if not _TEAM_HEADER.search(title) or name_index < 0 or _TEAM_HEADER.search(header[name_index]):
            continue
        yield from ((row[name_index], row[team_index]) for row in rows if len(row) > team_index and row[team_index])


def roster_from_tables(texts: Iterable[str]) -> dict[str, frozenset[str]]:
    """Driver key → every team the tables show them with.

    A team column pairs with the column immediately to its left: "Driver |
    Team" in the session tools, "sprint_winner | sprint_team" in SQL.
    """
    seen: dict[str, set[str]] = {}
    pairs = (pair for text in texts for header, rows in _tables(text) for pair in _pairs(header, rows))
    for name, team in pairs:
        for key in _keys(name):
            seen.setdefault(key, set()).add(team)
    return {key: frozenset(teams) for key, teams in seen.items()}


def _alternation(words: Iterable[str]) -> str:
    return "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))


_FILLER_WORDS = frozenset({"f1", "team"})


def _team_words(name: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", name.casefold()) if w not in _FILLER_WORDS)


def _initials(words: str) -> str:
    return "".join(word[0] for word in words.split())


def _same_team(first: str, second: str) -> bool:
    """One team under the names different sources give it.

    FastF1 says "Red Bull Racing" and "RB F1 Team" where f1db says "Red Bull"
    and "Racing Bulls". Filler words aside, a name matches if it contains the
    other or abbreviates it — so "RB" is Racing Bulls, while "Red Bull" is not.
    A name that is all filler ("F1 Team") contains nothing, so it never flags.
    """
    a, b = _team_words(first), _team_words(second)
    return a in b or b in a or a == _initials(b) or b == _initials(a)


def _excerpt(text: str, position: int) -> str:
    start = max(text.rfind(mark, 0, position) for mark in _SENTENCE_END) + 1
    ends = [i for mark in _SENTENCE_END if (i := text.find(mark, position)) != -1]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end].strip()


def _claims(answer: str, drivers: str, teams: str) -> Iterable[tuple[int, str, str]]:
    """Every (position, driver key, team) the answer states as an attribution."""
    driver_re = re.compile(rf"\b(?:{drivers})\b")
    # An optional "(NOR)" after the name is the driver's own code, not the claim.
    after = re.compile(rf"(?:\s*\([A-Z]{{3}}\))?[\s*_()\[\]|–—-]{{1,6}}({teams})\b")
    for_team = re.compile(rf"([^{_SENTENCE_END}]{{0,40}}?)\bfor\s+(?:the\s+)?({teams})\b")
    claimed_until = 0  # "Norris (NOR) | Mercedes" is one claim, not one per alias
    for found in driver_re.finditer(answer):
        if found.start() < claimed_until:
            continue
        if claim := after.match(answer, found.end()):
            claimed_until = claim.end()
            yield found.start(), found.group(), claim.group(1)
        claim = for_team.match(answer, found.end())
        if claim and not driver_re.search(claim.group(1)):
            yield found.start(), found.group(), claim.group(2)
    possessive = re.compile(rf"({teams})['’]s?\s+(?:[A-Z][\w-]+\s+){{0,2}}?({drivers})\b")
    for claim in possessive.finditer(answer):
        yield claim.start(), claim.group(2), claim.group(1)
    listed = re.compile(rf"({teams})(?:['’]s?)?\s+drivers?\b[^()\n]{{0,30}}\(([^)\n]{{1,160}})\)")
    for claim in listed.finditer(answer):
        for found in driver_re.finditer(claim.group(2)):
            yield claim.start(2) + found.start(), found.group(), claim.group(1)


def find_misattributions(answer: str, roster: Roster, team_names: Iterable[str]) -> list[Misattribution]:
    """Claims in ``answer`` that put a roster driver at a team the rows do not."""
    if not roster:
        return []
    # A driver's own surname or code is never a team, even when a constructor
    # shares it: f1db lists "LEC" (1977), which is also Leclerc's code.
    known = {*team_names, *(team for found in roster.values() for team in found)} - set(roster)
    teams = _alternation(known)
    flagged: dict[tuple[str, str], Misattribution] = {}
    for position, driver, claimed in sorted(_claims(answer, _alternation(roster), teams)):
        actual = roster[driver]
        if any(_same_team(claimed, team) for team in actual) or (driver, claimed) in flagged:
            continue
        flagged[(driver, claimed)] = Misattribution(driver, claimed, tuple(sorted(actual)), _excerpt(answer, position))
    return list(flagged.values())
