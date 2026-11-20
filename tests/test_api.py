import unittest
from cloudguard.api import create_app


class ServiceDeskTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_health_has_identity_and_synthetic_label(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["service"], "cloudguard-servicedesk")
        self.assertEqual(response.json["data_source"], "synthetic-demo")

    def test_filtered_tickets_are_meaningful_and_read_only(self):
        response = self.client.get("/api/tickets?status=open&priority=P1&limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 1)
        self.assertEqual(response.json["tickets"][0]["id"], "SYN-101")
        self.assertEqual(self.client.post("/api/tickets", json={}).status_code, 405)

    def test_query_validation(self):
        for query in ("status=unknown", "priority=P9", "limit=0", "limit=101", "limit=oops"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/tickets?" + query).status_code, 400)

    def test_pagination_does_not_mutate_data(self):
        self.client.get("/api/tickets?limit=1")
        self.assertEqual(self.client.get("/api/tickets").json["total"], 8)

    def test_metrics_count_normalized_routes_and_latency(self):
        self.client.get("/api/tickets?status=open")
        self.client.get("/api/tickets?priority=P1")
        self.client.get("/missing-untrusted-path")
        body = self.client.get("/metrics").text
        self.assertIn('route="/api/tickets",status="200"} 2.0', body)
        self.assertIn("cloudguard_http_request_duration_seconds_bucket", body)
        self.assertNotIn("missing-untrusted-path", body)
        self.assertNotIn("priority=P1", body)


if __name__ == "__main__":
    unittest.main()
