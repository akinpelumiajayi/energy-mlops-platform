"""UCI Appliances Energy Prediction dataset (Candanedo, Feldheim and Deramaix, 2017).

19,735 readings taken every 10 minutes for 4.5 months in a low-energy house in Stambruges,
Belgium: appliance energy use in Wh (the target), temperature and humidity in 9 rooms from
a ZigBee sensor network, and weather from Chievres airport. Downloaded from the original
author's GitHub repository.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "energydata_complete.csv"
URL = ("https://raw.githubusercontent.com/LuisM78/Appliances-energy-prediction-data/"
       "master/energydata_complete.csv")

TARGET = "Appliances"
SENSOR_COLUMNS = (
    [f"T{i}" for i in range(1, 10)] + [f"RH_{i}" for i in range(1, 10)]
    + ["T_out", "Press_mm_hg", "RH_out", "Windspeed", "Visibility", "Tdewpoint", "lights"]
)
TIME_COLUMNS = ["hour", "day_of_week", "is_weekend", "minutes_into_day"]
HISTORY_STEPS = 6  # the last hour of appliance readings, one every 10 minutes
LAG_COLUMNS = ["lag_1", "lag_2", "lag_3", "mean_last_hour", "std_last_hour", "max_last_hour"]
FEATURES = SENSOR_COLUMNS + TIME_COLUMNS + LAG_COLUMNS
# rv1 and rv2 are random noise columns the dataset authors added on purpose. We drop them.


def download(path: Path = DATA_PATH) -> Path:
    if not path.exists():
        import urllib.request

        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, path)
    return path


def load(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(download(path))
    df["date"] = pd.to_datetime(df["date"])
    for c in [TARGET, *SENSOR_COLUMNS]:
        df[c] = pd.to_numeric(df[c].astype(str).str.strip())
    df = add_time_features(df).sort_values("date").reset_index(drop=True)
    history = np.column_stack([df[TARGET].shift(k) for k in range(HISTORY_STEPS, 0, -1)])  # oldest .. newest
    df = pd.concat([df, history_features(history)], axis=1)
    return df.iloc[HISTORY_STEPS:].reset_index(drop=True)  # first hour has no history


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar features. Used for training and by the API, so both stay in step."""
    out = df.copy()
    ts = pd.to_datetime(out["date"])
    out["hour"] = ts.dt.hour
    out["day_of_week"] = ts.dt.dayofweek
    out["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)
    out["minutes_into_day"] = ts.dt.hour * 60 + ts.dt.minute
    return out


def history_features(history: np.ndarray) -> pd.DataFrame:
    """Features from the last hour of appliance readings, shape (n, 6), oldest first.
    The API builds the same features from the readings a client sends, so they match."""
    history = np.asarray(history, dtype="float64")
    return pd.DataFrame({
        "lag_1": history[:, -1], "lag_2": history[:, -2], "lag_3": history[:, -3],
        "mean_last_hour": history.mean(axis=1), "std_last_hour": history.std(axis=1),
        "max_last_hour": history.max(axis=1),
    })


def time_split(df: pd.DataFrame, test_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on the first 80% of the timeline, test on the last 20%."""
    cut = int(len(df) * (1 - test_fraction))
    return df.iloc[:cut], df.iloc[cut:]


def reference_stats(df: pd.DataFrame) -> dict:
    """Training mean and standard deviation per feature, used for live drift checks."""
    return {c: {"mean": float(df[c].mean()), "std": float(df[c].std() or 1.0)} for c in FEATURES}


__all__ = ["load", "time_split", "reference_stats", "history_features", "FEATURES", "TARGET", "HISTORY_STEPS"]
