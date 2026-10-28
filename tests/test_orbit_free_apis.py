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


    def test_federated_search_merges_and_deduplicates(self):
        with patch.object(api, "web_search", return_value={"provider": "web", "results": [
            {"title": "A", "url": "https://example.com/a", "snippet": "web", "kind": "web"}
        ]}), patch.object(api, "news_search", return_value={"provider": "news", "results": [
            {"title": "A duplicate", "url": "https://example.com/a/", "snippet": "news", "kind": "news"},
            {"title": "B", "url": "https://news.example/b", "snippet": "news", "kind": "news"}
        ]}):
            status, payload = api.handle_api("/api/search/all", {
                "q": ["orbit search"], "limit": ["10"], "sources": ["web,news"]
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["providers"]), 2)
        self.assertFalse(payload["partial"])


    def test_federated_search_preserves_provider_ranking_and_reports_latency(self):
        with patch.object(api, "web_search", return_value={"provider": "web", "results": [
            {"title": "Z highly relevant", "url": "https://example.com/z"},
            {"title": "A less relevant", "url": "https://example.com/a"},
        ]}), patch.object(api, "news_search", return_value={"provider": "news", "results": [
            {"title": "News item", "url": "https://news.example/story"},
        ]}):
            payload = api.federated_search("orbit", 10, "web,news")
        self.assertEqual(
            [row["title"] for row in payload["results"]],
            ["Z highly relevant", "A less relevant", "News item"],
        )
        self.assertGreaterEqual(payload["latency_ms"], 0)
        self.assertTrue(all("latency_ms" in provider for provider in payload["providers"]))

    def test_federated_search_rejects_unknown_provider(self):
        status, payload = api.handle_api("/api/search/all", {
            "q": ["orbit"], "sources": ["brave"]
        })
        self.assertEqual(status, 400)
        self.assertIn("Unsupported sources", payload["error"])

    def test_federated_search_reports_partial_provider_failure(self):
        with patch.object(api, "web_search", side_effect=api.AdapterError("not available")), \
             patch.object(api, "news_search", return_value={"provider": "news", "results": [
                 {"title": "News", "url": "https://news.example/story", "kind": "news"}
             ]}):
            status, payload = api.handle_api("/api/search/all", {
                "q": ["orbit"], "sources": ["web,news"]
            })
        self.assertEqual(status, 200)
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["count"], 1)

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
