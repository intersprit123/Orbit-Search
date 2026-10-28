import unittest
from unittest.mock import patch

import orbit_extra_apis as extra
import orbit_free_apis as free


class ExtraPublicApiTests(unittest.TestCase):
    def test_catalog_lists_many_real_provider_families(self):
        self.assertGreaterEqual(len(extra.EXTRA_CATALOG), 50)
        routes = "\n".join(item["route"] for item in extra.EXTRA_CATALOG)
        self.assertIn("/api/scholarly/openalex", routes)
        self.assertIn("/api/developer/github", routes)
        self.assertIn("/api/network/dns", routes)

    def test_openalex_results_are_normalized(self):
        with patch.object(extra, "_json", return_value={
            "meta": {"count": 1},
            "results": [{
                "id": "https://openalex.org/W123",
                "display_name": "Example paper",
                "publication_year": 2025,
                "cited_by_count": 4,
                "doi": "https://doi.org/10.1000/example",
            }],
        }):
            status, payload = extra.handle_extra_api(
                "/api/scholarly/openalex/works", {"q": ["example"], "limit": ["5"]}
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["title"], "Example paper")
        self.assertEqual(payload["count"], 1)

    def test_dictionary_extracts_synonyms_and_antonyms(self):
        sample = [{
            "word": "bright",
            "phonetics": [],
            "meanings": [{
                "partOfSpeech": "adjective",
                "synonyms": ["radiant"],
                "antonyms": ["dim"],
                "definitions": [{"definition": "Giving out much light.", "synonyms": ["shining"], "antonyms": []}],
            }],
        }]
        with patch.object(extra, "_json", return_value=sample):
            status, payload = extra.handle_extra_api(
                "/api/education/synonyms", {"word": ["bright"]}
            )
        self.assertEqual(status, 200)
        self.assertIn("radiant", payload["synonyms"])
        self.assertIn("shining", payload["synonyms"])

    def test_dns_rejects_localhost_without_network(self):
        with patch.object(extra, "_json") as fetch:
            status, payload = extra.handle_extra_api("/api/network/dns", {"name": ["localhost"]})
        self.assertEqual(status, 400)
        self.assertIn("domain name", payload["error"])
        fetch.assert_not_called()

    def test_invalid_github_repo_is_rejected_without_network(self):
        with patch.object(extra, "_json") as fetch:
            status, payload = extra.handle_extra_api("/api/developer/github/repo", {"name": ["bad/path/extra"]})
        self.assertEqual(status, 400)
        self.assertIn("owner/repository", payload["error"])
        fetch.assert_not_called()

    def test_trivia_decodes_html_entities(self):
        with patch.object(extra, "_json", return_value={
            "response_code": 0,
            "results": [{
                "category": "Science &amp; Nature", "type": "multiple",
                "difficulty": "easy", "question": "Which is 2 &lt; 3?",
                "correct_answer": "Yes &amp; no", "incorrect_answers": ["No"],
            }],
        }):
            status, payload = extra.handle_extra_api("/api/education/trivia", {"amount": ["1"]})
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["question"], "Which is 2 < 3?")
        self.assertEqual(payload["results"][0]["correct_answer"], "Yes & no")

    def test_package_search_preserves_partial_results(self):
        with patch.object(extra, "_npm_search", return_value=[
            {"title": "demo-package", "url": "https://www.npmjs.com/package/demo-package", "source": "npm"}
        ]), patch.object(extra, "_crates_search", side_effect=RuntimeError("rate limited")), \
             patch.object(extra, "_maven_search", return_value=[]), \
             patch.object(extra, "_rubygems_search", return_value=[]):
            status, payload = extra.handle_extra_api("/api/packages/search", {"q": ["demo"]})
        self.assertEqual(status, 200)
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["count"], 1)

    def test_unknown_route_does_not_claim_it_is_implemented(self):
        self.assertIsNone(extra.handle_extra_api("/api/made-up/route", {}))

    def test_catalog_is_exposed_via_main_orbit_catalog(self):
        status, payload = free.handle_api("/api/orbit/catalog", {})
        self.assertEqual(status, 200)
        self.assertIn("additional_public_apis", payload["catalog"])
        self.assertGreaterEqual(len(payload["catalog"]["additional_public_apis"]), 50)

    def test_routes_endpoint_returns_expanded_catalog(self):
        status, payload = free.handle_api("/api/orbit/routes", {})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(payload["expanded_route_families"], 50)


if __name__ == "__main__":
    unittest.main()
