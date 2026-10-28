import json
import unittest
from unittest.mock import MagicMock, patch

import orbit_resilience as resilience


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        resilience.clear_cache()

    def tearDown(self):
        resilience.clear_cache()

    @patch("orbit_resilience.urllib.request.urlopen")
    def test_successful_json_response_is_cached_and_defensively_copied(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"items": [{"title": "Example"}]}
        ).encode()
        urlopen.return_value = response

        first = resilience.fetch_json(
            "https://provider.example/api/search?q=private-query", cache_ttl=60
        )
        first["items"][0]["title"] = "mutated by caller"
        second = resilience.fetch_json(
            "https://provider.example/api/search?q=private-query", cache_ttl=60
        )

        self.assertEqual(second["items"][0]["title"], "Example")
        urlopen.assert_called_once()
        self.assertEqual(resilience.metrics_snapshot()["providers"]["provider.example"]["cache_hits"], 1)

    @patch("orbit_resilience.urllib.request.urlopen")
    def test_oversized_payload_is_rejected_and_counted_as_failure(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"payload":"too big"}'
        urlopen.return_value = response

        with self.assertRaises(ValueError):
            resilience.fetch_json(
                "https://large.example/data?token=must-not-leak",
                max_bytes=4,
                cache_ttl=0,
            )

        snapshot = resilience.metrics_snapshot()
        self.assertEqual(snapshot["providers"]["large.example"]["failures"], 1)
        self.assertNotIn("must-not-leak", json.dumps(snapshot))
        self.assertNotIn("/data", json.dumps(snapshot))

    @patch("orbit_resilience.urllib.request.urlopen", side_effect=OSError("network down"))
    def test_provider_failure_is_counted_without_exposing_query(self, urlopen):
        with self.assertRaises(OSError):
            resilience.fetch_json(
                "https://offline.example/search?q=private-person",
                cache_ttl=0,
            )

        snapshot = resilience.metrics_snapshot()
        provider = snapshot["providers"]["offline.example"]
        self.assertEqual(provider["status"], "degraded")
        self.assertEqual(provider["last_error"], "OSError")
        self.assertNotIn("private-person", json.dumps(snapshot))
        self.assertNotIn("/search", json.dumps(snapshot))


if __name__ == "__main__":
    unittest.main()
