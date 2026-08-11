"""Prediction and pit-strategy tools."""

from __future__ import annotations

from langchain_core.tools import tool
import structlog

from app.data.strategy import analyze_pit_strategy
from app.services.predictions import get_or_compute_race_prediction

logger = structlog.get_logger()


@tool
def get_race_predictions(year: int, round_num: int) -> str:
    """
    Predicts race finishing order for all 20 drivers with confidence ranges
    and reasoning factors.

    Use when user asks about race predictions, who will win, expected race
    results, or finishing order.

    Returns a rich race-engineer briefing with narrative reasoning,
    driver-by-driver analysis for the top 5, summary table for positions
    6-20, confidence ranges, and accuracy statistics.
    """
    logger.info("tool.race_predictions", year=year, round_num=round_num)
    try:
        result = get_or_compute_race_prediction(year, round_num)

        if not result.get("predictions"):
            warnings = result.get("warnings", [])
            return f"Could not generate predictions for {year} Round {round_num}. {'; '.join(warnings) if warnings else 'No driver data available.'}"

        predictions = result["predictions"]
        gp_name = result.get("grand_prix", f"Round {round_num}")
        data_sources = result.get("data_sources", [])
        accuracy = result.get("accuracy", {})
        warnings = result.get("warnings", [])

        # Build race-engineer briefing
        lines = []
        lines.append(f"### Race Prediction: {gp_name} {year}")
        lines.append("")

        # Narrative intro
        if predictions:
            top1 = predictions[0]
            top3 = predictions[:3]
            top3_names = ", ".join(p["driver_name"] for p in top3)
            lines.append(
                f"Based on my analysis of qualifying pace and recent form, "
                f"**{top1['driver_name']}** ({top1['team']}) is my top pick "
                f"for the win with {top1['confidence_low']}-{top1['confidence_high']}% confidence."
            )
            lines.append(f"Predicted podium: {top3_names}")
            lines.append("")

        # Top 5 detailed analysis
        lines.append("#### Top 5 - Detailed Analysis")
        lines.append("")
        for p in predictions[:5]:
            factors_str = "; ".join(p.get("factors", []))
            lines.append(
                f"**P{p['position']}. {p['driver_name']}** ({p['team']}) "
                f"[{p['confidence_low']}-{p['confidence_high']}% confidence]"
            )
            lines.append(f"  Key factors: {factors_str}")
            lines.append("")

        # Positions 6-20 summary table
        if len(predictions) > 5:
            lines.append("#### Positions 6-20")
            lines.append("| Pos | Driver | Team | Confidence |")
            lines.append("| :-- | :----- | :--- | :--------- |")
            lines.extend(
                f"| P{p['position']} | {p['driver_name']} | {p['team']} "
                f"| {p['confidence_low']}-{p['confidence_high']}% |"
                for p in predictions[5:]
            )
            lines.append("")

        # Data sources and accuracy
        lines.append(f"**Data sources:** {', '.join(data_sources)}")
        if accuracy.get("races_evaluated", 0) > 0:
            lines.append(
                f"**Model accuracy** (last {accuracy['races_evaluated']} races): "
                f"Top-3 {accuracy.get('recent_top3_pct', 0)}%, "
                f"Top-10 {accuracy.get('recent_top10_pct', 0)}%, "
                f"Avg position error {accuracy.get('avg_position_error', 'N/A')}"
            )

        if warnings:
            lines.append(f"**Note:** {'; '.join(warnings)}")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("tool.race_predictions.error", error=str(e))
        return f"Prediction analysis failed: {e}"


# Tyre colours spelled out — the model reads these back to users who know the
# compounds by colour rather than by name.
_COMPOUND_LABELS = {
    "SOFT": "SOFT (Red)",
    "MEDIUM": "MEDIUM (Yellow)",
    "HARD": "HARD (White)",
    "INTERMEDIATE": "INTER (Green)",
    "WET": "WET (Blue)",
}


def _stint_lines(stints: list[dict]) -> list[str]:
    """Stint breakdown table, or nothing when no stint data was resolved."""
    if not stints:
        return []

    lines = [
        "#### Stint Breakdown",
        "| Stint | Compound | Laps | Length | Avg Lap | Degradation | Fresh |",
        "| :---- | :------- | :--- | :----- | :------ | :---------- | :---- |",
    ]
    for stint in stints:
        degradation = stint["degradation_sec"]
        lines.append(
            f"| {stint['stint']} | {_COMPOUND_LABELS.get(stint['compound'], stint['compound'])} | {stint['laps']} "
            f"| {stint['stint_length']} laps | {stint['avg_lap_time']} "
            f"| {'+' if degradation > 0 else ''}{degradation:.2f}s "
            f"| {'Yes' if stint.get('fresh_tyres') else 'No'} |"
        )
    lines.append("")
    return lines


def _pit_stop_lines(pit_stops: list[dict]) -> list[str]:
    """Pit stop laps, with the position held going in where it is known."""
    if not pit_stops:
        return []

    lines = [f"**Pit stops:** {len(pit_stops)} stop{'s' if len(pit_stops) != 1 else ''}"]
    for stop in pit_stops:
        position = stop.get("position_before")
        lines.append(f"  - Lap {stop['lap']}{f' (P{position})' if position else ''}")
    lines.append("")
    return lines


def _undercut_lines(attempts: list[dict]) -> list[str]:
    """Undercut/overcut attempts and whether each one worked."""
    if not attempts:
        return []

    lines = ["#### Undercut/Overcut Analysis"]
    lines.extend(
        f"  - **{attempt['type'].capitalize()}** vs {attempt['target_driver']} "
        f"(lap {attempt['lap']}): {attempt['result']}"
        for attempt in attempts
    )
    lines.append("")
    return lines


def _distribution_lines(distribution: dict[str, int]) -> list[str]:
    """How many drivers ran each strategy, for the circuit-level view."""
    if not distribution:
        return []

    lines = ["#### Strategy Distribution"]
    lines.extend(
        f"  - {strategy}: {count} driver{'s' if count != 1 else ''}" for strategy, count in distribution.items()
    )
    lines.append("")
    return lines


def _historical_lines(historical: dict) -> list[str]:
    """Previous editions of the same race, when any could be loaded."""
    if not historical or not historical.get("editions"):
        return []

    lines = [
        "#### Historical Context",
        f"**Dominant strategy:** {historical.get('dominant_strategy', 'N/A')}",
    ]
    lines.extend(
        f"  - {edition['year']}: Winner used {edition['winner_strategy']} (avg {edition['avg_stops']} stops)"
        for edition in historical["editions"]
    )
    lines.append("")
    return lines


def _safety_car_lines(result: dict) -> list[str]:
    """Safety car likelihood at this circuit."""
    probability = result.get("safety_car_probability")
    if probability is None:
        return []
    return [f"**Safety car probability:** {probability}% - {result.get('safety_car_context', '')}"]


@tool
def get_pit_strategy(year: int, round_num: int, driver_code: str | None = None) -> str:
    """
    Analyzes pit strategy including tyre stints, undercut/overcut opportunities,
    and historical strategy data.

    Use when user asks about pit strategy, tyre choices, undercut, overcut,
    or stint analysis.

    Args:
        year: Season year (e.g. 2024).
        round_num: Round number in the season.
        driver_code: Optional 3-letter driver code (e.g. 'VER'). If omitted,
                     returns circuit-level strategy overview.
    """
    logger.info("tool.pit_strategy", year=year, round_num=round_num, driver=driver_code)
    try:
        result = analyze_pit_strategy(year, round_num, driver_code)

        if result.get("error"):
            return result["error"]

        gp_name = result.get("grand_prix", f"Round {round_num}")

        if driver_code:
            lines = [f"### Pit Strategy: {driver_code} - {gp_name} {year}", ""]
            lines.extend(_stint_lines(result.get("stints", [])))
            lines.extend(_pit_stop_lines(result.get("pit_stops", [])))
            lines.extend(_undercut_lines(result.get("undercut_overcut", [])))
        else:
            lines = [f"### Strategy Overview: {gp_name} {year}", ""]
            lines.extend(_distribution_lines(result.get("strategy_distribution", {})))

        lines.extend(_historical_lines(result.get("historical_strategies", {})))
        lines.extend(_safety_car_lines(result))

        return "\n".join(lines)

    except Exception as e:
        logger.exception("tool.pit_strategy.error", error=str(e))
        return f"Strategy analysis failed: {e}"
