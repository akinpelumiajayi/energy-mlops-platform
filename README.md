# Energy Forecast MLOps Platform: Terraform, Kubernetes, Prometheus and Grafana

A production-style platform for a machine learning model which forecasts household appliance energy use 10 minutes ahead, trained on real smart-home sensor data.

One `terraform apply` creates a Kubernetes cluster and deploys the model API with autoscaling, Prometheus monitoring, alert rules and a Grafana dashboard. Ansible prepares a fresh Ubuntu machine. GitHub Actions tests every layer, then deploys the whole stack to a throwaway cluster and checks it end to end.

![CI](https://github.com/akinpelumiajayi/energy-mlops-platform/actions/workflows/ci.yml/badge.svg)

```
                 Ansible: installs Docker, kind, kubectl, Helm, Terraform on Ubuntu
                                         │
                                         ▼
 docker build ──► local registry (localhost:5001) ◄── image pulls
                                                          │
 Terraform ──► kind cluster (1 control plane + 1 worker) ─┘
                ├── namespace energy
                │     ├── Deployment energy-api (FastAPI + model, 2 to 5 pods)
                │     ├── Service (NodePort 30080)
                │     ├── HorizontalPodAutoscaler (CPU 70%) ◄── metrics-server
                │     └── PodDisruptionBudget (min 1 available)
                └── namespace monitoring  (kube-prometheus-stack Helm chart)
                      ├── Prometheus ── scrapes /metrics every 15 s, evaluates alert rules
                      ├── Alertmanager
                      └── Grafana ── "Energy Forecast API" dashboard loaded from a ConfigMap
```

| Layer | Tools |
|---|---|
| Infrastructure as code | Terraform (kind, Helm and Kubernetes providers) |
| Host configuration | Ansible |
| Containers and orchestration | Docker (multi-stage, non-root), local container registry, Kubernetes, Helm |
| Model and API | scikit-learn, FastAPI, Pydantic |
| Monitoring and alerting | Prometheus, Alertmanager, Grafana, promtool |
| CI/CD | GitHub Actions, with a full deploy-and-test job on every push |

## The data and the model

[UCI Appliances Energy Prediction dataset](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction) (Candanedo et al., 2017): **19,735 real readings**, one every 10 minutes for 4.5 months, from a low-energy house in Belgium. Each reading has appliance energy use in Wh, temperature and humidity from 9 rooms, and local weather. It is downloaded from the original author's [GitHub repository](https://github.com/LuisM78/Appliances-energy-prediction-data).

The task: forecast appliance energy use for the next 10-minute interval from current sensor readings, the time of day and the last hour of usage.

The split is by time: train on 11 January to 30 April 2016, test on 30 April to 27 May. A random split would leak future data into training and flatter the score.

| Model (test period, May 2016) | MAE | RMSE | R² |
|---|---:|---:|---:|
| Naive: always predict the training median | 43.3 Wh | 98.0 Wh | -0.16 |
| Ridge regression | 28.5 Wh | 60.6 Wh | 0.56 |
| **Gradient boosting on log(Wh), selected** | **26.4 Wh** | **59.6 Wh** | **0.57** |

The selected model cuts the average error by 39% against the naive baseline. Without the last-hour usage features, both models barely beat the baseline (R² of 0.10 or lower), because May is much warmer than the training months. That seasonal shift is exactly what the drift monitoring below catches.

## The API

`POST /predict` takes up to 1,000 readings and returns a forecast for each. `GET /health` reports the model name and version. `GET /metrics` exposes Prometheus metrics:

| Metric | What it shows |
|---|---|
| `energy_api_requests_total{endpoint, status}` | traffic and error rate |
| `energy_api_request_seconds` (histogram) | latency percentiles |
| `energy_predicted_wh` (histogram) | spread of the forecasts |
| `energy_feature_drift_zscore{feature}` | mean of the last 500 live inputs against the training mean, in standard deviations |
| `energy_model_info{name, version}` | which model is live |

## Monitoring and alerts

[`monitoring/alert-rules.yaml`](monitoring/alert-rules.yaml) defines 3 recording rules and 5 alerts:

| Alert | Fires when | Severity |
|---|---|---|
| EnergyApiDown | no healthy pod scraped for 2 minutes | critical |
| EnergyApiHighLatency | p95 latency above 250 ms for 5 minutes | warning |
| EnergyApiHighErrorRate | over 2% of requests fail for 5 minutes | critical |
| EnergyFeatureDriftWarning | any monitored feature drifts more than 1.5 std for 10 minutes | warning |
| EnergyFeatureDriftCritical | drift above 3 std for 10 minutes: retrain | critical |

The drift thresholds come from the real data. Replaying the May test readings moves the living-room temperature (T2) 2.3 standard deviations above the training months, so the warning fires on real data. `make drift` adds 6 °C to replay a heatwave and trips the critical alert.

The rules have unit tests ([`alert-rules.test.yaml`](monitoring/alert-rules.test.yaml)) run with `promtool test rules`, covering both drift levels and the API-down alert.

The Grafana dashboard ([`energy-api.json`](monitoring/dashboards/energy-api.json)) has 10 panels: requests per second, p95 latency, error rate, ready pods, latency percentiles, request status, feature drift with warning and critical lines, forecast distribution, pod CPU and autoscaler replicas.

## Run it

You need an Ubuntu machine (or WSL2) with about 8 GB of free RAM.

```bash
git clone https://github.com/akinpelumiajayi/energy-mlops-platform.git
cd energy-mlops-platform

# 1. Install Docker, kind, kubectl, Helm and Terraform (skip if you have them)
cd ansible && ansible-playbook setup-host.yml --ask-become-pass && cd ..

# 2. Test the model and API locally
make setup && source .venv/bin/activate
make test

# 3. Build the image, push it to a local registry on localhost:5001 and deploy everything
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # set a Grafana password
make up            # about 5 minutes

# 4. Send real traffic and watch the dashboard
make load          # replays real May readings
make drift         # simulated heatwave, trips the critical drift alert after 10 minutes
```

| Service | URL |
|---|---|
| API docs | http://localhost:30080/docs |
| Grafana (admin / your password) | http://localhost:30030 |
| Prometheus alerts | http://localhost:30090/alerts |

`make down` deletes the cluster and the registry.

The image goes through a local registry, the approach the kind project recommends, instead of `kind load`. Docker 29 stores images in a format older kind releases cannot import, and a registry works with every Docker version.

## What CI checks on every push

| Job | Checks |
|---|---|
| Model and API tests | downloads the real data, trains, runs 9 pytest tests (data integrity, feature parity between training and serving, model beats baseline, API validation, metrics, drift gauge) |
| Prometheus and Grafana | `promtool check rules`, `promtool test rules`, and every dashboard query parsed by promtool |
| Ansible | syntax check and ansible-lint at the strictest `production` profile |
| Terraform | `fmt`, `init`, `validate` |
| End to end | builds the image, runs `terraform apply` to create a kind cluster and deploy everything, replays 90 seconds of real traffic, then checks Prometheus scrapes every pod, has counted the requests, and Grafana has the dashboard. Destroys the cluster afterwards. |

## Project structure

```
├── src/energy/          data loading, features, training
├── service/app.py       FastAPI service with Prometheus metrics and drift tracking
├── Dockerfile           multi-stage: trains in stage 1, runs as non-root in stage 2
├── infra/terraform/     kind cluster, kube-prometheus-stack, metrics-server, API, HPA, PDB
├── ansible/             host setup playbook
├── monitoring/          alert rules, rule unit tests, Grafana dashboard
├── scripts/             real-data load test, dashboard query check
├── tests/               pytest suite
└── .github/workflows/   CI and end-to-end deployment test
```

## Next steps

- Push the image to a registry and add a Terraform module for AKS or EKS, reusing the same Helm and Kubernetes resources.
- Route Alertmanager to email or Slack.
- Retrain automatically when the critical drift alert fires.

## Author

Akinpelumi Michael Ajayi, MSc Artificial Intelligence (Distinction), Sheffield Hallam University
[LinkedIn](https://www.linkedin.com/in/akinpelumi-michael-ajayi-) | [GitHub](https://github.com/akinpelumiajayi)

## Licence

MIT. The dataset is by Luis M. Candanedo, Véronique Feldheim and Dominique Deramaix: "Data driven prediction models of energy use of appliances in a low-energy house", Energy and Buildings, 2017.
