"""
Training script for the F1 race-position predictor.

Run from the backend/ directory:
    python -m app.ml.train

Fetches historical race data (2018-2025), engineers features, trains a
GradientBoostingRegressor, and saves the model to backend/models/.
"""

import os
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error

from app.ml.features import build_dataset, FEATURE_COLUMNS

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "race_predictor.joblib")


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)

    seasons = list(range(2018, 2026))
    print(f"Building dataset for seasons {seasons[0]}-{seasons[-1]}...")
    print("(This takes ~30-40 min due to API rate-limit throttling)")
    df = build_dataset(seasons)
    print(f"Dataset: {len(df)} observations, {df['year'].nunique()} seasons")

    X = df[FEATURE_COLUMNS].values
    y = df["finish_position"].values

    # Hold out the most recent season for evaluation.
    holdout_year = seasons[-1]
    train_mask = df["year"] < holdout_year
    test_mask = df["year"] == holdout_year

    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]

    print(f"Train: {len(X_train)} rows | Test ({holdout_year}): {len(X_test)} rows")

    # Fit scaler.
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model.
    print("Training GradientBoostingRegressor...")
    model = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    # Evaluate.
    y_pred = model.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, y_pred)
    print(f"Test MAE: {mae:.2f} positions")

    # Cross-validation on full dataset.
    X_all_scaled = scaler.fit_transform(X)
    cv_scores = cross_val_score(model, X_all_scaled, y, cv=5, scoring="neg_mean_absolute_error")
    cv_mae = -np.mean(cv_scores)
    print(f"5-Fold CV MAE: {cv_mae:.2f} positions")

    # Re-fit on all data for production model.
    scaler_final = StandardScaler()
    X_final = scaler_final.fit_transform(X)
    model.fit(X_final, y)

    # Feature importance.
    importance = dict(zip(FEATURE_COLUMNS, model.feature_importances_))
    print("Feature importance:")
    for feat, imp in sorted(importance.items(), key=lambda x: -x[1]):
        print(f"  {feat}: {imp:.3f}")

    # Save.
    bundle = {
        "model": model,
        "scaler": scaler_final,
        "features": FEATURE_COLUMNS,
        "mae": round(cv_mae, 2),
        "importance": importance,
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
