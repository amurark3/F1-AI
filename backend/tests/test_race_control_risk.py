"""Tests for app.services.race_control.risk — the pit-wall risk register.

The risk cards are the most quotable thing on the command center: a strategist
reads "High — elevated rain risk" and primes a wet branch. So the thing worth
guarding is that every card is *earned* by real state, and that the absence of
state degrades into a card that says so.

Three behaviours matter here:

* the weather card is graded from the race session's Open-Meteo forecast and
  nothing else. On 6 Nov 2026 (São Paulo, R20) it graded OpenWeatherMap's
  current conditions, 5 %, as "Dry conditions expected" while Open-Meteo
  forecast ~90 % for the race window;
* with no race-day forecast the card says so and why, with no percentage and
  no dry/wet grade, and
* no rival card at all is emitted when the standings snapshot has nobody
  trailing the leader — an empty panel beats an invented rival.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data import weather as owm
from app.data.open_meteo import HourlyReading, HourlySeries
from app.services.race_control import risk, session_weather
from app.services.race_control.session_weather import (
    NOTE_OFFLINE,
    RACE_DAY_FORECAST,
    RACE_DAY_RECORD,
    build_session_weather,
)

UNAVAILABLE = "Race-day forecast unavailable"
NO_GRADE = "No rain probability to grade: keep both the dry and wet branches ready."


def _event(*, is_sprint: bool = False, circuit_type: str | None = None) -> dict:
    return {
        "is_sprint": is_sprint,
        "circuit": {"circuit_type": circuit_type} if circuit_type else None,
    }


def _weekend(rain: float | None = None, *, phase: str = "upcoming", **payload) -> dict:
    """A ``session_weather`` payload whose Race session forecasts ``rain`` (None: no forecast)."""
    forecast = None if rain is None else {"rain_probability_pct": rain, "track_temp_c": 30.0, "wind_kph": 12.0}
    race = {"name": "Race", "phase": phase, "forecast": forecast, "forecast_opens": None}
    return {"status": "ready", "note": None, "as_of_label": None, "sessions": [race], **payload}


OFFLINE = {"status": "unavailable", "note": NOTE_OFFLINE, "as_of_label": None, "sessions": []}


# ---------------------------------------------------------------------------
# São Paulo 2026 (R20): the weekend the register graded OpenWeatherMap
# ---------------------------------------------------------------------------

SAO_PAULO = {
    "location": "São Paulo, Brazil",
    "sessions": {
        "Practice 1": "2026-11-06T14:30:00Z",
        "Sprint Qualifying": "2026-11-06T18:30:00Z",
        "Sprint": "2026-11-07T14:00:00Z",
        "Qualifying": "2026-11-07T18:00:00Z",
        "Race": "2026-11-08T17:00:00Z",
    },
}
SATURDAY = datetime(2026, 11, 7, 16, tzinfo=UTC)
# Open-Meteo's rain probability for 15:00-20:00 UTC on race day, as it answered
# on 6 Nov 2026 (STATUS.md log). The race runs 17:00-19:00: 92 % then 90 %.
RACE_DAY_RAIN = {15: 94.0, 16: 93.0, 17: 92.0, 18: 90.0, 19: 88.0, 20: 86.0}


def _sao_paulo_hours() -> tuple[HourlyReading, ...]:
    start = datetime(2026, 11, 6, tzinfo=UTC)
    hours = (start + timedelta(hours=offset) for offset in range(72))
    return tuple(
        HourlyReading(
            time=moment,
            temperature_c=21.0,
            humidity_pct=80.0,
            rain_probability_pct=RACE_DAY_RAIN.get(moment.hour, 30.0) if moment.day == 8 else 30.0,
            precipitation_mm=0.0,
            weather_code=61,
            cloud_cover_pct=100.0,
            wind_kph=14.0,
            wind_direction_deg=150.0,
            is_day=True,
        )
        for moment in hours
    )


@pytest.fixture
def open_meteo(monkeypatch):
    """Serve ``session_weather`` a series (or an outage) instead of calling Open-Meteo."""

    def install(series: HourlySeries | Exception | None) -> None:
        def fetch(*_args) -> HourlySeries | None:
            if isinstance(series, Exception):
                raise series
            return series

        monkeypatch.setattr(session_weather, "fetch_hourly", fetch)

    return install


@pytest.fixture
def owm_says_dry(monkeypatch):
    """OpenWeatherMap answering with the 5 % it showed on 6 Nov; records any call."""
    asked: list[str] = []

    async def current_conditions(location: str) -> dict:
        asked.append(location)
        return {"current": {"rain_probability_pct": 5, "track_temp_c": 29, "wind_speed_kph": 13}}

    monkeypatch.setattr(owm, "get_weather_for_circuit", current_conditions)
    return asked


@pytest.mark.unit
def test_sao_paulo_race_window_rain_is_elevated_risk_in_open_meteos_words(open_meteo):
    open_meteo(HourlySeries(readings=_sao_paulo_hours(), fetched_at=SATURDAY))

    card = risk._weather_risk(build_session_weather(SAO_PAULO, now=SATURDAY))

    assert card == {
        "level": "High",
        "title": "Elevated rain risk",
        "detail": f"{RACE_DAY_FORECAST}: 92% peak rain probability in the race window"
        " — prime the wet branch and intermediate crossover.",
    }


@pytest.mark.unit
def test_feed_down_with_openweathermap_dry_gives_no_dry_card_and_no_number(open_meteo, owm_says_dry):
    open_meteo(None)

    register = risk.build_risk_register(_event(), build_session_weather(SAO_PAULO, now=SATURDAY), [])

    assert register == [{"level": "Medium", "title": UNAVAILABLE, "detail": f"{NOTE_OFFLINE} {NO_GRADE}"}]
    assert not any("Dry" in card["title"] or "%" in card["detail"] for card in register)
    assert owm_says_dry == [], "the register never asks OpenWeatherMap"
    assert not hasattr(risk, "get_weather_for_circuit")


@pytest.mark.unit
def test_a_stored_forecast_keeps_its_as_of_label(open_meteo):
    fetched = datetime(2026, 11, 7, 14, 5, tzinfo=UTC)
    open_meteo(HourlySeries(readings=_sao_paulo_hours(), fetched_at=fetched, stored=True))

    card = risk._weather_risk(build_session_weather(SAO_PAULO, now=SATURDAY))

    assert card["level"] == "High"
    assert card["detail"].startswith(
        f"{RACE_DAY_FORECAST} · as of 14:05 UTC: 92% peak rain probability in the race window"
    )


@pytest.mark.unit
def test_a_race_past_the_horizon_says_when_its_forecast_opens(open_meteo):
    open_meteo(AssertionError("no call is made before the forecast opens"))

    card = risk._weather_risk(build_session_weather(SAO_PAULO, now=datetime(2026, 10, 20, tzinfo=UTC)))

    assert card == {
        "level": "Medium",
        "title": UNAVAILABLE,
        "detail": f"The race-day forecast opens on 24 Oct. {NO_GRADE}",
    }


# ---------------------------------------------------------------------------
# _weather_risk
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("weekend", "reason"),
    [
        (OFFLINE, NOTE_OFFLINE),
        (_weekend(None), "The race-day forecast has no rain reading."),
        (_weekend(None, sessions=[]), "The race-day forecast has no rain reading."),
        ({**OFFLINE, "note": None}, "The race-day forecast has no rain reading."),
    ],
    ids=["feed-down", "no-race-forecast", "no-race-session", "no-note"],
)
def test_weather_risk_says_the_forecast_is_unavailable_and_why(weekend, reason):
    """Neither Low (it would read as dry) nor High (nothing supports alarm): Medium, keep both branches."""
    card = risk._weather_risk(weekend)

    assert card == {"level": "Medium", "title": UNAVAILABLE, "detail": f"{reason} {NO_GRADE}"}
    assert "%" not in card["detail"], "an unavailable card must never quote a rain probability"


@pytest.mark.unit
def test_weather_risk_ignores_a_rain_figure_outside_the_race_sessions_forecast():
    """Only the Race session's forecast counts: a reading on the payload or another session does not."""
    qualifying = {"name": "Qualifying", "phase": "upcoming", "forecast": {"rain_probability_pct": 5}}
    weekend = {**OFFLINE, "rain_risk": 5, "sessions": [qualifying]}

    assert risk._weather_risk(weekend)["title"] == UNAVAILABLE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rain", "level", "title"),
    [
        (95, "High", "Elevated rain risk"),
        (40, "High", "Elevated rain risk"),
        (39.6, "High", "Elevated rain risk"),
        (39.4, "Medium", "Mixed conditions possible"),
        (20, "Medium", "Mixed conditions possible"),
        (19, "Low", "Dry conditions expected"),
        (0, "Low", "Dry conditions expected"),
    ],
    ids=[
        "downpour",
        "at-high-cutoff",
        "rounds-up-to-high",
        "rounds-down-to-medium",
        "at-moderate-cutoff",
        "below",
        "dry",
    ],
)
def test_weather_risk_grades_the_race_day_rain_probability(rain, level, title):
    card = risk._weather_risk(_weekend(rain))

    assert (card["level"], card["title"]) == (level, title)
    # Every graded card names its source and quotes the (rounded) figure it was
    # graded from, so the number on screen can be traced back to the forecast.
    assert card["detail"].startswith(f"{RACE_DAY_FORECAST}: {round(rain)}% peak rain probability in the race window")


@pytest.mark.unit
def test_a_race_already_run_is_graded_as_a_model_reading_not_a_forecast():
    card = risk._weather_risk(_weekend(70, phase="done"))

    assert card["detail"].startswith(f"{RACE_DAY_RECORD}: 70% peak rain probability in the race window")


# ---------------------------------------------------------------------------
# _rival_risk
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "competitors",
    [None, [], [{"rank": 1, "team": "McLaren", "gap_to_leader": 0}]],
    ids=["no-standings", "empty-standings", "leader-only"],
)
def test_rival_risk_is_omitted_when_nobody_trails_the_leader(competitors):
    assert risk._rival_risk(competitors) is None


@pytest.mark.unit
def test_rival_risk_is_omitted_when_the_gap_is_not_a_number():
    """A malformed standings row must not produce a card quoting a bogus gap."""
    assert risk._rival_risk([{"rank": 2, "team": "Ferrari", "gap_to_leader": None}]) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("gap", "level"),
    [(0, "High"), (25, "High"), (26, "Medium"), (60, "Medium"), (61, "Low"), (300, "Low")],
    ids=["dead-heat", "at-high-cutoff", "just-over", "at-moderate-cutoff", "just-over-moderate", "runaway"],
)
def test_rival_risk_grades_the_real_constructor_gap(gap, level):
    card = risk._rival_risk([{"rank": 2, "team": "Ferrari", "gap_to_leader": gap}])

    assert card["level"] == level
    assert card["title"] == "Rival offset plans"
    assert f"{gap} pts" in card["detail"]
    assert "Ferrari" in card["detail"]


@pytest.mark.unit
def test_rival_risk_picks_the_closest_rival_not_the_first_listed():
    card = risk._rival_risk(
        [
            {"rank": 1, "team": "McLaren", "gap_to_leader": 0},
            {"rank": 2, "team": "Ferrari", "gap_to_leader": 80},
            {"rank": 3, "team": "Red Bull", "gap_to_leader": 12},
        ]
    )

    assert card["level"] == "High", "the 12-point car is the one to plan against"
    assert "Red Bull" in card["detail"]


@pytest.mark.unit
def test_rival_risk_names_a_placeholder_when_the_row_has_no_team():
    card = risk._rival_risk([{"rank": 2, "gap_to_leader": 5}])

    assert "the nearest rival" in card["detail"]


# ---------------------------------------------------------------------------
# build_risk_register
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_is_empty_without_an_event():
    assert risk.build_risk_register(None, _weekend(90), [{"rank": 2, "gap_to_leader": 1}]) == []


@pytest.mark.unit
def test_register_adds_the_sprint_compression_risk_for_sprint_weekends():
    register = risk.build_risk_register(_event(is_sprint=True), OFFLINE, [])

    assert [card["title"] for card in register] == ["Sprint format compression", UNAVAILABLE]


@pytest.mark.unit
def test_register_adds_safety_car_exposure_only_for_street_circuits():
    """Classified on ``CIRCUIT_DATA``'s own strings. The check used to compare
    against ``"Street"``, which no real circuit carries, so the card never
    appeared — not even for Monaco."""
    street = risk.build_risk_register(_event(circuit_type="Street circuit"), OFFLINE, [])
    semi_street = risk.build_risk_register(_event(circuit_type="Semi-street circuit"), OFFLINE, [])
    permanent = risk.build_risk_register(_event(circuit_type="Purpose-built"), OFFLINE, [])

    assert "Safety car exposure" in [card["title"] for card in street]
    assert "Safety car exposure" not in [card["title"] for card in semi_street]
    assert "Safety car exposure" not in [card["title"] for card in permanent]


@pytest.mark.unit
def test_register_skips_the_street_risk_when_the_event_has_no_circuit_metadata():
    register = risk.build_risk_register(_event(circuit_type=None), OFFLINE, [])

    assert [card["title"] for card in register] == [UNAVAILABLE]


@pytest.mark.unit
def test_register_stacks_every_earned_card_in_reading_order():
    register = risk.build_risk_register(
        _event(is_sprint=True, circuit_type="Street circuit"),
        _weekend(55),
        [{"rank": 1, "team": "McLaren", "gap_to_leader": 0}, {"rank": 2, "team": "Ferrari", "gap_to_leader": 10}],
    )

    assert [card["title"] for card in register] == [
        "Sprint format compression",
        "Safety car exposure",
        "Elevated rain risk",
        "Rival offset plans",
    ]
    assert [card["level"] for card in register] == ["High", "High", "High", "High"]


@pytest.mark.unit
def test_every_card_is_graded_high_medium_or_low():
    """The web colours a card by its level and has no colour for a fourth one
    (`RiskLevel` in the frontend's `weekendTypes.ts`), so the register may only
    grade with these three words."""
    event = _event(is_sprint=True, circuit_type="Street circuit")
    leader = {"rank": 1, "team": "McLaren", "gap_to_leader": 0}
    # Together these reach every card the module writes: both event cards, the
    # unavailable and the three graded weather cards, and the three rival grades.
    inputs = [
        (OFFLINE, []),
        (_weekend(10), [leader, {"rank": 2, "team": "Ferrari", "gap_to_leader": 10}]),
        (_weekend(30), [leader, {"rank": 2, "team": "Ferrari", "gap_to_leader": 40}]),
        (_weekend(70), [leader, {"rank": 2, "team": "Ferrari", "gap_to_leader": 90}]),
    ]

    levels = {card["level"] for weather, rivals in inputs for card in risk.build_risk_register(event, weather, rivals)}

    assert levels == {"High", "Medium", "Low"}
