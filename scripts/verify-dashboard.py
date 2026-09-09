"""Check dashboard metric references against actual collector snapshots."""
import json
import re
from pathlib import Path

from prometheus_client.parser import text_string_to_metric_families
from app.metrics import PlatformMetrics

ROOT = Path(__file__).resolve().parents[1]
dashboard = json.loads((ROOT / "monitoring/grafana-dashboard.json").read_text())
assert len(dashboard["panels"]) == 14
sources = [PlatformMetrics().render().decode(), (ROOT / "artifacts/litellm/metrics.prom").read_text(), (ROOT / "artifacts/metrics/controller.prom").read_text()]
available = {sample.name for text in sources for family in text_string_to_metric_families(text) for sample in family.samples}
referenced = set()
for panel in dashboard["panels"]:
    assert panel["datasource"]["uid"] == "cloud-prometheus"
    for target in panel["targets"]:
        referenced.update(re.findall(r'\b(?:cloud_|sandbox_|litellm_)[a-z_]+', target["expr"]))
missing = referenced - available
assert not missing, sorted(missing)
report = {"result": "passed", "panels": len(dashboard["panels"]), "verified_metric_names": sorted(referenced), "scope": "Static dashboard and actual metric-name validation; visual Grafana rendering is optional and not tested."}
destination = ROOT / "artifacts/metrics/dashboard-report.json"
destination.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
