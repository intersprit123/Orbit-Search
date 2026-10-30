"""Deterministic, dependency-free relevance ranking for Orbit Search results.

This is a lightweight lexical reranker, not a machine-learning model. It adds
transparent scores and reasons; upstream provider order is retained for ties.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable

_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "with",
}


def _tokens(value: Any) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(str(value or "")) if w.lower() not in _STOP_WORDS]


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        # Support common year-only metadata without guessing a month/day.
        if re.fullmatch(r"\d{4}", raw):
            try:
                return datetime(int(raw), 1, 1, tzinfo=timezone.utc)
            except ValueError:
                return None
        return None


def rank_results(
    query: str,
    results: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rank result objects using explainable token overlap, phrase, and freshness.

    Output scores are 0..100. Title matches count more than snippet matches.
    Freshness is a small bonus (up to 8 points), never enough to overwhelm a
    strong textual match. Invalid rows are ignored; ties keep original order.
    """
    query_tokens = _tokens(query)
    if not query_tokens:
        output = [dict(row) for row in results if isinstance(row, dict)]
        return output if limit is None else output[:max(0, int(limit))]
    unique_query = set(query_tokens)
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    reference_now = reference_now.astimezone(timezone.utc)

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for position, row in enumerate(results):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        snippet = str(row.get("snippet") or row.get("description") or "")
        title_tokens = set(_tokens(title))
        body_tokens = set(_tokens(snippet))
        title_hits = len(unique_query & title_tokens)
        body_hits = len(unique_query & body_tokens)
        coverage = len(unique_query & (title_tokens | body_tokens)) / len(unique_query)
        title_coverage = title_hits / len(unique_query)
        score = 68.0 * coverage + 22.0 * title_coverage
        normalized_title = " ".join(_tokens(title))
        normalized_query = " ".join(query_tokens)
        if normalized_query and normalized_query in normalized_title:
            score += 8.0
        if title_hits and body_hits:
            score += 2.0

        published = _parse_date(row.get("published") or row.get("date") or row.get("publishedDate"))
        if published:
            age_days = max(0.0, (reference_now - published).total_seconds() / 86400)
            score += 8.0 * math.exp(-age_days / 180.0)
        score = round(min(100.0, max(0.0, score)), 2)

        reasons = []
        if title_hits:
            reasons.append(f"{title_hits} query term(s) in title")
        if body_hits:
            reasons.append(f"{body_hits} query term(s) in snippet")
        if normalized_query and normalized_query in normalized_title:
            reasons.append("exact phrase in title")
        if published:
            reasons.append("freshness bonus applied")
        item = dict(row)
        item["relevance_score"] = score
        item["relevance_reasons"] = reasons or ["no query-term match"]
        ranked.append((score, position, item))

    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    output = [item for _, _, item in ranked]
    return output if limit is None else output[:max(0, int(limit))]


def evaluate_ranking(
    ranked_results: Iterable[dict[str, Any]],
    relevance_by_url: dict[str, int],
    *,
    k: int = 10,
) -> dict[str, float | int]:
    """Evaluate a ranked list against hand-labelled URL relevance grades.

    Returns MRR, NDCG@k, relevant-result count, and evaluated-result count.
    Relevance grades are non-negative integers; grade 0 means not relevant.
    This is an offline benchmark helper and does not make live-provider claims.
    """
    rows = [row for row in ranked_results if isinstance(row, dict)][:max(0, int(k))]
    grades = [
        max(0, int(relevance_by_url.get(str(row.get("url") or ""), 0)))
        for row in rows
    ]
    reciprocal_rank = 0.0
    for index, grade in enumerate(grades, start=1):
        if grade > 0:
            reciprocal_rank = 1.0 / index
            break

    def dcg(values: list[int]) -> float:
        return sum((2 ** grade - 1) / math.log2(index + 2)
                   for index, grade in enumerate(values))

    ideal_grades = sorted((max(0, int(grade)) for grade in relevance_by_url.values()), reverse=True)[:len(rows)]
    ideal_dcg = dcg(ideal_grades)
    ndcg = dcg(grades) / ideal_dcg if ideal_dcg else 0.0
    return {
        "mrr": round(reciprocal_rank, 6),
        "ndcg_at_k": round(ndcg, 6),
        "relevant_results": sum(grade > 0 for grade in grades),
        "evaluated_results": len(rows),
    }


def citation_sources(results: Iterable[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Normalize result metadata into stable numbered citation records."""
    citations = []
    if int(limit) <= 0:
        return citations
    seen: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("page_url") or "").strip()
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        citations.append({
            "index": len(citations) + 1,
            "title": str(row.get("title") or "Untitled source")[:300],
            "url": url,
            "provider": str(row.get("provider") or row.get("source") or row.get("kind") or "unknown")[:120],
            "snippet": str(row.get("snippet") or row.get("description") or "")[:1200],
        })
        if len(citations) >= max(0, int(limit)):
            break
    return citations
