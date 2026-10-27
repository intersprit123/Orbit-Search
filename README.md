# Orbit-Search

A self-hosted web search project with a local crawler, SQLite/FTS5 index, browser UI, and REST endpoints.

## Orbit ecosystem API hub

Orbit now includes a modular API gateway for web/news/image/video search, place lookup, weather, currency conversion, encyclopedia search, country data, and market quotes/history. Optional provider keys are read from environment variables.

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


## Start the API Hub

Start the market service on the port that works on your machine (example: 8092):

```bash
python3 orbit_market.py serve --port 8092
```

In a second terminal, start the hub:

```bash
python3 orbit_api_hub.py --port 18092
```

Check `http://127.0.0.1:18092/api/orbit/status`. Set `ORBIT_MARKET_URL` if your market service uses a different port. Provider keys are optional; see [ORBIT_ECOSYSTEM.md](ORBIT_ECOSYSTEM.md). Do not commit API keys or expose this unauthenticated prototype to the public internet.
