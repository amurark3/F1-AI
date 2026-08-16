"""Strategy context: the dashboard block and the numbers behind it."""

from __future__ import annotations

from datetime import datetime, timezone

import fastf1
import pandas as pd
import structlog

from app.api.circuits import get_circuit_info
from app.services.race_control.workstreams import focus_for_event
from app.services.race_control_common import get_standings_snapshot, safe_int
from app.utils.f1_values import utc_isoformat

logger = structlog.get_logger()


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

        events.append(
            {
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
            }
        )

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
    primary_stop = ref.get("median_first_stop") or max(16, min(laps - 18, round(laps * (0.38 if is_street else 0.42))))
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
        competitor_rows.append(
            {
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
            }
        )

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
