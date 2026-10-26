import json

import numpy as np

from energy.data import FEATURES, HISTORY_STEPS, TARGET, history_features, load, time_split
from energy.train import METRICS_PATH


def test_dataset_is_real_and_complete():
    df = load()
    assert len(df) == 19735 - HISTORY_STEPS
    assert df[FEATURES + [TARGET]].isna().sum().sum() == 0
    assert df["date"].is_monotonic_increasing


def test_time_split_has_no_overlap():
    train, test = time_split(load())
    assert train["date"].max() < test["date"].min()


def test_history_features_match_training_rows():
    """Features built by the API from raw readings must equal the training features."""
    df = load()
    raw = df[TARGET].to_numpy()
    i = 500
    window = raw[i - HISTORY_STEPS:i][None, :]  # the 6 readings before row i, oldest first
    feats = history_features(window)
    for c in ["lag_1", "lag_2", "lag_3", "mean_last_hour", "max_last_hour"]:
        assert np.isclose(feats.loc[0, c], df.loc[i, c]), c


def test_model_beats_naive_baseline():
    m = json.loads(METRICS_PATH.read_text())
    best = m["test_metrics"][m["selected_model"]]
    naive = m["test_metrics"]["naive_median"]
    assert best["mae_wh"] < 0.8 * naive["mae_wh"]
    assert best["r2"] > 0.4
