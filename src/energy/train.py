"""Train and evaluate the appliance energy model.

    python -m energy.train          # writes model/model.joblib and model/metrics.json

Two models are compared on a time-based split, against a naive baseline which always
predicts the training median:
  - Ridge regression on standardised features
  - HistGradientBoostingRegressor on log(1 + Wh), since energy use is heavily right-skewed
The better model on the test period is saved together with the training feature
statistics the API uses for drift detection.
"""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from energy.data import FEATURES, ROOT, TARGET, load, reference_stats, time_split

MODEL_DIR = ROOT / "model"
MODEL_PATH = MODEL_DIR / "model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"
MODEL_VERSION = "1.0.0"


def evaluate(y_true, y_pred) -> dict:
    return {
        "rmse_wh": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
        "mae_wh": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def candidates() -> dict:
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "gradient_boosting": TransformedTargetRegressor(
            regressor=HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                                    l2_regularization=1.0, random_state=42),
            func=np.log1p, inverse_func=np.expm1),
    }


def main() -> dict:
    df = load()
    train, test = time_split(df)
    X_tr, y_tr, X_te, y_te = train[FEATURES], train[TARGET], test[FEATURES], test[TARGET]

    results = {"naive_median": evaluate(y_te, np.full(len(y_te), y_tr.median()))}
    fitted = {}
    for name, model in candidates().items():
        model.fit(X_tr, y_tr)
        fitted[name] = model
        results[name] = evaluate(y_te, model.predict(X_te))
        print(f"{name:18s} {results[name]}")

    best = min(fitted, key=lambda n: results[n]["mae_wh"])
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({
        "model": fitted[best],
        "name": best,
        "version": MODEL_VERSION,
        "features": FEATURES,
        "reference": reference_stats(train),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, MODEL_PATH)

    summary = {
        "selected_model": best,
        "version": MODEL_VERSION,
        "train_rows": len(train), "test_rows": len(test),
        "train_period": [str(train["date"].min()), str(train["date"].max())],
        "test_period": [str(test["date"].min()), str(test["date"].max())],
        "test_metrics": results,
    }
    METRICS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"Selected {best}: {results[best]}")
    return summary


if __name__ == "__main__":
    main()
