import unittest
from unittest.mock import patch
from scripts.lab import percentile, probe_availability, window


class MeasurementTests(unittest.TestCase):
    def test_nearest_rank_percentiles(self):
        self.assertEqual(percentile(list(range(1, 101)), .95), 95)
        self.assertEqual(percentile(list(range(1, 101)), .99), 99)
        self.assertEqual(percentile([7], .99), 7)

    def test_availability_uses_successful_probe_proportion(self):
        result = probe_availability([[1, "1"], [2, "0"], [3, "1"], [4, "1"]])
        self.assertEqual(result["successful_probes"], 3)
        self.assertEqual(result["total_observed_probes"], 4)
        self.assertEqual(result["availability_percent"], 75)

    def test_no_probes_does_not_mean_full_availability(self):
        self.assertIsNone(probe_availability([])["availability_percent"])

    @patch("scripts.lab.query")
    def test_raw_window_preserves_sample_timestamps(self, query):
        query.return_value = {"data": {"result": [{"values": [[9.9, "1"], [10.2, "0"], [12.7, "1"], [14, "1"]]}]}}
        _, points = window("probe_success", 10, 13)
        self.assertEqual(points, [[10.2, "0"], [12.7, "1"]])

    @patch("scripts.lab.query")
    def test_missing_series_rejects_availability_calculation(self, query):
        query.return_value = {"data": {"result": []}}
        with self.assertRaises(RuntimeError):
            window("probe_success", 10, 13)
