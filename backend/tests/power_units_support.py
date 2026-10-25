"""Shared builders for the power-unit service tests.

``season_context()`` is a 2026 f1db view with the real grid and the real Monza
swap: Liam Lawson in Red Bull's second car as #30 and Yuki Tsunoda in Lawson's
Racing Bulls car as #22 for round 13, everyone back in their own car by round
17. ``corpus()`` is the FIA documents of the fixtures directory as the ingest
job would have stored them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.data.power_units.allowances import SOURCE_FIA, AllowanceEntry
from app.data.power_units.season_context import Entry, SeasonContext, SeasonRound
from app.data.power_units.sources import SeasonSources, SourceDocument

FIXTURES = Path(__file__).parent / "fixtures" / "power_units"

ROUNDS = (
    SeasonRound(1, date(2026, 3, 8), "Australian GP", "AUS"),
    SeasonRound(13, date(2026, 9, 6), "Italian GP", "ITA"),
    SeasonRound(16, date(2026, 10, 4), "Bahrain GP", "BHR"),
    SeasonRound(17, date(2026, 10, 11), "Singapore GP", "SIN"),
    SeasonRound(18, date(2026, 10, 25), "United States GP", "USA"),
)

TEAMS = {
    "mclaren": "McLaren",
    "mercedes": "Mercedes",
    "red-bull": "Red Bull",
    "ferrari": "Ferrari",
    "williams": "Williams",
    "racing-bulls": "Racing Bulls",
    "aston-martin": "Aston Martin",
    "haas": "Haas",
    "audi": "Audi",
    "alpine": "Alpine",
    "cadillac": "Cadillac",
}

GRID = (
    (81, "oscar-piastri", "Oscar Piastri", "PIA", "mclaren"),
    (1, "lando-norris", "Lando Norris", "NOR", "mclaren"),
    (63, "george-russell", "George Russell", "RUS", "mercedes"),
    (12, "kimi-antonelli", "Kimi Antonelli", "ANT", "mercedes"),
    (3, "max-verstappen", "Max Verstappen", "VER", "red-bull"),
    (6, "isack-hadjar", "Isack Hadjar", "HAD", "red-bull"),
    (16, "charles-leclerc", "Charles Leclerc", "LEC", "ferrari"),
    (44, "lewis-hamilton", "Lewis Hamilton", "HAM", "ferrari"),
    (23, "alexander-albon", "Alexander Albon", "ALB", "williams"),
    (55, "carlos-sainz-jr", "Carlos Sainz Jr.", "SAI", "williams"),
    (41, "arvid-lindblad", "Arvid Lindblad", "LIN", "racing-bulls"),
    (30, "liam-lawson", "Liam Lawson", "LAW", "racing-bulls"),
    (18, "lance-stroll", "Lance Stroll", "STR", "aston-martin"),
    (14, "fernando-alonso", "Fernando Alonso", "ALO", "aston-martin"),
    (31, "esteban-ocon", "Esteban Ocon", "OCO", "haas"),
    (87, "oliver-bearman", "Oliver Bearman", "BEA", "haas"),
    (27, "nico-hulkenberg", "Nico Hülkenberg", "HUL", "audi"),
    (5, "gabriel-bortoleto", "Gabriel Bortoleto", "BOR", "audi"),
    (10, "pierre-gasly", "Pierre Gasly", "GAS", "alpine"),
    (43, "franco-colapinto", "Franco Colapinto", "COL", "alpine"),
    (11, "sergio-perez", "Sergio Pérez", "PER", "cadillac"),
    (77, "valtteri-bottas", "Valtteri Bottas", "BOT", "cadillac"),
)

#: Round 13's swaps: (car number in the grid above) → who raced it instead.
MONZA_SWAPS = {
    6: (30, "liam-lawson", "Liam Lawson", "LAW", "red-bull"),
    30: (22, "yuki-tsunoda", "Yuki Tsunoda", "TSU", "racing-bulls"),
}

CORPUS = (
    ("Italian Grand Prix", "Doc 13 - New PU Elements for this Competition", "new_elements_italy.txt"),
    ("Italian Grand Prix", "Doc 33 - New PU elements for this Competition", "new_elements_italy_1.txt"),
    ("Italian Grand Prix", "Doc 41 - Infringement - Car 30 - Change to PU elements", "decision_italy_car30.txt"),
    ("Singapore Grand Prix", "Doc 10 - PU Elements used per Driver up to now", "usage_singapore.txt"),
    ("Singapore Grand Prix", "Doc 20 - Infringement - Car 63 - Changes to PU elements", "decision_singapore_car63.txt"),
    (
        "Singapore Grand Prix",
        "Doc 80 - Infringement - Car 14 - PU element and changes made during Parc Ferme",
        "decision_singapore_car14_pitlane.txt",
    ),
    ("United States Grand Prix", "Doc 13 - New PU Elements for this Competition", "new_elements_usa.txt"),
    ("United States Grand Prix", "Doc 14 - Infringement - Car 43 - PU element", "decision_usa_car43.txt"),
    ("United States Grand Prix", "Doc 15 - Infringement - Car 5 - PU elements", "decision_usa_car5.txt"),
)


#: The 2026 allowances as the FIA's latest reports state them.
ALLOWANCES_2026 = {"ICE": 4, "TC": 4, "EXH": 4, "MGU-K": 3, "ES": 3, "PU-CE": 3, "PU-ANC": 6}


def allowance_entries(**overrides: AllowanceEntry) -> dict[str, AllowanceEntry]:
    """The stored allowance document as the ingest job would have written it."""
    entries = {
        code: AllowanceEntry(
            code=code,
            allowance=count,
            source=SOURCE_FIA,
            document_title="Doc 13 - New PU Elements for this Competition",
            document_url="https://www.fia.com/docs/new_elements_usa.txt",
            stated_on="2026-10-25",
            updated_at="2026-10-23T12:40:00+00:00",
        )
        for code, count in ALLOWANCES_2026.items()
    }
    return {**entries, **overrides}


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def entry(round_num: int, row: tuple[int, str, str, str, str]) -> Entry:
    number, driver_id, name, code, team_id = row
    return Entry(round_num, number, driver_id, name, code, team_id, TEAMS[team_id])


def season_context(entry_rounds: tuple[int, ...] = (1, 13, 17)) -> SeasonContext:
    """The f1db view, holding race-weekend entries for ``entry_rounds`` only."""
    entries = [
        entry(round_num, (MONZA_SWAPS.get(row[0]) if round_num == 13 else None) or row)
        for round_num in entry_rounds
        for row in GRID
    ]
    return SeasonContext(year=2026, rounds=ROUNDS, entries=tuple(entries))


def source(event: str, title: str, name: str, **overrides: object) -> SourceDocument:
    fields: dict = {
        "url": f"https://www.fia.com/docs/{name}",
        "event": event,
        "title": title,
        "published": "",
        "sha256": "",
        "fetched_at": "",
        "text": fixture(name),
    }
    return SourceDocument(**{**fields, **overrides})


def corpus(*extra: SourceDocument) -> SeasonSources:
    return SeasonSources(year=2026, documents=(*(source(*item) for item in CORPUS), *extra))
