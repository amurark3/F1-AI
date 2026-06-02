"""Race Control strategy simulation service.

This module owns the pit-strategy workflow so the Race Control facade does not
grow into a God object. The important boundary is data provenance: observed
FastF1 evidence is separated from user-provided scenario inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.api.schemas.race_control import StrategySimulationRequest
from app.data.strategy import analyze_pit_strategy

logger = structlog.get_logger()

MAX_GRID_POSITION = 22
BASELINE_TYRE_LIFE = {
    "SOFT": 18,
    "MEDIUM": 29,
    "HARD": 42,
    "INTERMEDIATE": 24,
    "WET": 20,
}


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def resolve_strategy_race(year: int, race_name: str | None) -> dict | None:
    """Resolve the requested/current race without depending on the facade."""

    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception as exc:
        logger.warning("race_control_strategy.schedule_failed", year=year, error=str(exc))
        return None

    events = [event_from_schedule_row(row) for _, row in schedule.iterrows()]
    if race_name and race_name not in {"Next Grand Prix", "Selected Grand Prix"}:
        requested = race_name.strip().lower()
        explicit = next((event for event in events if event["name"].lower() == requested), None)
        if explicit:
            return explicit

    active = next((event for event in events if event["status"] == "in_progress"), None)
    upcoming = next((event for event in events if event["status"] == "upcoming"), None)
    return active or upcoming or (events[-1] if events else None)


def event_from_schedule_row(row: pd.Series) -> dict:
    location = f"{row['Location']}, {row['Country']}"
    first_session_date = None
    last_session_date = None

    for i in range(1, 6):
        name_col = f"Session{i}"
        date_col = f"Session{i}DateUtc"
        if name_col not in row or pd.isna(row[name_col]) or pd.isna(row[date_col]):
            continue
        timestamp = row[date_col].to_pydatetime()
        first_session_date = timestamp if first_session_date is None else min(first_session_date, timestamp)
        last_session_date = timestamp if last_session_date is None else max(last_session_date, timestamp)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if last_session_date and now_utc > last_session_date + pd.Timedelta(hours=3):
        status = "completed"
    elif first_session_date and now_utc >= first_session_date:
        status = "in_progress"
    else:
        status = "upcoming"

    return {
        "round": safe_int(row["RoundNumber"]),
        "name": row["EventName"],
        "location": location,
        "country": row["Country"],
        "status": status,
        "circuit": get_circuit_info(location),
    }


def resolve_strategy_reference(year: int, race_name: str | None) -> dict:
    """Find the best real-data strategy reference for the simulator."""

    race = resolve_strategy_race(year, race_name)
    candidates: list[dict] = []

    if race and race.get("round") and race.get("status") == "completed":
        candidates.append({
            "year": year,
            "round": race["round"],
            "label": f"{year} {race['name']}",
            "kind": "completed selected race",
        })

    location = (race or {}).get("location", "")
    event_name = (race or {}).get("name", "")
    schedule_location = location.split(",")[0].strip()
    for past_year in range(year - 1, max(year - 5, 2018), -1):
        previous_round = find_round_for_strategy_reference(past_year, schedule_location, event_name)
        if previous_round:
            candidates.append({
                "year": past_year,
                "round": previous_round["round"],
                "label": f"{past_year} {previous_round['name']}",
                "kind": "previous edition of this circuit",
            })

    for candidate in candidates:
        try:
            analysis = analyze_pit_strategy(candidate["year"], candidate["round"], None)
            if not analysis.get("error"):
                return {
                    "status": "available",
                    "race": race,
                    "source": candidate,
                    "analysis": analysis,
                    "summary": f"Using FastF1 race lap data from {candidate['label']}.",
                }
        except Exception as exc:
            logger.debug("race_control_strategy.reference_failed", candidate=candidate, error=str(exc))

    return {
        "status": "unavailable",
        "race": race,
        "source": None,
        "analysis": None,
        "summary": "No FastF1 race-lap reference is available for this event yet.",
    }


def find_round_for_strategy_reference(year: int, location: str, event_name: str) -> dict | None:
    try:
        schedule = fastf1.get_event_schedule(year=year, include_testing=False)
    except Exception:
        return None

    location_key = location.strip().lower()
    event_key = event_name.strip().lower()
    for _, row in schedule.iterrows():
        row_location = str(row.get("Location", "")).strip().lower()
        row_event = str(row.get("EventName", "")).strip().lower()
        if location_key and row_location == location_key:
            return {"round": safe_int(row["RoundNumber"]), "name": row["EventName"]}
        if event_key and row_event == event_key:
            return {"round": safe_int(row["RoundNumber"]), "name": row["EventName"]}
    return None


def compound_reference_for_strategy(reference: dict, compound: str) -> dict:
    analysis = reference.get("analysis") or {}
    for row in analysis.get("compound_summary") or []:
        if str(row.get("compound", "")).upper() == compound:
            return {
                "compound_life": safe_int(row.get("p75_stint"), 0) or safe_int(row.get("median_stint"), 0),
                "median_stint": row.get("median_stint"),
                "p75_stint": row.get("p75_stint"),
                "max_observed_stint": row.get("max_observed_stint"),
                "sample_size": row.get("sample_size"),
                "avg_degradation_sec": row.get("avg_degradation_sec"),
                "source": "FastF1 observed race stints",
                "status": "observed",
            }

    baseline = BASELINE_TYRE_LIFE.get(compound, BASELINE_TYRE_LIFE["MEDIUM"])
    return {
        "compound_life": baseline,
        "median_stint": None,
        "p75_stint": None,
        "max_observed_stint": None,
        "sample_size": 0,
        "avg_degradation_sec": None,
        "source": "planning baseline; no matching FastF1 stint sample",
        "status": "baseline",
    }


def first_stop_reference(reference: dict) -> dict:
    analysis = reference.get("analysis") or {}
    window = analysis.get("first_stop_window") or {}
    if window.get("sample_size"):
        return {
            "sample_size": window.get("sample_size"),
            "p25": window.get("p25"),
            "median": window.get("median"),
            "p75": window.get("p75"),
            "source": "FastF1 first pit-stop laps",
            "status": "observed",
        }
    return {
        "sample_size": 0,
        "p25": None,
        "median": None,
        "p75": None,
        "source": "No observed first-stop window loaded",
        "status": "unavailable",
    }


def stop_count_reference(reference: dict) -> dict:
    analysis = reference.get("analysis") or {}
    stop_summary = analysis.get("stop_count_summary") or {}
    if stop_summary.get("sample_size"):
        return {
            "sample_size": stop_summary.get("sample_size"),
            "median": stop_summary.get("median"),
            "most_common": stop_summary.get("most_common"),
            "source": "FastF1 race stint count distribution",
            "status": "observed",
        }
    return {
        "sample_size": 0,
        "median": None,
        "most_common": None,
        "source": "No observed stop-count distribution loaded",
        "status": "unavailable",
    }


def strategy_source_cards(reference: dict, compound_ref: dict, first_stop_ref: dict, stop_count_ref: dict) -> list[dict]:
    race = reference.get("race") or {}
    circuit = race.get("circuit") or {}
    source = reference.get("source") or {}
    return [
        {
            "label": "Circuit",
            "status": "available" if circuit else "missing",
            "value": circuit.get("circuit_name") or race.get("name") or "No circuit loaded",
            "source": "FastF1 schedule + local circuit metadata" if circuit else "schedule unavailable",
        },
        {
            "label": "Race-lap reference",
            "status": reference.get("status"),
            "value": source.get("label") or "Not loaded",
            "source": reference.get("summary"),
        },
        {
            "label": "Tyre-life reference",
            "status": compound_ref.get("status"),
            "value": (
                f"{compound_ref['compound_life']} laps from {compound_ref.get('sample_size', 0)} stints"
                if compound_ref.get("status") == "observed"
                else f"{compound_ref['compound_life']} lap baseline"
            ),
            "source": compound_ref.get("source"),
        },
        {
            "label": "First-stop window",
            "status": first_stop_ref.get("status"),
            "value": format_first_stop_window(first_stop_ref),
            "source": first_stop_ref.get("source"),
        },
        {
            "label": "Stop-count tendency",
            "status": stop_count_ref.get("status"),
            "value": format_stop_count(stop_count_ref),
            "source": stop_count_ref.get("source"),
        },
    ]


def simulate_strategy(request: StrategySimulationRequest) -> dict:
    reference = resolve_strategy_reference(request.year, request.race)
    race = reference.get("race") or {}
    circuit = race.get("circuit") or {}
    total_laps = safe_int(circuit.get("laps"), 70)

    start = max(1, min(MAX_GRID_POSITION, request.starting_position))
    current_lap = max(1, min(total_laps, request.current_lap))
    pit_lap = max(1, min(total_laps, request.pit_lap))
    if pit_lap <= current_lap:
        pit_lap = min(total_laps, current_lap + 1)

    safety = max(0, min(100, request.safety_car_probability))
    weather = max(0, min(100, request.weather_risk))
    traffic = max(0, min(100, request.traffic_risk))
    compound = request.tyre_compound.upper()

    compound_ref = compound_reference_for_strategy(reference, compound)
    first_stop_ref = first_stop_reference(reference)
    stop_count_ref = stop_count_reference(reference)
    compound_life = safe_int(compound_ref.get("compound_life"), BASELINE_TYRE_LIFE["MEDIUM"])

    current_tyre_age = max(0, min(70, request.tyre_age))
    laps_to_stop = max(0, pit_lap - current_lap)
    tyre_age_at_stop = current_tyre_age + laps_to_stop
    life_used = tyre_age_at_stop / compound_life

    observed_degradation = compound_ref.get("avg_degradation_sec")
    degradation = max(
        0.7,
        life_used * 1.15
        + (float(observed_degradation) / 6 if isinstance(observed_degradation, (int, float)) else 0)
        + weather / 220
        + traffic / 320,
    )
    undercut_power = max(0, 2.4 - degradation + traffic / 150 + (start / 30))
    overcut_power = max(0, 1.8 - undercut_power / 2 + safety / 110 - max(0, life_used - 0.85) * 0.55)

    first_stop_alignment = first_stop_alignment_score(first_stop_ref, pit_lap)
    observed_stop_bias = stop_count_bias(stop_count_ref)
    one_stop_score, two_stop_score = score_stop_branches(
        degradation=degradation,
        safety=safety,
        weather=weather,
        traffic=traffic,
        tyre_age_at_stop=tyre_age_at_stop,
        compound_life=compound_life,
        start=start,
        first_stop_alignment=first_stop_alignment,
        observed_stop_bias=observed_stop_bias,
    )

    recommended = "One-stop" if one_stop_score >= two_stop_score else "Two-stop"
    branch_delta = round(abs(one_stop_score - two_stop_score), 1)
    confidence = "High" if branch_delta >= 12 else "Medium" if branch_delta >= 5 else "Low"
    source_cards = strategy_source_cards(reference, compound_ref, first_stop_ref, stop_count_ref)
    observed_sources = len([card for card in source_cards if card["status"] in {"available", "observed"}])

    return {
        "race": request.race,
        "team": request.team,
        "driver": request.driver,
        "inputs": request.model_dump(),
        "data_quality": {
            "grade": "Data-backed" if observed_sources >= 4 else "Partial data" if observed_sources >= 2 else "Scenario-only",
            "observed_sources": observed_sources,
            "total_sources": len(source_cards),
            "scenario_inputs": ["track position", "current lap", "tyre age", "target pit lap", "traffic risk", "safety-car probability", "rain risk"],
            "note": "User scenario inputs are kept separate from observed FastF1/Jolpica evidence.",
        },
        "data_sources": source_cards,
        "reference": {
            "status": reference.get("status"),
            "summary": reference.get("summary"),
            "race": {
                "name": race.get("name"),
                "round": race.get("round"),
                "location": race.get("location"),
                "status": race.get("status"),
                "total_laps": total_laps,
                "circuit": circuit.get("circuit_name"),
            },
        },
        "recommendation": {
            "plan": recommended,
            "pit_window": recommended_pit_window(recommended, pit_lap, total_laps),
            "confidence": confidence,
            "branch_delta": branch_delta,
            "rationale": recommendation_rationale(recommended),
        },
        "stint": {
            "current_lap": current_lap,
            "tyre_age_now": current_tyre_age,
            "tyre_age_at_stop": tyre_age_at_stop,
            "compound_life": compound_life,
            "compound_reference_source": compound_ref.get("source"),
            "compound_reference_status": compound_ref.get("status"),
            "life_used_pct": round(life_used * 100),
            "laps_to_stop": laps_to_stop,
        },
        "plans": [
            build_one_stop_plan(start, pit_lap, total_laps, one_stop_score, degradation, weather, tyre_age_at_stop, compound_life, traffic, first_stop_ref),
            build_two_stop_plan(start, pit_lap, total_laps, two_stop_score, safety, traffic, tyre_age_at_stop, stop_count_ref),
        ],
        "model_inputs": build_strategy_model_inputs(
            request,
            compound_life,
            tyre_age_at_stop,
            degradation,
            undercut_power,
            overcut_power,
            compound_ref,
            first_stop_ref,
            stop_count_ref,
        ),
        "decision_matrix": build_strategy_decision_matrix(
            recommended,
            one_stop_score,
            two_stop_score,
            tyre_age_at_stop,
            compound_life,
            traffic,
            safety,
            weather,
        ),
        "battle_cards": [
            {"label": "Tyre margin", "value": f"{compound_life - tyre_age_at_stop:+d} laps", "call": compound_ref.get("source")},
            {"label": "First-stop reference", "value": format_first_stop_window(first_stop_ref), "call": first_stop_ref.get("source")},
            {"label": "Stop tendency", "value": format_stop_count(stop_count_ref), "call": stop_count_ref.get("source")},
            {"label": "Scenario risk", "value": f"{traffic}% traffic / {weather}% rain", "call": "User scenario input"},
        ],
    }


def first_stop_alignment_score(first_stop_ref: dict, pit_lap: int) -> float:
    if first_stop_ref.get("status") != "observed" or first_stop_ref.get("median") is None:
        return 0.0
    median_stop = float(first_stop_ref["median"])
    return max(0, 8 - abs(pit_lap - median_stop))


def stop_count_bias(stop_count_ref: dict) -> int:
    if stop_count_ref.get("status") != "observed":
        return 0
    most_common = safe_int(stop_count_ref.get("most_common"), 1)
    if most_common <= 1:
        return 1
    if most_common >= 2:
        return -1
    return 0


def score_stop_branches(
    *,
    degradation: float,
    safety: int,
    weather: int,
    traffic: int,
    tyre_age_at_stop: int,
    compound_life: int,
    start: int,
    first_stop_alignment: float,
    observed_stop_bias: int,
) -> tuple[float, float]:
    one_stop_score = (
        88
        - degradation * 15
        + safety * 0.16
        - weather * 0.12
        - traffic * 0.06
        - max(0, tyre_age_at_stop - compound_life) * 1.45
        + first_stop_alignment * 0.7
        + observed_stop_bias * 5
    )
    two_stop_score = (
        78
        + degradation * 11
        + weather * 0.16
        + traffic * 0.05
        - safety * 0.07
        - max(0, start - 8) * 0.55
        - first_stop_alignment * 0.25
        - observed_stop_bias * 5
    )
    return one_stop_score, two_stop_score


def recommendation_rationale(recommended: str) -> str:
    if recommended == "One-stop":
        return "Track position is favored and the target stop fits the loaded tyre-life reference."
    return "Tyre age, traffic, or observed stop-count tendency make a second stop worth modelling."


def build_strategy_model_inputs(
    request: StrategySimulationRequest,
    compound_life: int,
    tyre_age_at_stop: int,
    degradation: float,
    undercut_power: float,
    overcut_power: float,
    compound_ref: dict,
    first_stop_ref: dict,
    stop_count_ref: dict,
) -> list[dict]:
    tyre_margin = compound_life - tyre_age_at_stop
    return [
        {
            "label": "Tyre life margin",
            "value": f"{tyre_margin:+d} laps",
            "impact": "Positive margin supports extending; negative margin pushes toward a second stop.",
            "source": f"{request.tyre_compound.upper()} reference: {compound_ref.get('source')}",
            "tone": "good" if tyre_margin >= 5 else "warning" if tyre_margin >= 0 else "critical",
        },
        {
            "label": "Stint pressure",
            "value": f"{degradation:.2f}",
            "impact": "Combines tyre age, loaded degradation evidence, and scenario risk inputs into the stop-pressure index.",
            "source": "FastF1 compound degradation when available; scenario risks otherwise",
            "tone": "critical" if degradation > 1.55 else "warning" if degradation > 1.25 else "good",
        },
        {
            "label": "First-stop evidence",
            "value": format_first_stop_window(first_stop_ref),
            "impact": "Shows whether the tested pit lap is near the observed first-stop range for this race reference.",
            "source": first_stop_ref.get("source"),
            "tone": "good" if first_stop_ref.get("status") == "observed" else "warning",
        },
        {
            "label": "Stop-count tendency",
            "value": format_stop_count(stop_count_ref),
            "impact": "Uses observed stint counts to bias the call toward one-stop or two-stop only when real race-lap data exists.",
            "source": stop_count_ref.get("source"),
            "tone": "good" if stop_count_ref.get("status") == "observed" else "warning",
        },
        {
            "label": "Undercut pressure",
            "value": f"{undercut_power:.2f}",
            "impact": "Scenario index for stopping earlier than rivals; it is not shown as live timing delta.",
            "source": "track position + traffic scenario + stint pressure",
            "tone": "good" if undercut_power >= 1.5 else "warning",
        },
        {
            "label": "Overcut pressure",
            "value": f"{overcut_power:.2f}",
            "impact": "Scenario index for extending the stint; it is not shown as live timing delta.",
            "source": "safety-car scenario + tyre-life reserve",
            "tone": "good" if overcut_power >= 1.3 else "warning",
        },
    ]


def build_strategy_decision_matrix(
    recommended: str,
    one_stop_score: float,
    two_stop_score: float,
    tyre_age_at_stop: int,
    compound_life: int,
    traffic: int,
    safety: int,
    weather: int,
) -> list[dict]:
    return [
        {
            "gate": "Commit / keep open",
            "status": "Commit" if abs(one_stop_score - two_stop_score) >= 12 else "Keep both branches open",
            "detail": f"{recommended} leads by {abs(one_stop_score - two_stop_score):.1f} model points.",
        },
        {
            "gate": "Tyre cliff",
            "status": "Critical" if tyre_age_at_stop > compound_life else "Inside life",
            "detail": f"Target stop reaches {tyre_age_at_stop} laps against a {compound_life}-lap reference.",
        },
        {
            "gate": "Rejoin traffic",
            "status": "Hold" if traffic >= 65 else "Attack window usable",
            "detail": f"Traffic risk is {traffic}%; this is a scenario input, not live telemetry.",
        },
        {
            "gate": "Race disruption",
            "status": "Prepare branch" if safety >= 45 or weather >= 45 else "Base plan",
            "detail": f"Safety car {safety}% and rain {weather}% are scenario inputs unless a live feed is connected.",
        },
    ]


def format_first_stop_window(first_stop_ref: dict) -> str:
    if first_stop_ref.get("status") == "observed":
        return f"L{first_stop_ref.get('p25')}-L{first_stop_ref.get('p75')}"
    return "Not loaded"


def format_stop_count(stop_count_ref: dict) -> str:
    if stop_count_ref.get("status") == "observed":
        return f"{safe_int(stop_count_ref.get('most_common'), 0)}-stop"
    return "Not loaded"


def recommended_pit_window(plan: str, pit_lap: int, total_laps: int = 70) -> str:
    start = max(1, pit_lap - (4 if plan == "One-stop" else 3))
    end = min(total_laps, pit_lap + (5 if plan == "One-stop" else 3))
    return f"L{start}-L{end}"


def build_one_stop_plan(
    start: int,
    pit_lap: int,
    total_laps: int,
    score: float,
    degradation: float,
    weather: int,
    tyre_age_at_stop: int,
    compound_life: int,
    traffic: int,
    first_stop_ref: dict,
) -> dict:
    expected_finish = max(1, min(MAX_GRID_POSITION, round(start - (score - 70) / 8)))
    tyre_note = f"Tyres reach lap {tyre_age_at_stop} at the stop; reference life is {compound_life} laps"
    reference_note = (
        f"Observed first-stop window: {format_first_stop_window(first_stop_ref)}"
        if first_stop_ref.get("status") == "observed"
        else "No observed first-stop window is loaded for this race reference"
    )
    return {
        "name": "One-stop",
        "score": round(score, 1),
        "expected_finish": f"P{expected_finish}",
        "pit_window": recommended_pit_window("One-stop", pit_lap, total_laps),
        "risk": "High" if degradation > 1.55 or weather > 55 or traffic > 70 else "Medium",
        "notes": [tyre_note, reference_note, "Protect clean air", "Avoid pitting into traffic"],
    }


def build_two_stop_plan(
    start: int,
    pit_lap: int,
    total_laps: int,
    score: float,
    safety: int,
    traffic: int,
    tyre_age_at_stop: int,
    stop_count_ref: dict,
) -> dict:
    expected_finish = max(1, min(MAX_GRID_POSITION, round(start - (score - 70) / 8 + 1)))
    second_stop = min(total_laps - 2, pit_lap + 12)
    reference_note = (
        f"Observed stop tendency: {format_stop_count(stop_count_ref)}"
        if stop_count_ref.get("status") == "observed"
        else "No observed stop-count tendency is loaded for this race reference"
    )
    return {
        "name": "Two-stop",
        "score": round(score, 1),
        "expected_finish": f"P{expected_finish}",
        "pit_window": f"L{max(1, pit_lap - 10)} and L{second_stop}",
        "risk": "High" if start > 10 and safety < 25 and traffic > 55 else "Medium",
        "notes": [f"First stop catches tyres at lap {tyre_age_at_stop}", reference_note, "Needs overtake delta", "Avoid if DRS trains are likely"],
    }
