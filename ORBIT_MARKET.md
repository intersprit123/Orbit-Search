# Orbit Market API

A small self-hosted REST API module for Orbit Search, focused on Indian stock symbols and financial-news discovery.

## Status

This is an educational prototype, not an exchange-authorized market-data service. It includes a small starter stock directory, an SQLite database, an RSS headline collector, and optional historical/quote lookups through `yfinance`.

**Data caveat:** `yfinance` is an unofficial adapter. Data may be delayed, incomplete, unavailable, or subject to provider terms. Do not present it as guaranteed live NSE/BSE data or redistribute it commercially. For production, replace the adapter with a properly licensed NSE/BSE data feed. RSS collection stores headline, summary and source URL; respect each publisher's terms.

## Quick start (Kali/Linux)

```bash
git pull
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-market.txt
python3 orbit_market.py init
python3 orbit_market.py collect-news
python3 orbit_market.py serve --port 8090
```

If your project already has a virtual environment, activate it instead of creating a new one. The server stays in the foreground; keep that terminal open.

## Endpoints

- `GET /api/market/status` — database and service status.
- `GET /api/market/search?q=bank` — search the starter stock directory.
- `GET /api/market/quote?symbol=RELIANCE&exchange=NSE` — latest available prototype quote.
- `GET /api/market/history?symbol=TCS&exchange=NSE&period=1y` — daily historical data. Periods: `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `max`.
- `GET /api/market/news?q=markets` — search headlines already collected.

Example local URLs:

- `http://127.0.0.1:8090/api/market/status`
- `http://127.0.0.1:8090/api/market/search?q=bank`
- `http://127.0.0.1:8090/api/market/quote?symbol=RELIANCE&exchange=NSE`
- `http://127.0.0.1:8090/api/market/news?q=markets`

Collect headlines again whenever you want to refresh the local news index:

```bash
python3 orbit_market.py collect-news
```

To test another RSS feed, pass `--feed 'https://example.com/feed.xml'` (repeat `--feed` for multiple feeds).

## Notes / next steps

- The starter directory is intentionally small and must be expanded using verified symbols and exchange data.
- The initial quote adapter may be called per request; add caching, request throttling and scheduled sync before heavier use.
- The current API binds to localhost by default. Do not expose it publicly without authentication, rate limits, and operational protections.
- Next integration step: add a Market tab to Orbit Search and have it call these endpoints.
