"""What kind of document a listed FIA title is, pinned on every title of a real event page.

The fixture is the 2026 Mexico City Grand Prix event page (R19): 85 documents,
typos included ("Infringment").
"""

from collections import Counter
from pathlib import Path

import pytest

from app.data.fia_documents.kinds import document_kind
from app.data.fia_documents.site import listed_documents

pytestmark = pytest.mark.unit

MEXICO = (Path(__file__).parent / "fixtures" / "fia_documents" / "event_page_mexico_2026.html").read_text()


def test_every_document_of_the_mexico_weekend_gets_its_kind():
    titles = [document.title for document in listed_documents(MEXICO, "Mexico City Grand Prix")]

    assert len(titles) == 85
    assert Counter(document_kind(title) for title in titles) == {
        "penalty": 35,
        "other": 24,
        "classification": 7,
        "deleted_laps": 7,
        "grid": 5,
        "entry_list": 3,
        "power_unit": 2,
        "pirelli": 1,
        "timetable": 1,
    }


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        # The documents phase D2 is accepted on.
        ("Doc 17 - Infringement - Car 77 - PU elements", "penalty"),
        ("Doc 33 - Infringement - Car 3 - Turn 14 incident with Car 30", "penalty"),
        ("Doc 57 - Infringement - Car 30 - Technical nonconformity", "penalty"),
        ("Doc 65 - Infringement - Car 30 - Changes made during Parc Ferme", "penalty"),
        ("Doc 79 - Infringement - Car 81 - Causing a collision", "penalty"),
        ("Doc 86 - Final Race Classification", "classification"),
        # Penalties: misspelt, summoned, a team summoned over a car, corrected.
        ("Doc 42 - Infringment - Car 77 - Pit Lane Speeding", "penalty"),
        ("Doc 82 - Summons - Car 63 - Alleged failure to attend mandatory post-race commitments", "penalty"),
        ("Doc 16 - Summons - Audi - Alleged release of car 98 in an unsafe condition", "penalty"),
        ("Doc 76 - Decision - Car 10 - Alleged leaving the track and gaining an advantage", "penalty"),
        ("Doc 44 - Corrected Infringement - Car 6 - PU elements", "penalty"),
        # Look like penalties, but name no car or are the technical delegate's reports.
        ("Doc 50 - Decision - Qualifying SC2-SC1 Times", "other"),
        ("Doc 53 - MGU-K Infringement, Car 30", "other"),
        ("Doc 3 - Post-Race Inspections on Car Number 63, 2026 United States GP", "other"),
        # Lap deletions are infringements too, and win.
        ("Doc 49 - Infringement - Qualifying Deleted Lap Times - Double Yellow", "deleted_laps"),
        ("Doc 80 - Infringement - Race Deleted Lap Times", "deleted_laps"),
        # The grid: sheets, parc fermé changes, and permission to start.
        ("Doc 60 - Provisional Starting Grid", "grid"),
        ("Doc 66 - Parts and Parameters been replaced and or changed during Parc Ferme", "grid"),
        ("Doc 58 - Decision - Car 30 - Permission to start", "grid"),
        # The entry list and driver changes.
        ("Doc 36 - Decision - Driver Change TGR Haas F1 Team", "entry_list"),
        ("Doc 37 - Revised Entry List", "entry_list"),
        # Power-unit reports, but not the race director's energy limits.
        ("Doc 9 - PU Elements used per Driver up to now", "power_unit"),
        ("Doc 14 - New PU Elements for this Competition", "power_unit"),
        ("Doc 6 - Power Unit Information", "other"),
        ("Doc 2 - Competition Notes - Pirelli Preview", "pirelli"),
        ("Doc 4 - Timetable V2", "timetable"),
        ("Doc 87 - Championship Points", "other"),
    ],
)
def test_document_kind(title, kind):
    assert document_kind(title) == kind
