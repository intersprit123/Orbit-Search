# Orbit Ecosystem and API Hub

Orbit API Hub is a modular local REST gateway for Orbit Search. It adds optional external providers and free/public data services without replacing the existing crawler or Orbit Market API.

## Start it

Run the Market API in one terminal using the port that works on your machine. For example:

```bash
python3 orbit_market.py serve --port 8092
```

In a second terminal:

```bash
python3 orbit_api_hub.py --port 18092
```

Open `http://127.0.0.1:18092/api/orbit/status`. Port 18092 is the default for the hub to avoid common development ports. If your Market API uses a different port, set `ORBIT_MARKET_URL` before starting the hub, for example:

```bash
export ORBIT_MARKET_URL=http://127.0.0.1:8091
python3 orbit_api_hub.py --port 18092
```

No additional Python packages are required for the hub itself; it uses the Python standard library. The separate Market API's optional price adapter still uses `requirements-market.txt`.

## Optional API keys

The free/public endpoints can be tested without keys. Optional provider-backed routes return a clear configuration message if their key is missing.

```bash
export BRAVE_SEARCH_API_KEY='paste-your-key-here'
export GNEWS_API_KEY='paste-your-key-here'
export TWELVE_DATA_API_KEY='paste-your-key-here'
export YOUTUBE_API_KEY='paste-your-key-here'
python3 orbit_api_hub.py --port 18092
```

Set only the keys you actually have. Do not paste keys into source code, commit them to Git, or share screenshots that expose them. These shell exports last only for the current terminal session. For persistent local setup, use a private shell profile or a local ignored environment file.

## Endpoints

| Endpoint | Purpose | Provider / fallback |
|---|---|---|
| `GET /api/orbit/status` | Service status and configured providers | Local |
| `GET /api/search/web?q=...` | Web search | Brave Search API (key required) |
| `GET /api/search/news?q=...` | News search | GNews (key required); falls back to Orbit Market's local RSS index |
| `GET /api/search/images?q=...` | Image search | Brave Search API (key required) |
| `GET /api/search/videos?q=...` | Video search | YouTube Data API if configured, otherwise Brave Search API |
| `GET /api/search/places?q=...` | Place/address lookup | OpenStreetMap Nominatim |
| `GET /api/weather?lat=18.5204&lon=73.8567` | Current conditions and 7-day forecast | Open-Meteo |
| `GET /api/currency?from=USD&to=INR&amount=1` | Reference currency conversion | Frankfurter |
| `GET /api/knowledge?q=...` | Encyclopedia search | Wikipedia |
| `GET /api/images/commons?q=...` | Search reusable media candidates | Wikimedia Commons |
| `GET /api/countries?q=india` | Country reference data | REST Countries |
| `GET /api/market/quote?symbol=RELIANCE&exchange=NSE` | Stock quote | Twelve Data if configured; otherwise local Orbit Market |
| `GET /api/market/history?symbol=RELIANCE&exchange=NSE&interval=1day` | Price history | Twelve Data if configured; otherwise local Orbit Market |

Use URL encoding for search terms containing spaces or special characters. The status endpoint shows whether optional API keys are configured; it never returns their values.

## Provider and usage notes

- **Brave Search API:** its current pricing page lists prepaid usage and a monthly credit. Web, news, image, and video endpoints require a valid key. See the official [API page](https://brave.com/search/api/) and [documentation](https://api-dashboard.search.brave.com/documentation/).
- **GNews:** the free plan is for development/testing and has request and freshness limits; check the current terms before publishing an app. See [pricing](https://gnews.io/pricing) and [docs](https://docs.gnews.io/).
- **Twelve Data:** coverage, exchange availability, update frequency, and API credits depend on the selected plan. Check current [docs](https://twelvedata.com/docs) and [pricing](https://twelvedata.com/pricing). Do not assume NSE data is real-time on a free plan.
- **Orbit Market:** its existing `yfinance` adapter is unofficial and may be delayed or incomplete. Do not describe it as guaranteed live exchange data or redistribute it commercially without the appropriate rights.
- **OpenStreetMap Nominatim:** follow its usage policy; it is not intended for high-volume autocomplete. For a public app, use a suitable provider or host an appropriate geocoder.
- **Open-Meteo, Frankfurter, Wikipedia, Wikimedia Commons, and REST Countries:** check their current terms, attribution requirements, and suitability for your use. For Commons, check the license of each individual image before reuse.
- **YouTube:** API key use is subject to YouTube Data API quota and terms.
- **Security:** the hub binds to localhost by default and has no authentication or per-user rate limits. Do not expose it to the public internet until authentication, rate limits, input validation, and deployment protections are added.

## Integration status

This commit adds the backend API hub. It does not yet add tabs/buttons to the existing browser UI. The next UI step is to connect the existing search page to these routes and display provider/source labels, loading states, errors, and attribution.
