import threading
import unittest
from cloudguard.recovery import CONTAINER, EXPECTED, LABELS, Controller, create_app


def alert(status="firing", **labels):
    return {"status": status, "startsAt": "2030-01-01T00:00:00Z", "labels": {**EXPECTED, **labels}}


class FakeDocker:
    def __init__(self):
        self.running = False
        self.starts = 0
        self.labels = dict(LABELS)

    def inspect(self):
        return {"Name": "/" + CONTAINER, "Config": {"Labels": self.labels},
                "State": {"Running": self.running, "Status": "running" if self.running else "exited"}}

    def start(self):
        self.starts += 1
        self.running = True


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.docker = FakeDocker()
        self.events = []
        self.controller = Controller(self.docker, health=lambda: self.docker.running,
                                     emit=lambda **e: self.events.append(e), health_timeout=.02, retry_interval=.001)
        self.token = "unit-test-placeholder-not-a-real-credential"
        self.client = create_app(self.controller, self.token).test_client()

    def post(self, alerts, auth=True):
        return self.client.post("/alerts", json={"alerts": alerts},
                                headers={"Authorization": "Bearer " + self.token} if auth else {})

    def test_authentication_required(self):
        self.assertEqual(self.post([alert()], auth=False).status_code, 401)
        self.assertEqual(self.docker.starts, 0)

    def test_resolved_and_unknown_targets_never_start(self):
        for entry in (alert(status="resolved"), alert(container="unrelated"), alert(service="other"),
                      alert(instance="http://attacker/health"), alert(alertname="OtherAlert"), None):
            with self.subTest(entry=entry):
                self.assertEqual(self.controller.recover(entry)["outcome"], "ignored")
        self.assertEqual(self.docker.starts, 0)

    def test_stopped_allowlisted_workload_is_started_and_http_verified(self):
        result = self.post([alert()])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["results"][0]["outcome"], "success")
        self.assertEqual(self.docker.starts, 1)
        self.assertEqual([e["event"] for e in self.events],
                         ["alert_received", "remediation_start", "remediation_finish"])
        self.assertTrue(self.events[-1]["http_health_verified"])

    def test_repeated_alert_is_idempotent(self):
        self.post([alert()])
        self.assertEqual(self.post([alert()]).json["results"][0]["outcome"], "already_healthy")
        self.assertEqual(self.docker.starts, 1)

    def test_container_labels_are_verified_independently_of_alert(self):
        self.docker.labels["com.docker.compose.project"] = "someone-else"
        self.assertEqual(self.controller.recover(alert())["outcome"], "rejected")
        self.assertEqual(self.docker.starts, 0)

    def test_running_unhealthy_container_is_not_restarted(self):
        self.docker.running = True
        self.controller.health = lambda: False
        self.assertEqual(self.post([alert()]).status_code, 503)
        self.assertEqual(self.docker.starts, 0)

    def test_health_verification_failure_is_reported_as_failed(self):
        self.controller.health = lambda: False
        self.assertEqual(self.post([alert()]).json["results"][0]["outcome"], "failed")
        self.assertEqual(self.events[-1]["outcome"], "failed")

    def test_overlapping_requests_cannot_start_twice(self):
        entered, release = threading.Event(), threading.Event()
        def blocked_health():
            entered.set()
            release.wait(2)
            return True
        self.controller.health = blocked_health
        result = []
        worker = threading.Thread(target=lambda: result.append(self.controller.recover(alert())))
        worker.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(self.controller.recover(alert())["outcome"], "in_progress")
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.docker.starts, 1)
        self.assertEqual(result[0]["outcome"], "success")

    def test_invalid_batches_are_rejected(self):
        for payload in ({}, {"alerts": "wrong"}, {"alerts": [alert()] * 11}):
            self.assertEqual(self.client.post("/alerts", json=payload,
                headers={"Authorization": "Bearer " + self.token}).status_code, 400)

    def test_no_restart_route_and_health_is_read_only(self):
        self.assertEqual(self.client.post("/restart").status_code, 404)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.docker.starts, 0)


if __name__ == "__main__":
    unittest.main()
