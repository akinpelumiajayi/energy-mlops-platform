"""End-to-end checks against a running deployment. Used by CI after terraform apply.

    python scripts/smoke_check.py --grafana-password <password>

Checks, retrying for up to --timeout seconds while Prometheus completes its first scrapes:
  1. Prometheus scrapes every energy-api pod (up == 1)
  2. Prometheus has counted the replayed requests
  3. the energy-api alert rules are loaded
  4. Grafana has the "Energy Forecast API" dashboard
"""
import argparse
import sys
import time

import requests


def prom(url: str, query: str) -> list:
    r = requests.get(f"{url}/api/v1/query", params={"query": query}, timeout=10)  # params are URL-encoded
    r.raise_for_status()
    return r.json()["data"]["result"]


def check_targets_up(a) -> str:
    result = prom(a.prometheus, 'up{job="energy-api"}')
    assert result, "no energy-api targets found"
    down = [r["metric"].get("pod") for r in result if r["value"][1] != "1"]
    assert not down, f"targets down: {down}"
    return f"{len(result)} energy-api pods scraped, all up"


def check_requests_counted(a) -> str:
    result = prom(a.prometheus, 'sum(energy_api_requests_total{endpoint="/predict"})')
    assert result, "no request metrics yet"
    total = float(result[0]["value"][1])
    assert total >= a.min_requests, f"only {total:.0f} requests counted"
    return f"{total:.0f} forecast requests counted"


def check_rules_loaded(a) -> str:
    r = requests.get(f"{a.prometheus}/api/v1/rules", timeout=10)
    r.raise_for_status()
    names = {rule["name"] for g in r.json()["data"]["groups"] for rule in g["rules"]}
    wanted = {"EnergyApiDown", "EnergyFeatureDriftWarning", "EnergyFeatureDriftCritical"}
    missing = wanted - names
    assert not missing, f"alert rules missing: {missing}"
    return f"{len(wanted)} key alert rules loaded"


def check_dashboard(a) -> str:
    r = requests.get(f"{a.grafana}/api/search", params={"query": "Energy Forecast API"},
                     auth=("admin", a.grafana_password), timeout=10)
    r.raise_for_status()
    assert r.json(), "dashboard not found"
    return f"Grafana dashboard found: {r.json()[0]['title']}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prometheus", default="http://localhost:30090")
    p.add_argument("--grafana", default="http://localhost:30030")
    p.add_argument("--grafana-password", required=True)
    p.add_argument("--min-requests", type=int, default=100)
    p.add_argument("--timeout", type=int, default=180)
    a = p.parse_args()

    failed = False
    for check in (check_targets_up, check_requests_counted, check_rules_loaded, check_dashboard):
        deadline, last_error = time.time() + a.timeout, None
        while time.time() < deadline:
            try:
                print(f"PASS {check.__name__}: {check(a)}")
                break
            except (AssertionError, requests.RequestException, KeyError, IndexError) as e:
                last_error = e
                time.sleep(10)
        else:
            print(f"FAIL {check.__name__}: {last_error}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
