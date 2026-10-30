# Orbit relevance ranking and citations

Orbit's federated search now applies a small, explainable reranking pass after provider results are merged and deduplicated.

## Ranking behavior

- Query terms matching titles contribute more than terms matching snippets.
- Exact query phrases in titles receive a bonus.
- A modest freshness bonus is applied when a result has a parseable `published`, `date`, or `publishedDate` field.
- Results include `relevance_score` (0–100) and `relevance_reasons` so clients can explain the ordering.
- Ties preserve the previous source order. The ranking is deterministic for the same query, result data, and reference time.
- This is a lightweight lexical ranking baseline, not a learned search model. It does not infer truth or authority from a score.

## Citation records

`POST /api/ai/answer` continues to return the model/digest answer and the legacy `sources` array. It now also returns a `citations` array with stable numeric indices, title, URL, provider, and source snippet. Duplicate URLs and non-HTTP(S) links are omitted from structured citations.

Example request:

```bash
curl -s http://127.0.0.1:18092/api/search/all?q=climate+change
```

Use the `results` from search as the `sources` array for `POST /api/ai/answer`. A citation index only points to the supplied source record; it is not independent proof that the source supports a claim. Check the linked source and snippet.

## Tests

Run the no-network suite:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover ranking order, stable ties, freshness behavior, invalid dates, citation deduplication, and integration into federated results. The `evaluate_ranking` helper computes MRR and NDCG@k against hand-labelled URL relevance grades, making it possible to compare ranking changes on a fixed offline query set. Provider live availability and search-quality improvements still require real-world measurement.
