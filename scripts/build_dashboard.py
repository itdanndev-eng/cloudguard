#!/usr/bin/env python3
"""Generate the provisioned CloudGuard dashboard."""
import json
from pathlib import Path

source = {"type": "prometheus", "uid": "cloudguard-prometheus"}
panels = []


def panel(title, kind, x, y, w, h, expressions, unit="short"):
    item = {"id": len(panels) + 1, "title": title, "type": kind,
            "datasource": source, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
            "targets": [{"refId": chr(65 + i), "expr": expr, "legendFormat": label,
                         "datasource": source} for i, (label, expr) in enumerate(expressions)]}
    if kind == "stat":
        item["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value"}
    else:
        item["options"] = {"legend": {"displayMode": "list", "placement": "bottom"}}
    panels.append(item)
    return item


probe = 'probe_success{job="servicedesk-http"}'
health = panel("Independent HTTP health", "stat", 0, 0, 8, 5, [("health", probe)])
health["fieldConfig"]["defaults"].update({
    "mappings": [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"},
                                               "1": {"text": "UP", "color": "green"}}}]})
panel("Successful probes / total probes (15m)", "stat", 8, 0, 8, 5,
      [("availability", f"100 * sum_over_time({probe}[15m]) / count_over_time({probe}[15m])")], "percent")
rate = 'sum(rate(cloudguard_http_requests_total{route="/api/tickets",status=~"2.."}[1m]))'
panel("Successful ticket requests / second", "stat", 16, 0, 8, 5, [("requests/s", rate)], "reqps")
latencies = [(f"p{int(q*100)}", 'histogram_quantile(' + str(q) +
              ', sum by (le) (rate(cloudguard_http_request_duration_seconds_bucket{route="/api/tickets"}[1m])))')
             for q in (.95, .99)]
panel("Ticket endpoint processing latency (histogram estimates)", "timeseries", 0, 5, 12, 8, latencies, "s")
panel("Ticket endpoint request rate by HTTP status", "timeseries", 12, 5, 12, 8,
      [("{{status}}", 'sum by (status) (rate(cloudguard_http_requests_total{route="/api/tickets"}[1m]))')], "reqps")
timeline = panel("Independent HTTP probe history (0 = failed, 1 = successful)", "timeseries", 0, 13, 24, 8,
                 [("HTTP availability", probe)])
timeline["fieldConfig"]["defaults"].update({"min": 0, "max": 1,
    "custom": {"drawStyle": "line", "lineInterpolation": "stepAfter", "spanNulls": False}})
dashboard = {"id": None, "uid": "cloudguard-service-desk", "title": "CloudGuard Service Desk Reliability",
             "schemaVersion": 39, "version": 1, "timezone": "utc", "refresh": "5s",
             "tags": ["cloudguard", "synthetic-demo", "local-validation"],
             "time": {"from": "now-15m", "to": "now"}, "panels": panels,
             "annotations": {"list": []}}
path = Path(__file__).resolve().parents[1] / "config/grafana/dashboards/servicedesk.json"
path.write_text(json.dumps(dashboard, indent=2) + "\n")
print(path.relative_to(path.parents[3]))
