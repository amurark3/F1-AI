"""Fitted retirement (DNF) and crash risk.

Replaces hand-tuned weights with logistic coefficients fitted on f1db history
(2018 onward) and gated by a season-forward backtest: the fit for season Y only
sees seasons before Y. Features are point-in-time: incident counts from earlier
rounds, the grid slot and the constructor standing before the round.

Usage (prints the walk-forward table and the coefficients to ship)::

    cd backend
    python -m app.ml.risk_model
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.data.predictions.incidents import _classify_status
from app.ml.risk_predict import LogisticFit, risk_features

FIRST_TRAIN_YEAR = 2018
FIRST_TEST_YEAR = 2021

DEFAULT_GRID = 20
DEFAULT_TEAM_POS = 10

_RAW_SQL = """
SELECT r.year, r.round, d.abbreviation AS code, rd.constructor_id AS team,
       rd.race_grid_position_number AS grid, rd.race_reason_retired AS reason,
       COALESCE(rd.race_points, 0) AS points
FROM race_data rd
JOIN race r ON r.id = rd.race_id
JOIN driver d ON d.id = rd.driver_id
WHERE rd.type = 'RACE_RESULT' AND d.abbreviation IS NOT NULL AND r.year >= ?
ORDER BY r.year, r.round
"""


def _team_ranks(points: dict[str, float]) -> dict[str, int]:
    ordered = sorted(points, key=lambda team: -points[team])
    return {team: place for place, team in enumerate(ordered, start=1)}


def _flags(reason: str | None) -> dict[str, bool]:
    if not reason:
        return {"dnf": False, "crash": False, "mechanical": False}
    return _classify_status(reason)


def build_rows(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per driver-race from race results sorted by (year, round).

    Everything on a row is known before that race: the driver's counts come from
    earlier rounds of the season plus the whole prior season, and the constructor
    rank from points before the round (last season's final order in round 1).
    """
    counts: dict[tuple[str, int], list[int]] = {}
    team_points: dict[int, dict[str, float]] = {}
    by_round: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for result in raw:
        by_round.setdefault((result["year"], result["round"]), []).append(result)

    rows: list[dict[str, Any]] = []
    for year, round_num in sorted(by_round):
        season_points = team_points.setdefault(year, {})
        ranks = _team_ranks(season_points or team_points.get(year - 1, {}))
        for result in by_round[(year, round_num)]:
            now = counts.get((result["code"], year), [0, 0, 0, 0])
            before = counts.get((result["code"], year - 1), [0, 0, 0, 0])
            starts, dnfs, crashes, mech = (a + b for a, b in zip(now, before, strict=True))
            flags = _flags(result["reason"])
            rows.append(
                {
                    "year": year,
                    "round": round_num,
                    "code": result["code"],
                    "starts": starts,
                    "dnfs": dnfs,
                    "crashes": crashes,
                    "mechanical": mech,
                    "team_pos": ranks.get(result["team"], DEFAULT_TEAM_POS),
                    "grid": int(result["grid"] or DEFAULT_GRID),
                    "dnf": flags["dnf"],
                    "crash": flags["crash"],
                    "other": flags["dnf"] and not flags["crash"],
                }
            )
        for result in by_round[(year, round_num)]:
            tally = counts.setdefault((result["code"], year), [0, 0, 0, 0])
            flags = _flags(result["reason"])
            tally[0] += 1
            tally[1] += flags["dnf"]
            tally[2] += flags["crash"]
            tally[3] += flags["mechanical"]
            season_points[result["team"]] = season_points.get(result["team"], 0.0) + result["points"]
    return rows


def load_rows() -> list[dict[str, Any]]:
    """Dataset rows for every race since ``FIRST_TRAIN_YEAR`` (the year before feeds history)."""
    from app.data.f1db_source import connect

    with connect() as conn:
        raw = [dict(row) for row in conn.execute(_RAW_SQL, (FIRST_TRAIN_YEAR - 1,)).fetchall()]
    return [row for row in build_rows(raw) if row["year"] >= FIRST_TRAIN_YEAR]


def row_features(row: dict[str, Any]) -> list[float]:
    return risk_features(row, row["grid"], row["team_pos"])


def legacy_risks(row: dict[str, Any]) -> dict[str, float]:
    """The retired hand-tuned formula, kept only as the baseline the fit must beat."""
    starts = row["starts"]
    dnf_rate = row["dnfs"] / starts if starts else 0.08
    crash_rate = row["crashes"] / starts if starts else 0.03
    mech_rate = row["mechanical"] / starts if starts else 0.04
    grid = row["grid"]
    traffic = 4 if 8 <= grid <= 16 else 2 if grid <= 4 else 1
    dnf = 6 + dnf_rate * 31 + mech_rate * 18 + max(0, row["team_pos"] - 5) * 1.1 + traffic
    crash = 3 + crash_rate * 26 + traffic * 1.2 + (2 if 10 <= grid <= 18 else 0)
    dnf, crash = max(3, min(42, round(dnf))), max(1, min(30, round(crash)))
    return {"dnf": dnf / 100, "crash": crash / 100, "other": max(2, min(35, round(dnf - crash * 0.45))) / 100}


def fit_logistic(rows: list[dict[str, Any]], label: str) -> LogisticFit:
    from sklearn.linear_model import LogisticRegression

    x = np.array([row_features(row) for row in rows])
    y = np.array([bool(row[label]) for row in rows])
    means, scales = x.mean(axis=0), x.std(axis=0)
    scales = np.where(scales == 0, 1.0, scales)
    model = LogisticRegression(C=1.0).fit((x - means) / scales, y)
    return LogisticFit(
        means=tuple(float(v) for v in means),
        scales=tuple(float(v) for v in scales),
        weights=tuple(float(v) for v in model.coef_[0]),
        bias=float(model.intercept_[0]),
    )


def best_threshold(probs: list[float], truth: list[bool]) -> float:
    """The probability cut that maximises F1 on the given rows."""
    p, t = np.array(probs), np.array(truth)
    best, best_f1 = 0.0, -1.0
    for cut in np.unique(p):
        called = p >= cut
        tp = float((called & t).sum())
        f1 = 2 * tp / (called.sum() + t.sum())
        if f1 > best_f1:
            best, best_f1 = float(cut), f1
    return best


def _metrics(probs: list[float], truth: list[bool], cut: float) -> dict[str, float]:
    from sklearn.metrics import brier_score_loss, roc_auc_score

    p, t = np.array(probs), np.array(truth)
    called = p >= cut
    tp = float((called & t).sum())
    return {
        "auc": float(roc_auc_score(t, p)),
        "brier": float(brier_score_loss(t, p)),
        "precision": tp / called.sum() if called.sum() else 0.0,
        "recall": tp / t.sum(),
        "flagged": int(called.sum()),
        "threshold": cut,
    }


def backtest(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, float]]:
    """Season-forward comparison of the fit and the legacy formula on held-out seasons.

    Each held-out year is predicted by a fit (and a threshold) from earlier years
    only; the reported threshold is the mean of the per-year ones.
    """
    scorers = {"fitted": None, "legacy": lambda r: legacy_risks(r)[label]}
    pooled: dict[str, tuple[list[float], list[bool]]] = {name: ([], []) for name in scorers}
    cuts: dict[str, list[float]] = {name: [] for name in scorers}
    for year in sorted({r["year"] for r in rows if r["year"] >= FIRST_TEST_YEAR}):
        train = [r for r in rows if r["year"] < year]
        test = [r for r in rows if r["year"] == year]
        fit = fit_logistic(train, label)
        scorers["fitted"] = lambda r, fit=fit: fit.predict(row_features(r))
        truth = [bool(r[label]) for r in train]
        for name, score in scorers.items():
            cuts[name].append(best_threshold([score(r) for r in train], truth))
            pooled[name][0].extend(score(r) for r in test)
            pooled[name][1].extend(bool(r[label]) for r in test)
    return {name: _metrics(*pooled[name], float(np.mean(cuts[name]))) for name in pooled}


def main() -> None:
    rows = load_rows()
    for label in ("dnf", "crash", "other"):
        print(label, backtest(rows, label))
        fit = fit_logistic(rows, label)
        probs = [fit.predict(row_features(r)) for r in rows]
        print("  ship", fit, "threshold", best_threshold(probs, [bool(r[label]) for r in rows]))


if __name__ == "__main__":
    main()
