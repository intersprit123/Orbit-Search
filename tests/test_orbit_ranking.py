import unittest
from datetime import datetime, timezone

from orbit_ranking import citation_sources, evaluate_ranking, rank_results


class OrbitRankingTests(unittest.TestCase):
    def test_relevance_prefers_title_match_over_unrelated_result(self):
        rows = [
            {"title": "Gardening tips", "snippet": "How to grow plants", "url": "https://example.org/garden"},
            {"title": "Orbit Search relevance ranking", "snippet": "Search engine query ranking", "url": "https://example.org/orbit"},
        ]
        ranked = rank_results("Orbit Search", rows)
        self.assertEqual(ranked[0]["title"], "Orbit Search relevance ranking")
        self.assertIn("relevance_score", ranked[0])
        self.assertTrue(ranked[0]["relevance_reasons"])

    def test_freshness_is_a_small_bonus(self):
        now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        rows = [
            {"title": "climate report", "snippet": "climate data", "published": "2020-01-01"},
            {"title": "climate report", "snippet": "climate data", "published": "2026-10-29"},
        ]
        ranked = rank_results("climate report", rows, now=now)
        self.assertGreater(ranked[0]["relevance_score"], ranked[1]["relevance_score"])
        self.assertEqual(ranked[0]["published"], "2026-10-29")

    def test_ties_keep_original_order(self):
        rows = [{"title": "python search", "id": 1}, {"title": "python search", "id": 2}]
        self.assertEqual([r["id"] for r in rank_results("python", rows)], [1, 2])

    def test_empty_query_returns_original_order_and_limit(self):
        rows = [{"title": "one"}, {"title": "two"}]
        self.assertEqual(rank_results("   ", rows, limit=1), rows[:1])

    def test_invalid_dates_do_not_crash(self):
        ranked = rank_results("space", [{"title": "space science", "published": "not-a-date"}])
        self.assertEqual(len(ranked), 1)

    def test_offline_benchmark_reports_mrr_and_ndcg(self):
        rows = [
            {"url": "https://example.org/good"},
            {"url": "https://example.org/bad"},
            {"url": "https://example.org/also-good"},
        ]
        metrics = evaluate_ranking(rows, {
            "https://example.org/good": 3,
            "https://example.org/bad": 0,
            "https://example.org/also-good": 1,
        }, k=3)
        self.assertEqual(metrics["mrr"], 1.0)
        self.assertGreater(metrics["ndcg_at_k"], 0.9)
        self.assertEqual(metrics["evaluated_results"], 3)
        self.assertEqual(metrics["relevant_results"], 2)

    def test_citations_are_valid_deduplicated_and_numbered(self):
        rows = [
            {"title": "First", "url": "https://example.org/a", "source": "A", "snippet": "Evidence"},
            {"title": "Duplicate", "url": "https://example.org/a"},
            {"title": "Bad", "url": "javascript:alert(1)"},
            {"title": "Second", "url": "http://example.org/b"},
        ]
        citations = citation_sources(rows)
        self.assertEqual([x["index"] for x in citations], [1, 2])
        self.assertEqual(citations[0]["provider"], "A")
        self.assertEqual(citations[1]["url"], "http://example.org/b")


if (name := __name__) == "__main__":
    unittest.main()
