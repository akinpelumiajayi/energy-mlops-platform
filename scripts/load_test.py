"""Replay real readings from the dataset against the API to generate traffic for Grafana.

    python scripts/load_test.py --url http://localhost:30080 --period test --rps 20 --seconds 120
    python scripts/load_test.py --period test --shift-temp 6     # simulate a heatwave to trip the drift alert

--period train replays January to April, --period test replays May (warmer weather, real drift).
"""
import argparse
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from energy.data import HISTORY_STEPS, SENSOR_COLUMNS, TARGET, load, time_split  # noqa: E402


def payloads(period: str, shift_temp: float):
    df = load()
    train, test = time_split(df)
    part = train if period == "train" else test
    raw = df[TARGET].to_numpy()
    for i in part.index:
        row = part.loc[i]
        reading = {c: float(row[c]) for c in SENSOR_COLUMNS}
        for c in ("T_out", *[f"T{k}" for k in range(1, 10)]):
            reading[c] += shift_temp
        reading["timestamp"] = row["date"].isoformat()
        reading["recent_appliances_wh"] = [float(v) for v in raw[i - HISTORY_STEPS:i]]
        yield reading, float(row[TARGET])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:30080")
    p.add_argument("--period", choices=["train", "test"], default="test")
    p.add_argument("--rps", type=float, default=10)
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--shift-temp", type=float, default=0.0)
    a = p.parse_args()

    rows = list(payloads(a.period, a.shift_temp))
    random.seed(0)
    end, sent, errors, abs_err = time.time() + a.seconds, 0, 0, 0.0
    while time.time() < end:
        reading, actual = random.choice(rows)
        try:
            r = requests.post(f"{a.url}/predict", json=[reading], timeout=5)
            r.raise_for_status()
            abs_err += abs(r.json()[0]["predicted_wh"] - actual)
        except requests.RequestException:
            errors += 1
        sent += 1
        time.sleep(1 / a.rps)
    ok = sent - errors
    print(f"sent {sent}, errors {errors}, live MAE {abs_err / max(ok, 1):.1f} Wh")


if __name__ == "__main__":
    main()
