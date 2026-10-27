import unittest
from unittest.mock import patch

import orbit_free_apis as api


class FreeApiTests(unittest.TestCase):
    def test_catalog_is_exposed_without_network(self):
        status, payload = api.handle_api("/api/orbit/catalog", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        names = {item["name"] for item in payload["catalog"]["free_no_key_adapters"]}
        self.assertIn("GDELT news search", names)
        self.assertIn("YouTube video search", names)

    def test_missing_search_query_is_a_client_error(self):
        status, payload = api.handle_api("/api/search/web", {})
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_ai_without_sources_is_transparent(self):
        payload = api.ai_answer("What happened?", [])
        self.assertEqual(payload["mode"], "no_evidence")
        self.assertIn("No source material", payload["answer"])

    def test_suggestions_fall_back_to_wikipedia(self):
        with patch.object(api, "_ddgs", side_effect=api.AdapterError("missing optional dependency")), \
             patch.object(api, "_json", return_value=["cats", ["cat", "cats"], [], []]):
            payload = api.suggestions("cat", 5)
        self.assertEqual(payload["provider"], "Wikipedia OpenSearch")
        self.assertEqual(payload["suggestions"], ["cat", "cats"])

    def test_ai_answer_route_requires_sources_array(self):
        status, payload = api.handle_api("/api/ai/answer", {
            "q": ["What is it?"],
            "sources": ["not-json"],
        })
        self.assertEqual(status, 400)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
