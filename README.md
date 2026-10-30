# Orbit-Search

A self-hosted search project with a local crawler, SQLite/FTS5 index, browser UI, federated search, and a large collection of public-data REST endpoints.

## Orbit ecosystem API hub

Orbit includes a local API gateway for no-key public data, including federated search, scholarly metadata, developer platforms, package registries, knowledge APIs, archives, science datasets, media catalogues, education, food products, public economic data, DNS and domain registration lookups. Existing weather, currency, places, countries, and market adapters remain available; this expansion does not add weather routes. External video search is intentionally not enabled.

See [ORBIT_ECOSYSTEM.md](ORBIT_ECOSYSTEM.md) for setup, provider caveats, and endpoint details. The existing market service remains separate; see [ORBIT_MARKET.md](ORBIT_MARKET.md). See [ORBIT_RANKING.md](ORBIT_RANKING.md) for relevance scoring and structured citations.

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


## Expanded API endpoint families

The expanded API adapters are implemented in orbit_extra_apis.py. The live route inventory is returned by:

    curl -s http://127.0.0.1:18092/api/orbit/routes
    curl -s http://127.0.0.1:18092/api/orbit/catalog

The inventory currently documents more than 65 additional endpoint families. Use the exact route and required query parameters shown in each catalog entry. Orbit also includes a bounded in-memory TTL cache and privacy-conscious, host-level provider metrics.

### Scholarly research and health datasets
- GET /api/scholarly/openalex/works?q=...
- GET /api/scholarly/openalex/authors?q=...
- GET /api/scholarly/openalex/sources?q=...
- GET /api/scholarly/openalex/institutions?q=...
- GET /api/scholarly/openalex/topics?q=...
- GET /api/scholarly/openalex/publishers?q=...
- GET /api/scholarly/openalex/work?id=W...
- GET /api/scholarly/crossref/works?q=...
- GET /api/scholarly/crossref/journals?q=...
- GET /api/scholarly/crossref/funders?q=...
- GET /api/scholarly/crossref/members?q=...
- GET /api/scholarly/crossref/doi?doi=10....
- GET /api/scholarly/europepmc?q=...
- GET /api/scholarly/europepmc/article?id=...
- GET /api/health/clinicaltrials?q=...
- GET /api/health/clinicaltrials/study?nct=NCT01234567
- GET /api/health/openfda?dataset=drug-label&q=...
- GET /api/health/openfda/datasets

### Developer, AI, and packages
- GET /api/developer/github/repos?q=...
- GET /api/developer/github/repo?name=owner/repo
- GET /api/developer/github/releases?repo=owner/repo
- GET /api/developer/github/commits?repo=owner/repo
- GET /api/developer/github/issues?repo=owner/repo&state=open
- GET /api/developer/github/contributors?repo=owner/repo
- GET /api/developer/github/languages?repo=owner/repo
- GET /api/developer/github/user?username=...
- GET /api/developer/github/user-repos?username=...
- GET /api/developer/gitlab/projects?q=...
- GET /api/developer/gitlab/project?path=group/project
- GET /api/developer/gitlab/releases?path=group/project
- GET /api/developer/stackoverflow/search?q=...&site=stackoverflow
- GET /api/ai/huggingface/models?q=...
- GET /api/ai/huggingface/datasets?q=...
- GET /api/ai/huggingface/spaces?q=...
- GET /api/ai/huggingface/model?id=org/name
- GET /api/ai/huggingface/dataset?id=org/name
- GET /api/ai/huggingface/space?id=org/name
- GET /api/packages/search?q=...
- GET /api/packages/npm/search?q=...
- GET /api/packages/npm/package?name=...
- GET /api/packages/pypi/project?name=...
- GET /api/packages/pypi/release?name=...&version=...
- GET /api/packages/crates/search?q=...
- GET /api/packages/crates/package?name=...
- GET /api/packages/maven/search?q=...
- GET /api/packages/rubygems/search?q=...
- GET /api/packages/rubygems/gem?name=...
- GET /api/packages/nuget/search?q=...

### Knowledge, archives, and public collections
- GET /api/books/openlibrary/search?q=...
- GET /api/books/openlibrary/authors?q=...
- GET /api/books/openlibrary/isbn?isbn=978...
- GET /api/books/openlibrary/author?id=OL...A
- GET /api/books/openlibrary/work?id=OL...W
- GET /api/books/openlibrary/editions?work=OL...W
- GET /api/books/openlibrary/subjects?q=...
- GET /api/knowledge/opensearch?q=...
- GET /api/knowledge/summary?title=...
- GET /api/knowledge/page?title=...
- GET /api/knowledge/random
- GET /api/knowledge/categories?title=...
- GET /api/knowledge/wikidata/search?q=...
- GET /api/knowledge/wikidata/entity?id=Q42
- GET /api/archives/search?q=...
- GET /api/archives/metadata?id=...
- GET /api/archives/wayback?url=https%3A%2F%2Fexample.com
- GET /api/open-data/library-of-congress/search?q=...

### Science, space, media, games, and food
- GET /api/science/earthquakes?period=day&min_magnitude=2.5
- GET /api/science/species?q=...
- GET /api/science/occurrences?taxon_key=...
- GET /api/science/space/news?q=...
- GET /api/science/space/launches
- GET /api/media/itunes/search?term=...&entity=song
- GET /api/media/itunes/lookup?id=...
- GET /api/media/musicbrainz/search?q=...&type=artist
- GET /api/entertainment/tv/search?q=...
- GET /api/entertainment/tv/show?id=...
- GET /api/entertainment/tv/episodes?id=...
- GET /api/games/pokemon/search?q=...
- GET /api/games/pokemon/details?name=pikachu
- GET /api/games/pokemon/ability?name=static
- GET /api/games/pokemon/type?name=electric
- GET /api/games/pokemon/item?name=poke-ball
- GET /api/food/search?q=...
- GET /api/food/product?barcode=...

### Education, economy, and network metadata
- GET /api/education/trivia?amount=10&difficulty=medium
- GET /api/education/dictionary?word=...
- GET /api/education/synonyms?word=...
- GET /api/education/antonyms?word=...
- GET /api/economy/worldbank/countries?q=...
- GET /api/economy/worldbank/indicator?country=IND&indicator=NY.GDP.MKTP.CD&date=2020:2025
- GET /api/economy/worldbank/indicators?q=...
- GET /api/network/dns?name=example.com&type=A
- GET /api/network/domain?name=example.com
- GET /api/network/certificates?domain=example.com

### Local reliability and diagnostics

- `GET /api/orbit/health` — confirms the local hub is responding and reports cache configuration. It does not actively probe upstream providers.
- `GET /api/orbit/metrics` — shows per-host request counts, cache hits, failures, average network latency, last success/error timestamps, and a coarse status.
- Public JSON responses use a bounded in-memory cache by default (30 seconds, maximum 512 entries). Cache entries are process-local and disappear on restart.
- `ORBIT_API_CACHE_TTL=0` disables caching; values from 0 to 300 seconds are accepted. `ORBIT_API_CACHE_MAX_ENTRIES` can be set from 16 to 2048.
- Metrics never include full request URLs, paths, query strings, or search terms. “Unknown” means Orbit has not contacted that host during the current process lifetime; it is not a failed health check.

Example:

    curl -s http://127.0.0.1:18092/api/orbit/health
    curl -s http://127.0.0.1:18092/api/orbit/metrics

### Examples

Search packages across registries:

    curl --get 'http://127.0.0.1:18092/api/packages/search' --data-urlencode 'q=web framework'

Search research papers:

    curl --get 'http://127.0.0.1:18092/api/scholarly/openalex/works' --data-urlencode 'q=operating system'

Search public GitHub repositories:

    curl --get 'http://127.0.0.1:18092/api/developer/github/repos' --data-urlencode 'q=toy operating system'

Look up DNS records:

    curl 'http://127.0.0.1:18092/api/network/dns?name=example.com&type=A'

List recent earthquakes:

    curl 'http://127.0.0.1:18092/api/science/earthquakes?period=day&min_magnitude=2.5'

Provider limitations are real: GitHub's anonymous REST API has rate limits, Crossref/Open Library and other public services have usage policies, and APIs can change or temporarily fail. Federated search calls up to five selected providers concurrently, keeps the provider order stable, preserves each provider's ranking, reports per-provider latency, and returns partial results when some providers fail. The aggregate package endpoint also reports partial provider status. Health endpoints return public records only and are not medical advice. Public metadata does not guarantee rights to redistribute full text, images, datasets, or media. The hub should remain on localhost unless authentication, per-client rate limiting, request logging, and a security review are added.

Helpful official documentation: [OpenAlex API](https://help.openalex.org/api/), [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [Open Library API](https://openlibrary.org/developers/api), [PyPI JSON API](https://docs.pypi.org/api/json/), and [ICANN RDAP](https://www.icann.org/rdap/).
