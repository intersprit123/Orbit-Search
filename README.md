# Orbit-Search

A self-hosted web search project with a local crawler, SQLite/FTS5 index, browser UI, and REST endpoints.

## Orbit Market API (prototype)

Orbit Search now includes a separate API module for Indian-stock discovery and financial-news indexing.

See [ORBIT_MARKET.md](ORBIT_MARKET.md) for setup and endpoint details.

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
