"""Tests for driver resolution in app.data.identity, on real f1db seasons.

What every emit point relies on:

* the display name is f1db ``driver.name`` ("Carlos Sainz Jr.", "Ryō
  Hirakawa"), never ``full_name``, the legal name;
* a feed row resolves by f1db id, then code, then car number, then folded
  name, and the code and number only ever count within the season (VER is Jos
  in 2003, Max in 2026);
* a key that fits several drivers resolves nothing on its own, and nothing is
  picked among them: no match means the feed's own words, recased, with no id.
"""

from __future__ import annotations

from dataclasses import astuple
import json

import pytest

from app.data import f1db_source, identity
from app.data.identity import (
    CanonicalDriver,
    canonical_driver,
    normalize_feed_name,
    resolve_driver,
    season_directory,
)
from tests.identity_support import build_identity_db, identity_seasons
from tests.roster_support import MEXICO

# f1db's driver table rows, by id: (id, name, first, last, full name, code, permanent number).
DRIVER_ROWS = {row[0]: row for row in identity_seasons()["drivers"]}
SEASON_DRIVERS = sorted({(year, driver_id) for year, _rnd, _kind, driver_id, *_ in identity_seasons()["entries"]})


class F1dbReadError(Exception):
    """Raised by the stand-in ``connect`` of a test that forbids reading f1db."""


def _forbid_f1db(monkeypatch: pytest.MonkeyPatch) -> None:
    def connect() -> None:
        raise F1dbReadError

    monkeypatch.setattr(f1db_source, "connect", connect)


@pytest.fixture
def seasons_f1db(tmp_path, monkeypatch):
    """Point f1db at the captured seasons, with no directory or index cached from elsewhere."""
    monkeypatch.setattr(f1db_source, "DB_PATH", build_identity_db(tmp_path / "f1db.db"))
    identity.clear_cache()
    yield
    identity.clear_cache()


def _feed_spelling(driver_id: str) -> str:
    """How OpenF1 writes a driver: f1db's name with the surname shouted ("Nyck DE VRIES")."""
    _id, name, _first, last, *_ = DRIVER_ROWS[driver_id]
    assert name.casefold().endswith(last.casefold())
    return name[: len(name) - len(last)] + last.upper()


# --- DriverEntry carries f1db's name parts -------------------------------------------------


@pytest.mark.integration
def test_directory_entries_carry_f1dbs_first_and_last_name(seasons_f1db):
    drivers = {driver.id: driver for driver in season_directory(2026).drivers}

    sainz = drivers["carlos-sainz-jr"]
    assert (sainz.name, sainz.first_name, sainz.last_name) == ("Carlos Sainz Jr.", "Carlos", "Sainz Jr.")
    assert drivers["ryo-hirakawa"].last_name == "Hirakawa"


@pytest.mark.integration
def test_first_name_is_f1dbs_and_can_be_a_legal_name(seasons_f1db):
    """Jak Crawford's f1db first name is "Carlton": display text comes from ``name``, never the parts."""
    crawford = resolve_driver(2026, code="CRA")

    assert crawford is not None
    assert (crawford.name, crawford.first_name, crawford.last_name) == ("Jak Crawford", "Carlton", "Crawford")
    assert canonical_driver(2026, code="CRA").name == "Jak Crawford"


# --- The named drivers ---------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "keys",
    [
        {"driver_id": "carlos-sainz-jr"},
        {"code": "SAI"},
        {"number": 55},
        {"name": "Carlos Sainz Jr."},
        {"name": "SAINZ JR."},
        {"code": "SAI", "number": 55, "name": "Carlos SAINZ"},
    ],
    ids=["id", "code", "number", "name", "last-name", "openf1-row"],
)
def test_sainz_is_carlos_sainz_jr(seasons_f1db, keys):
    assert canonical_driver(2026, **keys) == CanonicalDriver(
        name="Carlos Sainz Jr.", last_name="Sainz Jr.", code="SAI", id="carlos-sainz-jr"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    ["Nyck de Vries", "Nyck DE VRIES", "NYCK DE VRIES", "De Vries", "de vries"],
)
def test_de_vries_resolves_with_f1dbs_casing(seasons_f1db, name):
    """f1db writes "Nyck de Vries", and "De Vries" for the surname standing alone."""
    assert canonical_driver(2023, name=name) == CanonicalDriver(
        name="Nyck de Vries", last_name="De Vries", code="DEV", id="nyck-de-vries"
    )
    assert resolve_driver(2023, number=21).id == "nyck-de-vries"


@pytest.mark.integration
def test_de_vries_outside_his_seasons_falls_back_to_the_same_casing(seasons_f1db):
    assert canonical_driver(2026, name="Nyck DE VRIES") == CanonicalDriver(
        name="Nyck de Vries", last_name="De Vries", code=None, id=None
    )


@pytest.mark.integration
@pytest.mark.parametrize("name", ["Hulkenberg", "HULKENBERG", "Nico HULKENBERG", "Nico Hülkenberg", "hülkenberg"])
def test_hulkenberg_matches_with_or_without_the_umlaut(seasons_f1db, name):
    driver = canonical_driver(2026, name=name)

    assert (driver.id, driver.name, driver.last_name) == ("nico-hulkenberg", "Nico Hülkenberg", "Hülkenberg")


@pytest.mark.integration
@pytest.mark.parametrize(
    "keys",
    [{"name": "Ryo Hirakawa"}, {"number": 50}, {"number": "50"}, {"code": "HIR", "number": 50, "name": "Ryo HIRAKAWA"}],
    ids=["openf1-name", "car-number", "car-number-as-text", "openf1-row"],
)
def test_hirakawa_resolves_to_ryo_with_the_macron(seasons_f1db, keys):
    assert canonical_driver(2026, **keys) == CanonicalDriver(
        name="Ryō Hirakawa", last_name="Hirakawa", code="HIR", id="ryo-hirakawa"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "session",
    ["openf1_drivers.json", "openf1_drivers_qualifying.json", "openf1_drivers_practice1.json"],
    ids=["race", "qualifying", "practice-1"],
)
def test_every_openf1_row_at_mexico_city_resolves_to_its_f1db_driver(seasons_f1db, session):
    """FP1 included: its nine rookies took part, so they resolve too."""
    rows = json.loads((MEXICO / session).read_text())

    resolved = {
        row["name_acronym"]: canonical_driver(
            2026, code=row["name_acronym"], number=row["driver_number"], name=row["full_name"]
        )
        for row in rows
    }

    assert all(driver.resolved for driver in resolved.values())
    assert all(driver.name == DRIVER_ROWS[driver.id][1] for driver in resolved.values())
    assert resolved["HIR"].name == "Ryō Hirakawa"
    assert resolved["SAI"].name == "Carlos Sainz Jr."
    assert resolved["HUL"].name == "Nico Hülkenberg"
    assert resolved["PER"].name == "Sergio Pérez"


# --- The legal-name regression -------------------------------------------------------------


@pytest.mark.integration
def test_canonical_driver_never_answers_with_the_legal_name(seasons_f1db):
    """``full_name`` is the legal name ("Carlos Sainz Vázquez de Castro"); it never reaches a page."""
    sainz = canonical_driver(2026, driver_id="carlos-sainz-jr")
    assert "Carlos Sainz Vázquez de Castro" not in astuple(sainz)

    for year, driver_id in SEASON_DRIVERS:
        _id, name, _first, last, full_name, code, _number = DRIVER_ROWS[driver_id]
        driver = canonical_driver(year, driver_id=driver_id)
        assert driver == CanonicalDriver(name=name, last_name=last, code=code, id=driver_id)
        if full_name != name:
            assert full_name not in astuple(driver)


@pytest.mark.integration
def test_the_legal_name_is_not_a_key(seasons_f1db):
    assert resolve_driver(2026, name="Carlos Sainz Vázquez de Castro") is None
    assert resolve_driver(2026, name="Andrea Kimi Antonelli") is None


# --- Order of keys and the season ----------------------------------------------------------


@pytest.mark.integration
def test_id_beats_code(seasons_f1db):
    assert resolve_driver(2026, driver_id="max-verstappen", code="NOR").id == "max-verstappen"


@pytest.mark.integration
def test_code_beats_number(seasons_f1db):
    assert resolve_driver(2026, code="NOR", number=3).id == "lando-norris"


@pytest.mark.integration
def test_an_id_resolves_only_within_its_season(seasons_f1db):
    """Michael Schumacher raced no 2026 session, so his id names nobody there and the code decides."""
    assert resolve_driver(2026, driver_id="michael-schumacher") is None
    assert resolve_driver(2026, driver_id="michael-schumacher", code="NOR").id == "lando-norris"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "code", "expected"),
    [
        (2003, "VER", "jos-verstappen"),
        (2026, "VER", "max-verstappen"),
        (2026, "ver", "max-verstappen"),
        (2006, "MSC", "michael-schumacher"),
        (2022, "MSC", "mick-schumacher"),
    ],
    ids=["VER-2003", "VER-2026", "lower-case", "MSC-2006", "MSC-2022"],
)
def test_a_code_resolves_within_the_season(seasons_f1db, year, code, expected):
    assert resolve_driver(year, code=code).id == expected


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "number", "expected"),
    [
        (2026, 50, "ryo-hirakawa"),
        (2026, 31, "esteban-ocon"),
        (2026, 1, "lando-norris"),
        # f1db's permanent number for Max is now 3; in 2022 he raced 1 and Ricciardo raced 3.
        (2022, 1, "max-verstappen"),
        (2022, 3, "daniel-ricciardo"),
    ],
)
def test_a_number_is_the_one_the_car_raced_with_that_season(seasons_f1db, year, number, expected):
    assert DRIVER_ROWS["max-verstappen"][6] == "3"
    assert resolve_driver(year, number=number).id == expected


# --- Never guess ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "keys"),
    [
        (2006, {"code": "MON"}),
        (2014, {"code": "VER"}),
        (2006, {"name": "Schumacher"}),
        (2006, {"number": 23}),
        (2022, {"number": 45}),
    ],
    ids=["MON-Monteiro-or-Montagny", "VER-Vergne-or-Max-in-FP1", "two-Schumachers", "Super-Aguri-23", "45-in-FP1"],
)
def test_an_ambiguous_key_resolves_nobody(seasons_f1db, year, keys):
    assert resolve_driver(year, **keys) is None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("year", "keys", "expected"),
    [
        (2014, {"code": "VER", "number": 25}, "jean-eric-vergne"),
        (2014, {"code": "VER", "number": 38}, "max-verstappen"),
        (2006, {"number": 23, "name": "Sakon Yamamoto"}, "sakon-yamamoto"),
        (2006, {"code": "MON", "name": "Franck Montagny"}, "franck-montagny"),
    ],
    ids=["Vergne-by-number", "Max-by-number", "Yamamoto-by-name", "Montagny-by-name"],
)
def test_an_ambiguous_key_leaves_the_decision_to_the_next_exact_key(seasons_f1db, year, keys, expected):
    assert resolve_driver(year, **keys).id == expected


@pytest.mark.integration
def test_an_unknown_driver_falls_back_to_the_feeds_words(seasons_f1db):
    """Mick Schumacher raced no 2026 session: his row keeps the feed's name and code, and gets no id."""
    driver = canonical_driver(2026, code="msc", number=47, name="Mick SCHUMACHER")

    assert driver == CanonicalDriver(name="Mick Schumacher", last_name="Schumacher", code="MSC", id=None)
    assert driver.resolved is False


@pytest.mark.integration
@pytest.mark.parametrize(
    "keys",
    [{}, {"driver_id": "", "code": "", "name": ""}, {"code": "   ", "name": "   "}, {"number": ""}],
    ids=["nothing", "empty", "blank", "empty-number"],
)
def test_empty_inputs_resolve_nobody_without_reading_f1db(monkeypatch, keys):
    _forbid_f1db(monkeypatch)

    assert resolve_driver(2026, **keys) is None
    assert canonical_driver(2026, **keys) == CanonicalDriver(name="", last_name=None, code=None, id=None)


@pytest.mark.unit
def test_an_unknown_keyword_is_a_typo_and_fails_loudly(monkeypatch):
    """No type checker runs in CI, so a misspelt key must not silently resolve nobody."""
    _forbid_f1db(monkeypatch)

    with pytest.raises(TypeError, match="unknown driver keys: acronym, nmae"):
        resolve_driver(2026, nmae="Lando NORRIS", acronym="NOR", code="NOR")


@pytest.mark.integration
def test_car_zero_is_looked_up_not_taken_for_a_blank(seasons_f1db, monkeypatch):
    """Damon Hill raced car 0 in 1993-94, so 0 is a number to look up."""
    _forbid_f1db(monkeypatch)

    with pytest.raises(F1dbReadError):
        resolve_driver(2026, number=0)


# --- normalize_feed_name -------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Lando NORRIS", "Lando Norris"),
        ("LANDO NORRIS", "Lando Norris"),
        ("Lando Norris", "Lando Norris"),
        ("  Lando   NORRIS ", "Lando Norris"),
        ("Kimi ANTONELLI", "Kimi Antonelli"),
        ("Nico HULKENBERG", "Nico Hulkenberg"),
        ("Jean-Éric VERGNE", "Jean-Éric Vergne"),
        ("Patricio O'WARD", "Patricio O'Ward"),
        ("Carlos SAINZ JR.", "Carlos Sainz Jr."),
        ("Nyck DE VRIES", "Nyck de Vries"),
        ("DE VRIES", "De Vries"),
        ("Pedro DE LA ROSA", "Pedro de la Rosa"),
        ("", ""),
    ],
)
def test_normalize_feed_name_recases_only_what_the_feed_shouted(text, expected):
    assert normalize_feed_name(text) == expected


@pytest.mark.integration
def test_fallback_matches_f1dbs_casing_for_every_captured_driver(seasons_f1db):
    """Shout each surname the way OpenF1 does; the fallback must give back f1db's name and surname.

    Year 1999 is in none of the captured seasons, so every lookup falls back.
    """
    for driver_id, (_id, name, _first, last, *_rest) in DRIVER_ROWS.items():
        driver = canonical_driver(1999, name=_feed_spelling(driver_id))
        assert (driver.name, driver.last_name, driver.id) == (name, last, None)


@pytest.mark.integration
@pytest.mark.parametrize("text", ["Lando Norris", "LANDO NORRIS", "Lando NORRIS jr", ""])
def test_the_fallback_names_no_surname_the_feed_did_not_mark(seasons_f1db, text):
    """A surname is read only from shouted words after an unshouted given name (1999 is not captured)."""
    assert canonical_driver(1999, name=text).last_name is None


# --- Cache ---------------------------------------------------------------------------------


@pytest.mark.integration
def test_the_index_is_read_once_per_f1db_release(seasons_f1db, monkeypatch):
    assert resolve_driver(2026, code="HIR").id == "ryo-hirakawa"
    _forbid_f1db(monkeypatch)

    assert resolve_driver(2026, number=50).id == "ryo-hirakawa"

    monkeypatch.setattr(f1db_source, "installed_version", lambda: "v2026.20.0")
    with pytest.raises(F1dbReadError):
        resolve_driver(2026, code="HIR")


@pytest.mark.integration
def test_clear_cache_drops_the_index(seasons_f1db, monkeypatch):
    resolve_driver(2026, code="HIR")
    identity.clear_cache()
    _forbid_f1db(monkeypatch)

    with pytest.raises(F1dbReadError):
        resolve_driver(2026, code="HIR")
