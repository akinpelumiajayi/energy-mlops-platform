"""Check every PromQL query in the Grafana dashboard parses, using promtool.

    python scripts/check_dashboard_queries.py path/to/promtool
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

dash = json.loads((Path(__file__).resolve().parents[1] / "monitoring/dashboards/energy-api.json").read_text())
exprs = [t["expr"] for p in dash["panels"] for t in p.get("targets", [])]
rules = {"groups": [{"name": "dashboard", "rules": [{"record": f"dashboard:query_{i}", "expr": e}
                                                     for i, e in enumerate(exprs)]}]}
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
    yaml.safe_dump(rules, f)
result = subprocess.run([sys.argv[1] if len(sys.argv) > 1 else "promtool", "check", "rules", f.name])
print(f"{len(exprs)} dashboard queries checked")
sys.exit(result.returncode)
