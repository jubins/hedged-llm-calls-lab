"""Check that the compose file, Prometheus config and Grafana dashboard parse."""
import json
import pathlib

import yaml

root = pathlib.Path(__file__).resolve().parent.parent
for name in ("docker-compose.yml", "observability/prometheus.yml",
             "observability/grafana/provisioning/datasources/prometheus.yml",
             "observability/grafana/provisioning/dashboards/dashboards.yml"):
    yaml.safe_load((root / name).read_text())
dash = json.loads((root / "observability/grafana/dashboards/hedging.json").read_text())
assert dash["panels"], "dashboard has no panels"
print("configs ok")
