"""Session-classification tools: sprint, sprint qualifying and qualifying.

Every table is read from f1db, or OpenF1 until f1db holds the round, and says
which. A car that did not finish reads DNF with its reason, never a place.
"""

from __future__ import annotations

from langchain_core.tools import tool
import structlog

from app.api.errors import tool_error_text
from app.api.tools.provenance import Provenance, Sourced, classification_chips
from app.api.tools.rounds import resolve_event
from app.data.qualifying_times import QualifyingCar, QualifyingTimes, qualifying_times
from app.services.race_results import build_session_result, clock

logger = structlog.get_logger()

NO_TIME = "-"


def source_line(final: bool) -> str:
    """Which source the table is read from, and whether it is the final classification."""
    if final:
        return "*(Source: the FIA final classification)*"
    return "*(Source: OpenF1, provisional until the FIA final classification is published)*"


def driver_label(name: str, code: str) -> str:
    """'Kimi Antonelli (ANT)': the name f1db gives the driver, with the code as a handle."""
    return f"{name} ({code})" if name and code else name or code or NO_TIME


def time_cell(row: dict) -> str:
    """Race time, gap, laps down, or how the car's race ended (DNF with its reason, DNS, DSQ, NC)."""
    status = row["status"]
    if status != "Finished":
        return f"❌ {status}" + (f" ({row['reason']})" if row["reason"] else "")
    text = row["time"] if row["position"] == 1 else row["gap"]
    penalty = f" (incl. {row['time_penalty']}s penalty)" if row["time_penalty"] else ""
    return (text or "Interval") + penalty


def points_cell(points: float | None) -> str:
    return f"{points or 0:g}"


def _header(*value_labels: str) -> list[str]:
    """Column headings and the alignment row for one classification table."""
    alignments = (f":{'-' * (len(label) - 1)}" for label in value_labels)
    return [
        f"| Pos | Driver | Team | {' | '.join(value_labels)} |",
        f"| :-- | :----- | :--- | {' | '.join(alignments)} |",
    ]


def _row(position: object, name: str, code: str, team: str, *values: str) -> str:
    return f"| {position} | {driver_label(name, code)} | {team or NO_TIME} | {' | '.join(values)} |"


@tool
def get_sprint_results(year: int, grand_prix: str) -> str:
    """
    Fetches the SATURDAY SPRINT RACE results (the short 100 km race) of ONE
    Grand Prix — for 'Sprint', 'Sprint Race' or 'Saturday Race'. Do NOT use
    get_race_results for a sprint. For sprints across several weekends, use
    one query_f1_database query instead of calling this per weekend.

    Returns a Markdown table of finishing positions, drivers, teams, times /
    DNF reasons, and the sprint points each scored.
    """
    logger.info("tool.sprint_results", grand_prix=grand_prix, year=year)
    try:
        round_num, event_name = resolve_event(year, grand_prix)
        sprint = build_session_result(year, round_num, "sprint")
        if sprint is None:
            return (
                f"No sprint classification is published for {grand_prix} {year} (not a sprint weekend, or not run yet)."
            )
        rows = [
            _row(
                row["position"] or row["status"],
                row["driver_name"],
                row["driver_code"],
                row["team"],
                time_cell(row),
                points_cell(row["points"]),
            )
            for row in sprint["classification"]
        ]
        heading = [
            f"### Sprint Race Results: {grand_prix} {year}",
            source_line(sprint["final"]),
            "",
            *_header("Time/Status", "Pts"),
        ]
        provenance = Provenance(
            sources=classification_chips(sprint["sources"], final=sprint["final"]),
            subject=f"{event_name} {year} sprint",
        )
        return Sourced("\n".join([*heading, *rows]), provenance)
    except Exception as e:
        return f"Could not fetch Sprint results: {tool_error_text('tool.get_sprint_results.failed', e)}"


def _time_cell(seconds: float, note: str | None) -> str:
    return clock(round(seconds * 1000)) + (f" ({note})" if note else "")


def _segment_table(cars: tuple[QualifyingCar, ...], index: int, title: str, label: str) -> list[str]:
    """One segment's table: the cars that set a time in it, fastest first; empty when none did."""
    timed = sorted(((car, time) for car in cars if (time := car.times[index]) is not None), key=lambda pair: pair[1])
    if not timed:
        return []
    rows = [
        _row(rank, car.name, car.code, car.team, _time_cell(time, car.note))
        for rank, (car, time) in enumerate(timed, 1)
    ]
    return [title, *_header(f"{label} Time"), *rows]


def _qualifying_report(table: QualifyingTimes, prefix: str, heading: str, subject: str) -> Sourced:
    """The Q1/Q2/Q3 tables (``prefix`` "Q" or "SQ"), or an ordered list when the cars carry no segment times."""
    cars = table.cars
    pole = "Sprint Pole Position" if prefix == "SQ" else "Pole Position"
    titles = (f"### {prefix}1 Results ({heading})", f"### {prefix}2 Results", f"### {prefix}3 Results ({pole})")
    tables = [_segment_table(cars, index, title, f"{prefix}{index + 1}") for index, title in enumerate(titles)]
    shown = [lines for lines in tables if lines]
    provenance = Provenance(
        sources=classification_chips(({"source": table.source},), final=table.final), subject=subject
    )
    if shown:
        body = [line for lines in shown[:-1] for line in (*lines, "\n---\n")] + shown[-1]
        return Sourced("\n".join([source_line(table.final), "", *body]), provenance)
    ordered = sorted(cars, key=lambda car: car.position or len(cars) + 1)
    rows = [_row(car.position or car.note, car.name, car.code, car.team, NO_TIME) for car in ordered]
    text = "\n".join(
        [
            f"### {prefix} Classification ({heading})",
            source_line(table.final),
            f"*(Detailed {prefix}1/{prefix}2/{prefix}3 split data currently unavailable)*\n",
            *_header("Time"),
            *rows,
        ]
    )
    return Sourced(text, provenance)


@tool
def get_sprint_qualifying_results(year: int, grand_prix: str) -> str:
    """Fetches SPRINT QUALIFYING (Shootout) results, split SQ1/SQ2/SQ3.

    Use for 'Sprint Qualifying', 'Shootout', 'SQ' or 'Sprint Quali' — NOT
    get_qualifying_results.
    """
    logger.info("tool.sprint_qualifying", grand_prix=grand_prix, year=year)
    try:
        round_num, event_name = resolve_event(year, grand_prix)
        table = qualifying_times(year, round_num, "SQ")
        if table is None:
            return f"No sprint qualifying results are published for {grand_prix} {year} (not a sprint weekend, or not run yet)."
        return _qualifying_report(table, "SQ", f"{grand_prix} {year}", f"{event_name} {year} sprint qualifying")
    except Exception as e:
        return f"Could not fetch Sprint Qualifying. Note: {grand_prix} {year} might not be a Sprint weekend. Error: {tool_error_text('tool.get_sprint_qualifying_results.failed', e)}"


@tool
def get_qualifying_results(year: int, grand_prix: str) -> str:
    """
    Fetches the MAIN QUALIFYING results (determines the Sunday race grid).

    Returns separate tables for Q1, Q2, and Q3 with each driver's best
    lap time for that session segment.

    IMPORTANT: Do NOT use this for Sprint Qualifying / Shootout sessions.
    Use get_sprint_qualifying_results for those.
    """
    logger.info("tool.qualifying", grand_prix=grand_prix, year=year)
    try:
        round_num, event_name = resolve_event(year, grand_prix)
        table = qualifying_times(year, round_num, "Q")
        if table is None:
            return f"No qualifying results are published for {grand_prix} {year} yet."
        return _qualifying_report(table, "Q", f"{grand_prix} {year}", f"{event_name} {year} qualifying")
    except Exception as e:
        return f"Failed to fetch qualifying results: {tool_error_text('tool.get_qualifying_results.failed', e)}"
