# Orbit-Search

A self-hosted web search project with a local crawler, SQLite/FTS5 index, browser UI, and REST endpoints.

## Orbit ecosystem API hub

Orbit includes a local API gateway for no-key public data: RSS news, place lookup, weather, currency conversion, encyclopedia search, Wikimedia Commons media, country data, and the local market adapter. The built-in Web tab uses the existing local crawler. External video search is intentionally not enabled.

See [ORBIT_ECOSYSTEM.md](ORBIT_ECOSYSTEM.md) for setup, provider caveats, and endpoint details. The existing market service remains separate; see [ORBIT_MARKET.md](ORBIT_MARKET.md).

Quick start on Kali/Linux:

```bash
git pull
python3 -m pip install -r requirements-market.txt
python3 orbit_market.py init
python3 orbit_market.py collect-news
python3 orbit_market.py serve --port 8090
```

Then open `http://127.0.0.1:8090/api/market/status`.

**Market-data note:** The current price adapter uses unofficial `yfinance` data for prototype/testing only. Quotes may be delayed or incomplete. Use a properly licensed NSE/BSE feed before treating prices as live or redistributing them. The news collector stores headlines, summaries and links from RSS sources and remains subject to publisher terms.


## Free provider integrations

Install the optional no-key adapters into the same Python environment:

```bash
python3 -m pip install -r requirements-free.txt
```

The hub adds these routes:
- `GET /api/search/all?q=...&sources=web,news,research,books` — federated search across selected providers, with partial-failure reporting and URL deduplication. Supported sources: `web`, `images`, `news`, `research`, `books`.
- `GET /api/search/related?q=...` — related-search suggestions.
- `GET /api/search/web?q=...` — web search through the optional DDGS community client.
- `GET /api/search/images?q=...` — image search; verify each original image's licence before reuse.
- `GET /api/search/suggest?q=...` — suggestions, with Wikipedia OpenSearch fallback if DDGS is absent.
- `GET /api/search/news?q=...` — GDELT news search.
- `GET /api/search/research?q=...` — arXiv paper metadata.
- `GET /api/search/books?q=...` — public Google Books metadata (quota applies).
- `POST /api/ai/answer` — grounded answer from supplied result snippets; uses local Ollama if running, otherwise returns a clearly labelled source digest.
- `GET /api/orbit/catalog` — reports enabled adapters, buildable UI features, and providers that still need verification or credentials.

Example AI request:

```bash
curl -X POST http://127.0.0.1:18092/api/ai/answer \\
  -H 'Content-Type: application/json' \\
  -d '{"question":"What do these sources say?","sources":[{"title":"Example","url":"https://example.com","snippet":"Example source text","source":"web"}]}'
```

Existing no-key endpoints remain available for weather, currency reference rates, Wikipedia, Wikimedia Commons, country data, place lookup, and the local Orbit Market adapter. Free does not mean unlimited: respect rate limits, attribution, licensing, and provider terms. Some search adapters depend on upstream websites and may temporarily fail or change their behaviour. Do not expose the unauthenticated local prototype to the public internet.

## Start the API Hub

Start the market service on the port that works on your machine (example: 8092):

```bash
python3 orbit_market.py serve --port 8092
```

In a second terminal, start the hub:

```bash
python3 orbit_api_hub.py --port 18092
```

Check `http://127.0.0.1:18092/api/orbit/status`. Set `ORBIT_MARKET_URL` if your market service uses a different port. No API keys or developer-account signups are required for the hub's enabled public-data routes. See [ORBIT_ECOSYSTEM.md](ORBIT_ECOSYSTEM.md) for provider policies and limitations. Do not expose this unauthenticated prototype to the public internet.
