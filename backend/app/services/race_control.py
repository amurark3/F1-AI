"""Race Control overview orchestration and public service facade.

Focused feature services live beside this module. This file keeps the existing
router contract stable while limiting itself to command-center composition.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.data.strategy import circuit_strategy_reference
from app.data.weather import get_weather_for_circuit
from app.services.predictions import get_or_compute_race_prediction
from app.services.race_control_battles import build_driver_battle
from app.services.race_control_championship import build_championship_forecast
from app.services.race_control_common import get_driver_options, get_standings_snapshot, safe_int
from app.services.race_control_debriefs import build_race_debrief
from app.services.race_control_standings import build_intel, build_teams
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()

WEATHER_FEED_OFFLINE = "External forecast feed not connected"
WEATHER_FEED_LIVE = "Live forecast (OpenWeatherMap)"

# Rain probability (%) cut-offs used to grade the live weather risk card.
RAIN_RISK_HIGH = 40
RAIN_RISK_MODERATE = 20

# Constructor championship point-gap cut-offs used to grade the rival-offset risk.
RIVAL_GAP_HIGH = 25
RIVAL_GAP_MODERATE = 60


def _offline_weather_block() -> dict:
    """Honest 'no live feed' block — null values, no fabricated numbers."""
    return {
        "rain_risk": None,
        "track_temp_c": None,
        "wind_kph": None,
        "confidence": WEATHER_FEED_OFFLINE,
    }


def build_weather_block(race: dict | None) -> dict:
    """Fetch live weather for the selected race's circuit location.

    Degrades to an explicit offline block when no location is available, no
    API key is configured, or the forecast call fails — never invents numbers.

    ``build_overview`` runs in a worker thread (see the race-control router,
    which offloads it via ``asyncio.to_thread``), so no event loop is running
    on this thread and ``asyncio.run`` can drive the async weather client.
    """
    location = (race or {}).get("location")
    if not location:
        return _offline_weather_block()

    try:
        weather = asyncio.run(get_weather_for_circuit(location))
    except Exception as exc:
        logger.warning("race_control.weather.failed", location=location, error=str(exc))
        return _offline_weather_block()

    current = weather.get("current") if isinstance(weather, dict) else None
    if not current or weather.get("error"):
        logger.info("race_control.weather.offline", location=location, reason=weather.get("error"))
        return _offline_weather_block()

    return {
        "rain_risk": current.get("rain_probability_pct"),
        "track_temp_c": current.get("track_temp_c"),
        "wind_kph": current.get("wind_speed_kph"),
        "confidence": WEATHER_FEED_LIVE,
    }


def build_strategy_dashboard(year: int) -> dict:
    """Build the command-center shell from schedule and standings data."""

    schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    events = []
    for _, row in schedule.iterrows():
        location = f"{row['Location']}, {row['Country']}"
        sessions = {}
        first_session_date = None
        last_session_date = None
        race_session_date = None

        for i in range(1, 6):
            name_col = f"Session{i}"
            date_col = f"Session{i}DateUtc"
            if name_col not in row or pd.isna(row[name_col]):
                continue

            session_name = row[name_col]
            session_date = row[date_col]
            if pd.isna(session_date):
                continue

            sessions[session_name] = utc_isoformat(session_date)
            timestamp = session_date.to_pydatetime()
            first_session_date = timestamp if first_session_date is None else min(first_session_date, timestamp)
            last_session_date = timestamp if last_session_date is None else max(last_session_date, timestamp)
            if session_name == "Race":
                race_session_date = timestamp

        if last_session_date and now_utc > last_session_date + pd.Timedelta(hours=3):
            status = "completed"
        elif first_session_date and now_utc >= first_session_date:
            status = "in_progress"
        else:
            status = "upcoming"

        days_until = None
        if first_session_date and status == "upcoming":
            days_until = max(0, int((first_session_date - now_utc).total_seconds() // 86400))

        events.append({
            "round": safe_int(row["RoundNumber"]),
            "name": row["EventName"],
            "location": location,
            "country": row["Country"],
            "status": status,
            "date": row["EventDate"].isoformat(),
            "sessions": sessions,
            "is_sprint": "Sprint" in sessions,
            "days_until": days_until,
            "circuit": get_circuit_info(location),
            "race_session": utc_isoformat(race_session_date) if race_session_date else None,
        })

    active_event = next((event for event in events if event["status"] == "in_progress"), None)
    next_event = next((event for event in events if event["status"] == "upcoming"), None)
    selected_event = active_event or next_event or (events[-1] if events else None)
    drivers, constructors = get_standings_snapshot(year)

    return {
        "year": year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "focus": focus_for_event(selected_event),
        "race": selected_event,
        "season": {
            "total_events": len(events),
            "completed_events": len([event for event in events if event["status"] == "completed"]),
            "upcoming_events": len([event for event in events if event["status"] == "upcoming"]),
        },
        "championship": {
            "drivers": drivers[:5],
            "constructors": constructors[:5],
        },
    }


def focus_for_event(event: dict | None) -> str:
    if not event:
        return "Season review"
    if event["status"] == "in_progress":
        return "Live session control"
    if event["days_until"] is not None and event["days_until"] <= 10:
        return "Race-week strategy lock"
    return "Pre-race simulation build"


def _weather_risk(weather: dict | None) -> dict:
    """Grade the weather risk from the live forecast block.

    Falls back to an honest "feed offline" Medium risk when no live rain
    probability is available, rather than asserting a confirmation task that
    may already be resolved.
    """
    rain = (weather or {}).get("rain_risk")
    if not isinstance(rain, (int, float)):
        return {
            "level": "Medium",
            "title": "Weather feed offline",
            "detail": "Live forecast unavailable — confirm dry/wet branches manually before lock.",
        }

    rain_pct = round(rain)
    if rain_pct >= RAIN_RISK_HIGH:
        return {
            "level": "High",
            "title": "Elevated rain risk",
            "detail": f"Live forecast shows {rain_pct}% rain probability — prime the wet branch and intermediate crossover.",
        }
    if rain_pct >= RAIN_RISK_MODERATE:
        return {
            "level": "Medium",
            "title": "Mixed conditions possible",
            "detail": f"Live forecast shows {rain_pct}% rain probability — keep the dry/wet crossover branch ready.",
        }
    return {
        "level": "Low",
        "title": "Dry conditions expected",
        "detail": f"Live forecast shows {rain_pct}% rain probability — dry strategy holds as the primary branch.",
    }


def _rival_risk(competitors: list[dict]) -> dict | None:
    """Grade the rival-offset risk from the real constructor championship gap.

    Returns ``None`` when there is no trailing rival to plan against (e.g. an
    empty standings snapshot), so the panel never shows a rival task that no
    data supports.
    """
    rivals = [row for row in (competitors or []) if row.get("rank", 0) > 1]
    if not rivals:
        return None

    closest = min(rivals, key=lambda row: row.get("gap_to_leader", float("inf")))
    gap = closest.get("gap_to_leader")
    team = closest.get("team", "the nearest rival")
    if not isinstance(gap, (int, float)):
        return None

    gap_pts = round(gap)
    if gap_pts <= RIVAL_GAP_HIGH:
        return {
            "level": "High",
            "title": "Rival offset plans",
            "detail": f"{team} is within {gap_pts} pts — rehearse undercut and overcut responses for direct track battles.",
        }
    if gap_pts <= RIVAL_GAP_MODERATE:
        return {
            "level": "Medium",
            "title": "Rival offset plans",
            "detail": f"{team} trails by {gap_pts} pts — prepare undercut and overcut responses for the closest rival.",
        }
    return {
        "level": "Low",
        "title": "Rival offset plans",
        "detail": f"Nearest rival ({team}) trails by {gap_pts} pts — lower direct championship pressure this round.",
    }


def build_risk_register(
    event: dict | None,
    weather: dict | None,
    competitors: list[dict],
) -> list[dict]:
    """Assemble the risk register from real event, weather, and standings state.

    Sprint and street risks come from the event profile; the weather and rival
    risks are graded from the live forecast block and the constructor gap so the
    cards reflect the current situation instead of fixed editorial copy.
    """
    if not event:
        return []

    risks = []
    if event["is_sprint"]:
        risks.append({
            "level": "High",
            "title": "Sprint format compression",
            "detail": "Reduced practice time increases setup and parc ferme decision pressure.",
        })
    if event["circuit"] and event["circuit"].get("circuit_type") == "Street":
        risks.append({
            "level": "High",
            "title": "Safety car exposure",
            "detail": "Street circuit profile raises track-position and pit-window volatility.",
        })

    risks.append(_weather_risk(weather))
    rival_risk = _rival_risk(competitors)
    if rival_risk:
        risks.append(rival_risk)
    return risks


def _weekend_brief_status(event: dict | None) -> str:
    if not event:
        return "Waiting"
    if event["status"] == "in_progress":
        return "Live"
    if event["status"] == "completed":
        return "Complete"
    return "Ready"


def _race_model_status(predictions: dict | None, data_source: dict) -> str:
    """Reflect whether the race model is telemetry-backed, still building, or missing."""
    if not (predictions or {}).get("predictions"):
        return "Waiting"
    return "Ready" if data_source.get("mode") == "telemetry" else "Build"


def _rival_watch_status(competitors: list[dict]) -> str:
    if not competitors:
        return "Standby"
    if any(row.get("threat") in ("Primary", "High") for row in competitors if row.get("rank", 0) > 1):
        return "Active"
    return "Monitor"


def _live_control_status(event: dict | None) -> str:
    if not event:
        return "Idle"
    if event["status"] == "in_progress":
        return "Live"
    if event["status"] == "completed":
        return "Complete"
    return "Standby"


def build_workstreams(
    event: dict | None,
    predictions: dict | None,
    strategy_context: dict,
) -> list[dict]:
    """Build the workstream board with statuses derived from live desk state.

    Priorities are fixed operational weightings (a config attribute of each
    stream), but every status reflects real progress: session state, whether the
    race model is telemetry-backed, and whether a close rival is in play.
    """
    data_source = (strategy_context or {}).get("data_source", {})
    competitors = (strategy_context or {}).get("competitors", [])
    return [
        {
            "id": "weekend-brief",
            "title": "Weekend Brief",
            "owner": "Strategy",
            "priority": "P1",
            "status": _weekend_brief_status(event),
            "href": "/race-control",
        },
        {
            "id": "race-model",
            "title": "Race Model",
            "owner": "Performance",
            "priority": "P1",
            "status": _race_model_status(predictions, data_source),
            "href": "/race-control/predictions",
        },
        {
            "id": "rival-watch",
            "title": "Rival Watch",
            "owner": "Competitor Intel",
            "priority": "P2",
            "status": _rival_watch_status(competitors),
            "href": "/race-control/teams",
        },
        {
            "id": "live-control",
            "title": "Live Control",
            "owner": "Pit Wall",
            "priority": "P1",
            "status": _live_control_status(event),
            "href": "/race-control/live",
        },
    ]


def build_overview(year: int) -> dict:
    dashboard = build_strategy_dashboard(year)
    race = dashboard.get("race")
    championship = dashboard.get("championship", {})
    constructors = championship.get("constructors", [])

    predictions = None
    if race and race.get("round"):
        try:
            predictions = get_or_compute_race_prediction(year, race["round"])
        except Exception as exc:
            logger.warning("race_control.predictions.failed", year=year, error=str(exc))

    strategy_reference = None
    if race and race.get("location"):
        try:
            strategy_reference = circuit_strategy_reference(race["location"], year)
        except Exception as exc:
            logger.warning("race_control.strategy_reference.failed", year=year, error=str(exc))

    strategy_context = build_strategy_context(race, constructors, predictions, strategy_reference)
    weather = build_weather_block(race)

    return {
        **dashboard,
        "predicted_podium": (predictions or {}).get("predictions", [])[:3],
        "strategy_context": strategy_context,
        "weather": weather,
        "risk_register": build_risk_register(race, weather, strategy_context.get("competitors", [])),
        "workstreams": build_workstreams(race, predictions, strategy_context),
        "live_status": {
            "connected": bool(race and race.get("status") == "in_progress"),
            "label": "Live session active" if race and race.get("status") == "in_progress" else "Standby",
        },
    }


def derive_traffic_threshold(reference: dict, is_street: bool) -> tuple[str, bool]:
    """Estimate how much traffic a car rejoins into after its stop.

    Returns ``(label, modeled)`` where ``label`` is ``"low"``/``"medium"``/``"high"``
    and ``modeled`` is ``True`` when the value is a circuit-shape heuristic rather
    than derived from telemetry.

    When telemetry is available the first-stop window spread is a real proxy for
    rejoin traffic: a narrow window means the field converges on the same pit lap,
    so a car emerging from the pits is more likely to rejoin into a pack. Street
    circuits raise the floor because clean air is scarce and passing is hard.
    Without telemetry, fall back to circuit shape alone and flag it as modeled.
    """
    p25 = reference.get("first_stop_p25")
    p75 = reference.get("first_stop_p75")
    if isinstance(p25, (int, float)) and isinstance(p75, (int, float)):
        window = p75 - p25
        if window <= 4:
            base = "high"
        elif window <= 9:
            base = "medium"
        else:
            base = "low"
        # Street circuits trap cars in traffic — bump one level (capped at high).
        if is_street:
            base = {"low": "medium", "medium": "high", "high": "high"}[base]
        return base, False

    return ("high" if is_street else "medium"), True


def build_strategy_context(
    race: dict | None,
    constructors: list[dict],
    predictions: dict | None,
    reference: dict | None = None,
) -> dict:
    """Build transparent decision-support context for the command center.

    When ``reference`` is supplied (real telemetry from the circuit's most
    recent completed edition), pit loss, tyre windows, stint compounds, and
    undercut/overcut deltas are sourced from that data. Otherwise the function
    falls back to circuit-shape heuristics so the panel still renders.
    """

    laps = safe_int((race or {}).get("circuit", {}).get("laps") if race else None, 58)
    circuit_type = ((race or {}).get("circuit") or {}).get("circuit_type", "Permanent")
    is_street = str(circuit_type).lower() == "street"
    is_sprint = bool((race or {}).get("is_sprint"))
    podium = (predictions or {}).get("predictions", [])[:3]
    lead_prediction = podium[0] if podium else None

    ref = reference or {}
    has_real = bool(ref)

    # Pit model — real deltas when telemetry is available, else circuit heuristics.
    pit_loss = ref.get("pit_loss_seconds") or (24 if is_street else 21)
    undercut_from_ref = ref.get("undercut_delta")
    overcut_from_ref = ref.get("overcut_delta")
    undercut_delta = undercut_from_ref or round(1.2 + (0.4 if is_street else 0.2), 1)
    overcut_delta = overcut_from_ref or round(0.8 + (0.2 if is_sprint else 0.1), 1)
    traffic_threshold, traffic_modeled = derive_traffic_threshold(ref, is_street)

    # Tyre windows — real first-stop distribution when available.
    primary_stop = ref.get("median_first_stop") or max(
        16, min(laps - 18, round(laps * (0.38 if is_street else 0.42)))
    )
    offset_stop = ref.get("first_stop_p25") or max(10, primary_stop - (5 if is_street else 4))
    late_stop = min(laps - 8, (ref.get("first_stop_p75") or primary_stop) + (8 if is_street else 10))

    opening_compound = ref.get("opening_compound") or "Medium"
    finishing_compound = ref.get("finishing_compound") or "Hard"
    most_common_stops = ref.get("most_common_stops")
    stop_word = {1: "one-stop", 2: "two-stop", 3: "three-stop"}.get(most_common_stops, "one-stop")
    # Alternate branch to keep ready: two-stop backs a one-stop (or heuristic) base, and vice versa.
    alt_word = "one-stop" if isinstance(most_common_stops, int) and most_common_stops >= 2 else "two-stop"

    if has_real:
        primary_summary = (
            f"Field ran a {opening_compound}-to-{finishing_compound} {stop_word} here in "
            f"{ref['source_year']} (median first stop L{primary_stop}, {ref['sample_size']}-car sample); "
            f"keep a {alt_word} branch open if degradation shifts the crossover."
        )
        primary_confidence = "high" if lead_prediction else "medium"
    else:
        primary_summary = (
            f"Model a medium-to-hard one-stop around L{primary_stop}; keep a two-stop branch "
            "open if tyre age exceeds the working life before the stop."
        )
        primary_confidence = "medium" if lead_prediction else "low"

    if has_real:
        assumptions = [
            f"Pit loss, tyre windows, and stint compounds are derived from the {ref['source_year']} "
            f"race telemetry for this circuit (FastF1, {ref['sample_size']}-car sample).",
            "Undercut and overcut deltas remain modeled estimates — stint pace data is not yet fuel-corrected per compound.",
            "Weather is not treated as live until an external forecast feed is connected.",
        ]
    else:
        assumptions = [
            "Race context is derived from the season schedule, circuit metadata, standings, and cached prediction snapshots.",
            "Weather is not treated as live until an external forecast feed is connected.",
            "Tyre windows are planning heuristics — no completed edition of this circuit was available for telemetry.",
        ]

    competitor_rows = []
    leader_points = constructors[0]["points"] if constructors else 0
    for index, team in enumerate(constructors[:5], start=1):
        gap = max(0, leader_points - team["points"])
        competitor_rows.append({
            "rank": index,
            "team": team["team"],
            "points": team["points"],
            "gap_to_leader": round(gap, 1),
            "threat": "Primary" if index == 1 else "High" if gap <= 60 else "Monitor",
            "operating_read": (
                "Benchmark car; protect against clean-air extensions."
                if index == 1
                else "Undercut exposure if they qualify within one pit-loss window."
                if gap <= 60
                else "Scenario dependent; watch safety-car offsets."
            ),
        })

    return {
        "phase": "Live race desk" if race and race.get("status") == "in_progress" else "Pre-race build",
        "primary_call": {
            "title": "Base race plan",
            "summary": primary_summary,
            "confidence": primary_confidence,
        },
        "data_source": {
            "mode": "telemetry" if has_real else "heuristic",
            "edition_year": ref.get("source_year"),
            "sample_size": ref.get("sample_size"),
        },
        "decision_gates": [
            {
                "gate": "Parc ferme lock",
                "trigger": "After qualifying",
                "owner": "Performance",
                "decision": "Freeze wing level and cooling assumptions before strategy branches are finalised.",
            },
            {
                "gate": "First stop call",
                "trigger": f"L{offset_stop}-L{primary_stop}",
                "owner": "Strategy",
                "decision": (
                    f"Undercut is worth ~{undercut_delta}s here; commit only if the rival gap is inside that "
                    f"window and rejoin traffic stays {traffic_threshold} or lower."
                ),
            },
            {
                "gate": "Safety-car branch",
                "trigger": f"L{primary_stop}-L{late_stop}",
                "owner": "Pit Wall",
                "decision": (
                    f"Box if a safety car opens a near-free stop (~{pit_loss}s pit loss) or a tyre offset "
                    "protects track position."
                ),
            },
        ],
        "stint_plan": [
            {
                "stint": "Opening",
                "compound": opening_compound,
                "window": f"L1-L{primary_stop}",
                "target": f"Hold {opening_compound} surface temperatures and avoid opening-lap traffic damage.",
            },
            {
                "stint": "Race finish",
                "compound": finishing_compound,
                "window": f"L{primary_stop + 1}-L{laps}",
                "target": f"Protect track position on {finishing_compound}; switch to a {alt_word} if degradation crosses the cliff.",
            },
        ],
        "pit_model": {
            "pit_loss_seconds": pit_loss,
            "undercut_delta": undercut_delta,
            "overcut_delta": overcut_delta,
            "undercut_modeled": not undercut_from_ref,
            "overcut_modeled": not overcut_from_ref,
            "traffic_threshold": traffic_threshold,
            "traffic_modeled": traffic_modeled,
        },
        "stint_windows": {
            "total_laps": laps,
            "opening_compound": opening_compound,
            "finishing_compound": finishing_compound,
            "offset_lap": offset_stop,
            "primary_lap": primary_stop,
            "late_lap": late_stop,
            "modeled": not has_real,
        },
        "competitors": competitor_rows,
        "assumptions": assumptions,
    }
