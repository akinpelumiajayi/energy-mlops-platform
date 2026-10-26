from fastapi.testclient import TestClient

from service.app import app

client = TestClient(app)

READING = {
    "timestamp": "2016-05-10T18:30:00",
    "recent_appliances_wh": [50, 60, 60, 90, 120, 110],
    "T1": 21.5, "RH_1": 40.1, "T2": 20.3, "RH_2": 38.0, "T3": 22.4, "RH_3": 38.5,
    "T4": 21.0, "RH_4": 37.9, "T5": 19.8, "RH_5": 48.0, "T6": 12.4, "RH_6": 30.2,
    "T7": 20.6, "RH_7": 33.5, "T8": 22.1, "RH_8": 41.0, "T9": 20.0, "RH_9": 40.3,
    "T_out": 14.2, "Press_mm_hg": 757.0, "RH_out": 70.0, "Windspeed": 3.5,
    "Visibility": 40.0, "Tdewpoint": 8.8, "lights": 0,
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_predict_returns_positive_forecast():
    r = client.post("/predict", json=[READING, READING])
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2 and body[0]["predicted_wh"] >= 0


def test_rejects_wrong_history_length():
    bad = {**READING, "recent_appliances_wh": [50, 60]}
    assert client.post("/predict", json=[bad]).status_code == 422


def test_metrics_exposed_for_prometheus():
    client.post("/predict", json=[READING])
    text = client.get("/metrics").text
    assert 'energy_api_requests_total{path="/predict",status="200"}' in text
    assert "energy_api_request_seconds_bucket" in text
    assert 'energy_feature_drift_zscore{feature="T_out"}' in text
    assert "energy_model_info{" in text


def test_drift_gauge_rises_for_heatwave_inputs():
    hot = {**READING, "T_out": 35.0}
    for _ in range(50):
        client.post("/predict", json=[hot])
    line = next(l for l in client.get("/metrics").text.splitlines()
                if l.startswith('energy_feature_drift_zscore{feature="T_out"}'))
    assert float(line.split()[-1]) > 1.5
