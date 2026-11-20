"""Internal authenticated webhook with an exact container allowlist and start-only Docker access."""
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import socket
import threading
import time
from urllib.request import urlopen
from flask import Flask, jsonify, request

CONTAINER = "cloudguard-servicedesk"
HEALTH_URL = "http://servicedesk:8000/health"
EXPECTED = {"alertname": "ServiceDeskUnavailable", "job": "servicedesk-http",
            "service": "servicedesk", "container": CONTAINER, "instance": HEALTH_URL}
LABELS = {"com.docker.compose.project": "cloudguard-original",
          "com.docker.compose.service": "servicedesk", "io.cloudguard.recovery": "allowlisted-demo"}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=5)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class DockerClient:
    """Only inspect and start are implemented. No payload-controlled paths or target names."""
    def __init__(self, socket_path="/var/run/docker.sock"):
        self.socket_path = socket_path

    def _request(self, method, suffix):
        conn = UnixConnection(self.socket_path)
        try:
            conn.request(method, "/v1.44/containers/" + CONTAINER + suffix, body=b"")
            response = conn.getresponse()
            body = response.read()
            if response.status not in (200, 204, 304):
                raise RuntimeError("Docker API returned HTTP " + str(response.status))
            return json.loads(body) if body else {}
        finally:
            conn.close()

    def inspect(self):
        return self._request("GET", "/json")

    def start(self):
        return self._request("POST", "/start")


def healthy():
    try:
        with urlopen(HEALTH_URL, timeout=2) as response:
            payload = json.load(response)
            return response.status == 200 and payload.get("status") == "ok" and payload.get("service") == CONTAINER
    except (OSError, ValueError):
        return False


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def __call__(self, **event):
        line = json.dumps({"at_utc": utc(), **event}, separators=(",", ":"))
        with self.lock:
            with self.path.open("a") as handle:
                handle.write(line + "\n")
                handle.flush()
            print(line, flush=True)


class Controller:
    def __init__(self, docker, health=healthy, emit=None, health_timeout=15, retry_interval=.25):
        self.docker, self.health = docker, health
        self.emit = emit or (lambda **event: None)
        self.health_timeout, self.retry_interval = health_timeout, retry_interval
        self.lock = threading.Lock()

    def recover(self, alert):
        if not isinstance(alert, dict):
            return {"outcome": "ignored", "reason": "invalid_alert"}
        if alert.get("status") != "firing":
            self.emit(event="ignored_alert", reason="not_firing")
            return {"outcome": "ignored", "reason": "not_firing"}
        labels = alert.get("labels", {})
        if not isinstance(labels, dict) or any(labels.get(k) != v for k, v in EXPECTED.items()):
            self.emit(event="ignored_alert", reason="unknown_target")
            return {"outcome": "ignored", "reason": "unknown_target"}
        incident = hashlib.sha256((str(alert.get("startsAt", "")) + HEALTH_URL).encode()).hexdigest()[:20]
        self.emit(event="alert_received", incident=incident, container=CONTAINER)
        if not self.lock.acquire(blocking=False):
            self.emit(event="overlap_prevented", incident=incident)
            return {"outcome": "in_progress"}
        started = None
        try:
            info = self.docker.inspect()
            actual = info.get("Config", {}).get("Labels", {})
            if info.get("Name") != "/" + CONTAINER or any(actual.get(k) != v for k, v in LABELS.items()):
                self.emit(event="recovery_rejected", incident=incident, reason="container_identity_mismatch")
                return {"outcome": "rejected", "reason": "container_identity_mismatch"}
            state = info.get("State", {})
            if state.get("Running"):
                result = "already_healthy" if self.health() else "running_unhealthy"
                self.emit(event="recovery_skipped", incident=incident, reason=result)
                return {"outcome": result}
            if state.get("Status") not in ("exited", "created") or state.get("Paused"):
                return {"outcome": "rejected", "reason": "unsupported_container_state"}
            started = time.monotonic()
            self.emit(event="remediation_start", incident=incident, container=CONTAINER, action="start")
            self.docker.start()
            deadline = time.monotonic() + self.health_timeout
            while time.monotonic() < deadline:
                if self.health():
                    elapsed = round(time.monotonic() - started, 6)
                    self.emit(event="remediation_finish", incident=incident, container=CONTAINER,
                              outcome="success", duration_seconds=elapsed, http_health_verified=True)
                    return {"outcome": "success", "duration_seconds": elapsed}
                time.sleep(self.retry_interval)
            raise RuntimeError("HTTP health verification timed out")
        except Exception as exc:
            elapsed = round(time.monotonic() - started, 6) if started is not None else None
            self.emit(event="remediation_finish", incident=incident, container=CONTAINER,
                      outcome="failed", duration_seconds=elapsed, error=str(exc)[:300])
            return {"outcome": "failed"}
        finally:
            self.lock.release()


def create_app(controller=None, token=None):
    if token is None:
        token = Path(os.environ.get("RECOVERY_TOKEN_FILE", "/run/secrets/recovery_token")).read_text().strip()
    if len(token) < 32:
        raise RuntimeError("A recovery token of at least 32 characters is required.")
    if controller is None:
        controller = Controller(DockerClient(), emit=Journal("/var/lib/cloudguard/events.jsonl"))
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 65536

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="cloudguard-recovery")

    @app.post("/alerts")
    def alerts():
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, "Bearer " + token):
            return jsonify(error="unauthorized"), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list) or len(payload["alerts"]) > 10:
            return jsonify(error="invalid_alert_batch"), 400
        results = [controller.recover(alert) for alert in payload["alerts"]]
        failed = any(r["outcome"] in ("failed", "running_unhealthy") for r in results)
        return jsonify(results=results), 503 if failed else 200

    return app
