"""Proactive race anomaly detection.

Scans a completed race for statistically notable stories — big movers, one-sided
teammate battles, and retirements — straight from the f1db dataset, so the
assistant can surface insight without being asked ("Piastri lost 12 places from
pole; Hulkenberg was the drive of the day").

Detection is pure data (no LLM).  An optional one-line LLM headline can be added
by the caller when an engine is configured.  Results are cached in the document
store and exposed via the intel API + the proactive background loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.f1db_source import connect

if TYPE_CHECKING:
    import sqlite3

logger = structlog.get_logger()

# Thresholds for what counts as "notable".
BIG_MOVE_POSITIONS = 5  # gained/lost this many places vs grid
LOPSIDED_TEAMMATE_GAP = 6  # finishing-position gap between teammates


def _race_id(conn: sqlite3.Connection, year: int, round_num: int) -> str | None:
    row = conn.execute("SELECT id FROM race WHERE year = ? AND round = ?", (year, round_num)).fetchone()
    return row["id"] if row else None


def _race_result_rows(conn: sqlite3.Connection, race_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT d.driver_id, dr.name AS driver, d.constructor_id AS team,
               d.position_number AS finish, d.position_text AS finish_text,
               d.race_grid_position_number AS grid,
               d.race_positions_gained AS gained,
               d.race_reason_retired AS retired
        FROM race_data d
        JOIN driver dr ON dr.id = d.driver_id
        WHERE d.race_id = ? AND d.type = 'RACE_RESULT'
        ORDER BY d.position_display_order
        """,
        (race_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _big_movers(rows: list[dict]) -> list[dict]:
    anomalies = []
    for r in rows:
        grid, finish = r.get("grid"), r.get("finish")
        if grid is None or finish is None:
            continue
        delta = int(grid) - int(finish)  # positive = gained places
        if abs(delta) >= BIG_MOVE_POSITIONS:
            anomalies.append(
                {
                    "kind": "big_gain" if delta > 0 else "big_loss",
                    "driver": r["driver"],
                    "detail": (
                        f"{r['driver']} {'gained' if delta > 0 else 'lost'} {abs(delta)} places "
                        f"(P{int(grid)} → P{int(finish)})"
                    ),
                    "magnitude": abs(delta),
                }
            )
    return anomalies


def _teammate_battles(rows: list[dict]) -> list[dict]:
    by_team: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("finish") is not None:
            by_team.setdefault(r["team"], []).append(r)
    anomalies = []
    for drivers in by_team.values():
        if len(drivers) < 2:
            continue
        drivers.sort(key=lambda r: int(r["finish"]))
        best, worst = drivers[0], drivers[-1]
        gap = int(worst["finish"]) - int(best["finish"])
        if gap >= LOPSIDED_TEAMMATE_GAP:
            anomalies.append(
                {
                    "kind": "teammate_gap",
                    "driver": best["driver"],
                    "detail": (
                        f"{best['driver']} beat teammate {worst['driver']} by {gap} places "
                        f"(P{int(best['finish'])} vs P{int(worst['finish'])})"
                    ),
                    "magnitude": gap,
                }
            )
    return anomalies


def _retirements(rows: list[dict]) -> list[dict]:
    dnfs = [r for r in rows if r.get("retired")]
    if not dnfs:
        return []
    names = ", ".join(f"{r['driver']} ({r['retired']})" for r in dnfs[:6])
    return [
        {
            "kind": "retirements",
            "driver": None,
            "detail": f"{len(dnfs)} retirement(s): {names}",
            "magnitude": len(dnfs),
        }
    ]


def detect_race_anomalies(year: int, round_num: int) -> dict:
    """Return notable anomalies for a completed race (empty when no data)."""
    try:
        with connect() as conn:
            race_id = _race_id(conn, year, round_num)
            if not race_id:
                return {"year": year, "round": round_num, "available": False, "anomalies": []}
            rows = _race_result_rows(conn, race_id)
    except Exception as exc:
        logger.warning("anomaly.detect_failed", year=year, round=round_num, error=str(exc))
        return {"year": year, "round": round_num, "available": False, "anomalies": []}

    if not rows:
        return {"year": year, "round": round_num, "available": False, "anomalies": []}

    anomalies = _big_movers(rows) + _teammate_battles(rows) + _retirements(rows)
    anomalies.sort(key=lambda a: a["magnitude"], reverse=True)
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "anomalies": anomalies,
        "headline": anomalies[0]["detail"] if anomalies else "A clean, orderly race — no major anomalies.",
    }
