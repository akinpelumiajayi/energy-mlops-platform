"""FastAPI service: forecasts the next 10 minutes of appliance energy use.

Exposes Prometheus metrics at /metrics. The URL label is called "path", not "endpoint",
because Prometheus Operator sets its own "endpoint" label on every scraped series.
  - energy_api_requests_total{path, status}       traffic and errors
  - energy_api_request_seconds{path}             latency histogram (p50, p95, p99)
  - energy_predicted_wh                               distribution of forecasts
  - energy_feature_drift_zscore{feature}              live input mean vs training mean, in std units
  - energy_model_info{name, version}                  which model is serving

Run locally:  PYTHONPATH=src uvicorn service.app:app --port 8000
"""
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from energy.data import HISTORY_STEPS, SENSOR_COLUMNS, add_time_features, history_features

MODEL_PATH = Path(os.getenv("MODEL_PATH", Path(__file__).resolve().parents[1] / "model" / "model.joblib"))
DRIFT_WINDOW = int(os.getenv("DRIFT_WINDOW", "500"))     # recent requests used for drift
DRIFT_FEATURES = ["T_out", "RH_out", "T2", "RH_1", "Tdewpoint", "mean_last_hour"]

REQUESTS = Counter("energy_api_requests_total", "API requests", ["path", "status"])
LATENCY = Histogram("energy_api_request_seconds", "Request latency", ["path"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
PREDICTED = Histogram("energy_predicted_wh", "Forecast appliance energy (Wh)",
                      buckets=(25, 50, 75, 100, 150, 200, 300, 500, 800))
DRIFT = Gauge("energy_feature_drift_zscore", "Live feature mean vs training mean (std units)", ["feature"])
MODEL_INFO = Gauge("energy_model_info", "Serving model", ["name", "version"])

bundle = joblib.load(MODEL_PATH)
MODEL_INFO.labels(bundle["name"], bundle["version"]).set(1)
recent = {f: deque(maxlen=DRIFT_WINDOW) for f in DRIFT_FEATURES}

app = FastAPI(title="Appliance Energy Forecast API", version=bundle["version"])


class Reading(BaseModel):
    """Sensor readings at one 10-minute timestamp, plus the previous hour of appliance use."""
    timestamp: datetime
    recent_appliances_wh: list[float] = Field(..., min_length=HISTORY_STEPS, max_length=HISTORY_STEPS,
                                              description="Last 6 readings (Wh), oldest first")
    T1: float; RH_1: float; T2: float; RH_2: float; T3: float; RH_3: float  # noqa: E702
    T4: float; RH_4: float; T5: float; RH_5: float; T6: float; RH_6: float  # noqa: E702
    T7: float; RH_7: float; T8: float; RH_8: float; T9: float; RH_9: float  # noqa: E702
    T_out: float; Press_mm_hg: float; RH_out: float; Windspeed: float  # noqa: E702
    Visibility: float; Tdewpoint: float; lights: float = 0.0  # noqa: E702


class Forecast(BaseModel):
    timestamp: datetime
    predicted_wh: float


def to_features(readings: list[Reading]) -> pd.DataFrame:
    raw = pd.DataFrame([{"date": r.timestamp, **{c: getattr(r, c) for c in SENSOR_COLUMNS}} for r in readings])
    hist = history_features(np.array([r.recent_appliances_wh for r in readings]))
    return pd.concat([add_time_features(raw), hist], axis=1)[bundle["features"]]


def update_drift(X: pd.DataFrame) -> None:
    ref = bundle["reference"]
    for f in DRIFT_FEATURES:
        recent[f].extend(X[f].tolist())
        DRIFT.labels(f).set((np.mean(recent[f]) - ref[f]["mean"]) / ref[f]["std"])


@app.middleware("http")
async def track(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    try:
        response = await call_next(request)
    except Exception:
        REQUESTS.labels(path, "500").inc()
        raise
    if path != "/metrics":
        LATENCY.labels(path).observe(time.perf_counter() - start)
        REQUESTS.labels(path, str(response.status_code)).inc()
    return response


@app.post("/predict", response_model=list[Forecast])
def predict(readings: list[Reading]) -> list[Forecast]:
    if not readings or len(readings) > 1000:
        raise HTTPException(422, "Send between 1 and 1000 readings")
    X = to_features(readings)
    preds = np.clip(bundle["model"].predict(X), 0, None)
    for p in preds:
        PREDICTED.observe(p)
    update_drift(X)
    return [Forecast(timestamp=r.timestamp, predicted_wh=round(float(p), 1)) for r, p in zip(readings, preds)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": bundle["name"], "version": bundle["version"]}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
