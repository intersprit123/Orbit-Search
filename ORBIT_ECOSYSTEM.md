# Orbit Ecosystem — public API setup

Orbit Search combines a local crawler and local services with optional public-data APIs. Most expanded providers do not require keys for basic interactive use. A public endpoint can still be rate-limited, unavailable, or subject to attribution/licensing rules.

## Start the services

Terminal 1 — Orbit Market (required only for market data and its RSS index):

    python3 orbit_market.py serve --port 8092

Terminal 2 — API Hub:

    python3 orbit_api_hub.py --port 18092

Optional provider package for the original web and image adapters:

    python3 -m pip install -r requirements-free.txt

Check status and discover the full route catalog:

    curl -s http://127.0.0.1:18092/api/orbit/status
    curl -s http://127.0.0.1:18092/api/orbit/health
    curl -s http://127.0.0.1:18092/api/orbit/metrics
    curl -s http://127.0.0.1:18092/api/orbit/routes
    curl -s http://127.0.0.1:18092/api/orbit/catalog

The route inventory is generated from the code catalog and is the most up-to-date list of expanded routes. The current expansion contains more than 65 additional endpoint families. It adds no new weather routes.

## Reliability and diagnostics

Orbit's JSON provider adapters share a bounded in-memory TTL cache (default 30 seconds, 512 entries maximum). This reduces repeated upstream calls and helps avoid unnecessary pressure on public providers. Cache only contains successful responses; provider errors are not cached.

- Set `ORBIT_API_CACHE_TTL=0` to disable cache, or a value up to 300 seconds.
- Set `ORBIT_API_CACHE_MAX_ENTRIES` to a value from 16 to 2048.
- `GET /api/orbit/health` reports local process health and cache settings; it does not claim every upstream is online.
- `GET /api/orbit/metrics` reports host-level request totals, cache hits, failures, average network latency, and last success/error timestamps.
- Metrics deliberately omit URLs, request paths, query strings, and search terms. Provider status is passive: unknown means no request has been made to that host since process startup.

## Expanded public API families

### Scholarly data and biomedical records
- /api/scholarly/openalex/works, authors, sources, institutions, topics, publishers, work
- /api/scholarly/crossref/works, journals, funders, members, doi
- /api/scholarly/europepmc and /api/scholarly/europepmc/article
- /api/health/clinicaltrials and /api/health/clinicaltrials/study
- /api/health/openfda and /api/health/openfda/datasets

### Developer tools, AI metadata and package registries
- /api/developer/github/repos, repo, releases, commits, issues, contributors, languages, user, user-repos
- /api/developer/gitlab/projects, project, releases
- /api/developer/stackoverflow/search
- /api/ai/huggingface/models, datasets, spaces, model, dataset, space
- /api/packages/search
- /api/packages/npm/search, package
- /api/packages/pypi/project, release
- /api/packages/crates/search, package
- /api/packages/maven/search
- /api/packages/rubygems/search, gem
- /api/packages/nuget/search

### Knowledge, books and archives
- /api/books/openlibrary/search, authors, isbn, author, work, editions, subjects
- /api/knowledge/summary, page, random, categories, opensearch
- /api/knowledge/wikidata/search, entity
- /api/archives/search, metadata, wayback
- /api/open-data/library-of-congress/search
- Existing /api/search/books and /api/images/commons remain available.

### Science, media, entertainment and games
- /api/science/earthquakes
- /api/science/species and /api/science/occurrences
- /api/science/space/news and /api/science/space/launches
- /api/media/itunes/search, lookup
- /api/media/musicbrainz/search
- /api/entertainment/tv/search, show, episodes
- /api/games/pokemon/search, details, ability, type, item
- /api/food/search and /api/food/product

### Education, economy and network lookup
- /api/education/trivia, dictionary, synonyms, antonyms
- /api/economy/worldbank/countries, indicator, indicators
- /api/network/dns, domain, certificates

## Request examples

Search software packages across multiple registries:

    curl --get 'http://127.0.0.1:18092/api/packages/search' --data-urlencode 'q=web framework'

Search public repository metadata:

    curl --get 'http://127.0.0.1:18092/api/developer/github/repos' --data-urlencode 'q=toy operating system'

Search research records:

    curl --get 'http://127.0.0.1:18092/api/scholarly/openalex/works' --data-urlencode 'q=operating system'

Get a dictionary entry:

    curl 'http://127.0.0.1:18092/api/education/dictionary?word=curious'

Resolve DNS:

    curl 'http://127.0.0.1:18092/api/network/dns?name=example.com&type=A'

Get recent earthquake events:

    curl 'http://127.0.0.1:18092/api/science/earthquakes?period=day&min_magnitude=2.5'

## Original no-key endpoints

| Endpoint | Purpose | Provider / notes |
|---|---|---|
| GET /api/orbit/status | Service status | Local hub |
| GET /api/search/news?q=... | Existing market RSS news or GDELT search adapter | Results depend on selected route and available services |
| GET /api/search/places?q=... | Place lookup | OpenStreetMap Nominatim is strictly rate-limited |
| GET /api/weather?lat=18.5204&lon=73.8567 | Current weather and forecast | Existing endpoint; no new weather routes were added in this expansion |
| GET /api/currency?from=USD&to=INR&amount=1 | Reference currency conversion | Frankfurter; not a bank quote |
| GET /api/knowledge?q=... | Encyclopedia search | Wikipedia |
| GET /api/images/commons?q=... | Public media candidates | Wikimedia Commons; check each file’s licence |
| GET /api/countries?q=india | Country reference data | REST Countries |
| GET /api/market/quote?symbol=RELIANCE&exchange=NSE | Stock quote | Local Orbit Market adapter; unofficial and may be delayed |
| GET /api/market/history?symbol=RELIANCE&exchange=NSE&interval=1day | Price history | Local Orbit Market adapter; unofficial and may be delayed |

## Important usage limits

- GitHub's unauthenticated REST API is rate-limited. Handle HTTP 403/429 and wait instead of retrying rapidly.
- OpenAlex supports basic keyless use; higher-volume users should review its current authentication and rate-limit policy.
- Crossref, Open Library, Nominatim, MusicBrainz and other public services have usage expectations and may throttle callers.
- Provider outages can cause 404, 429, 502 or partial responses. Federated search calls up to five selected providers concurrently, preserves each provider's result order, and reports per-provider latency and partial failures rather than silently claiming all providers succeeded.
- openFDA, ClinicalTrials.gov and other health-data results are public information, not clinical recommendations.
- Public metadata or media URLs do not imply permission to redistribute the underlying work. Check licences and attribution before reuse.
- DNS, RDAP and certificate transparency results are informational. A lack of a result does not prove a domain, URL or certificate is safe.
- The API hub is bound to localhost by default. Do not expose it publicly without authentication, request limits, logging, and a security review.

Official documentation:
- [OpenAlex API](https://help.openalex.org/api/)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [GitHub REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Open Library API](https://openlibrary.org/developers/api)
- [PyPI JSON API](https://docs.pypi.org/api/json/)
- [ICANN RDAP](https://www.icann.org/rdap/)
