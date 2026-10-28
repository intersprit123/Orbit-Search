# Orbit Ecosystem — no-key setup

Orbit Search's API Hub is designed to work without API keys, paid subscriptions, free trials, or third-party developer accounts. The hub uses public data services and the local Orbit Market adapter.

## Start the services

Terminal 1: start Orbit Market on the port available on your machine (example: 8092):

```bash
python3 orbit_market.py serve --port 8092
```

Terminal 2:

```bash
python3 orbit_api_hub.py --port 18092
```

If Orbit Market uses another port, set it before starting the hub:

```bash
export ORBIT_MARKET_URL=http://127.0.0.1:8091
python3 orbit_api_hub.py --port 18092
```

Open `http://127.0.0.1:18092/api/orbit/status` to check the hub. The hub uses only Python's standard library. No API keys or additional packages are required for the hub itself.

## No-key endpoints

| `GET /api/search/all?q=...&sources=web,news,research,books` | Federated search with provider status, deduplication, and partial-failure reporting | Optional DDGS web/image search, GDELT news, arXiv, Google Books; specify `sources=web,images,news,research,books` to select sources |
| `GET /api/search/related?q=...` | Related search suggestions | DDGS with Wikipedia OpenSearch fallback |

| Endpoint | Purpose | Provider / notes |
|---|---|---|
| `GET /api/orbit/status` | Service status | Local hub |
| `GET /api/search/news?q=...` | Search collected news headlines | Orbit Market's local RSS index; start Market and run `python3 orbit_market.py collect-news` |
| `GET /api/search/places?q=...` | Place/address lookup | OpenStreetMap Nominatim; strict rate limits apply |
| `GET /api/weather?lat=18.5204&lon=73.8567` | Current weather and 7-day forecast | Open-Meteo |
| `GET /api/currency?from=USD&to=INR&amount=1` | Reference currency conversion | Frankfurter; not a bank quote |
| `GET /api/knowledge?q=...` | Encyclopedia search | Wikipedia |
| `GET /api/images/commons?q=...` | Media candidates | Wikimedia Commons; check each file's license |
| `GET /api/countries?q=india` | Country reference data | REST Countries |
| `GET /api/market/quote?symbol=RELIANCE&exchange=NSE` | Stock quote | Local Orbit Market adapter; unofficial and may be delayed |
| `GET /api/market/history?symbol=RELIANCE&exchange=NSE&interval=1day` | Price history | Local Orbit Market adapter; unofficial and may be delayed |

## What is intentionally not enabled?

- No Brave Search, GNews, Twelve Data, or YouTube API keys.
- No paid API subscriptions, developer-account setup, or adult-account signup flows.
- The built-in Orbit Search Web tab uses Orbit's existing local crawler/search API. It is separate from this hub.
- Video search is intentionally excluded from this build.
- The local market adapter may use unofficial data sources. Do not treat it as guaranteed real-time financial data.

## Public-service rules

“No API key” does not mean unlimited use or unrestricted reuse. Respect provider policies and attribution/licensing requirements:

- **Open-Meteo:** free for non-commercial use under its terms; check current terms and attribution requirements: https://open-meteo.com/en/terms
- **Nominatim / OpenStreetMap:** public Nominatim has strict usage limits; do not use for autocomplete or bulk requests. Attribution is required: https://operations.osmfoundation.org/policies/nominatim/
- **Wikimedia APIs:** follow access policy and identify your application: https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy
- **Wikimedia Commons:** individual files have different licenses; check each file before reuse.
- **Wikipedia:** respect Wikimedia API policy and source attribution.
- **Frankfurter:** reference exchange rates can lag and are not guaranteed bank/trading rates.
- **REST Countries:** public community API; use responsibly and expect availability/schema changes.

Keep the hub bound to localhost. Do not expose it to the internet without authentication, rate limiting, and a security review.
