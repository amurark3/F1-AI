"""
Inference module for the F1 race-position predictor.

Loads the trained model and predicts finishing order for a given Grand Prix.
Returns Markdown-formatted results for display in chat.
"""

import os
import joblib

from app.ml.features import compute_features_for_prediction, FEATURE_COLUMNS

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "race_predictor.joblib")

_model_cache = None


def _load_model():
    global _model_cache
    if _model_cache is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                "Race predictor model not found. Run `python -m app.ml.train` first."
            )
        _model_cache = joblib.load(MODEL_PATH)
    return _model_cache


def _explain_prediction(row: dict, importance: dict) -> str:
    """Picks the most influential factor for a specific driver's predicted position."""
    factors = []
    if importance.get("grid_position", 0) > 0.1:
        factors.append(("Grid P" + str(int(row["grid_position"])), importance["grid_position"]))
    if importance.get("recent_form", 0) > 0.05:
        factors.append((f"Recent avg P{row['recent_form']:.1f}", importance["recent_form"]))
    if importance.get("constructor_strength", 0) > 0.05:
        factors.append((f"Team rank #{int(row['constructor_strength'])}", importance["constructor_strength"]))
    if importance.get("track_history", 0) > 0.05:
        factors.append((f"Track avg P{row['track_history']:.1f}", importance["track_history"]))
    if importance.get("driver_championship_pos", 0) > 0.05:
        factors.append((f"WDC P{int(row['driver_championship_pos'])}", importance["driver_championship_pos"]))

    if not factors:
        return "Multiple factors"
    factors.sort(key=lambda x: -x[1])
    return factors[0][0]


def predict_race(year: int, grand_prix: str) -> str:
    """
    Predicts the finishing order for all drivers at a given Grand Prix.
    Returns a Markdown table.
    """
    bundle = _load_model()
    model = bundle["model"]
    scaler = bundle["scaler"]
    features = bundle["features"]
    importance = bundle.get("importance", {})
    mae = bundle.get("mae", "N/A")

    df = compute_features_for_prediction(year, grand_prix)

    X = scaler.transform(df[features].values)
    df["predicted_position"] = model.predict(X)
    df = df.sort_values("predicted_position").reset_index(drop=True)

    lines = [f"### Predicted Race Results: {grand_prix} {year}\n"]
    lines.append("| Pos | Driver | Key Factor |")
    lines.append("| :-- | :----- | :--------- |")

    for i, (_, row) in enumerate(df.iterrows(), 1):
        factor = _explain_prediction(row.to_dict(), importance)
        lines.append(f"| P{i} | {row['driver_name']} | {factor} |")

    lines.append(
        f"\n*Model accuracy: ~{mae} positions MAE. "
        f"Based on qualifying, form, constructor strength, and track history.*"
    )
    return "\n".join(lines)
