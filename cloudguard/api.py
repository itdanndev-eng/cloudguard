"""Read-only IT operations API backed by explicitly synthetic demo tickets."""
import time
from flask import Flask, Response, jsonify, request
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Fictional operational scenarios; no real customers, employees, or production records.
TICKETS = (
    {"id": "SYN-101", "title": "VPN access unavailable", "priority": "P1", "status": "open", "team": "network"},
    {"id": "SYN-102", "title": "Shared printer queue stalled", "priority": "P3", "status": "open", "team": "workplace"},
    {"id": "SYN-103", "title": "Demo laptop disk capacity warning", "priority": "P2", "status": "in_progress", "team": "workplace"},
    {"id": "SYN-104", "title": "Synthetic payroll service timeout", "priority": "P1", "status": "in_progress", "team": "applications"},
    {"id": "SYN-105", "title": "Test account password reset", "priority": "P3", "status": "resolved", "team": "identity"},
    {"id": "SYN-106", "title": "Demo branch router packet loss", "priority": "P2", "status": "open", "team": "network"},
    {"id": "SYN-107", "title": "Synthetic certificate renewal", "priority": "P2", "status": "resolved", "team": "platform"},
    {"id": "SYN-108", "title": "Test monitoring agent offline", "priority": "P2", "status": "open", "team": "platform"},
)


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 65536
    registry = CollectorRegistry()
    requests = Counter("cloudguard_http_requests_total", "Completed API requests", ("method", "route", "status"), registry=registry)
    duration = Histogram("cloudguard_http_request_duration_seconds", "Application processing time",
                         ("method", "route"), buckets=(.001, .0025, .005, .01, .025, .05, .1, .25, .5, 1, 2),
                         registry=registry)

    @app.before_request
    def start_timer():
        request.started = time.perf_counter()

    @app.after_request
    def measure(response):
        if request.path != "/metrics":
            route = request.url_rule.rule if request.url_rule else "unmatched"
            method = request.method if request.method in ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH") else "OTHER"
            requests.labels(method, route, str(response.status_code)).inc()
            duration.labels(method, route).observe(time.perf_counter() - request.started)
        response.headers["X-CloudGuard-Data"] = "synthetic-demo"
        return response

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="cloudguard-servicedesk", data_source="synthetic-demo")

    @app.get("/api/tickets")
    def tickets():
        status = request.args.get("status")
        priority = request.args.get("priority")
        if status is not None and status not in ("open", "in_progress", "resolved"):
            return jsonify(error="Invalid status; choose open, in_progress, or resolved."), 400
        if priority is not None and priority not in ("P1", "P2", "P3"):
            return jsonify(error="Invalid priority; choose P1, P2, or P3."), 400
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            return jsonify(error="limit must be an integer between 1 and 100."), 400
        if not 1 <= limit <= 100:
            return jsonify(error="limit must be between 1 and 100."), 400
        rows = [dict(t) for t in TICKETS if (status is None or t["status"] == status)
                and (priority is None or t["priority"] == priority)]
        return jsonify(data_source="synthetic-demo", total=len(rows), returned=min(len(rows), limit),
                       tickets=rows[:limit], filters={"status": status, "priority": priority, "limit": limit})

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)

    return app
