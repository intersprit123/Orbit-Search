#!/usr/bin/env python3
"""Orbit API Hub: optional web/news/media/place/utility/finance integrations.

All provider keys are read from environment variables. The service binds to
localhost by default. This is an educational prototype, not a production gateway.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

VERSION = "0.1"
USER_AGENT = "OrbitSearch/0.1 (educational project)"
BRAVE_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
GNEWS_KEY = os.getenv("GNEWS_API_KEY", "")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
YOUTUBE_KEY = os.getenv("YOUTUBE_API_KEY", "")
MARKET_BASE = os.getenv("ORBIT_MARKET_URL", "http://127.0.0.1:8092").rstrip(" /")


class ProviderError(RuntimeError):
    pass


def request_json(url: str, headers: dict[str, str] | None = None, timeout: int = 12) -> Any:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read(4_000_000).decode("utf-8", "replace"))
    except Exception as exc:
        raise ProviderError(type(exc).__name__) from exc


def url_with_params(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def brave_search(path: str, q: str, count: int = 10, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if not BRAVE_KEY:
        return {"ok": False, "provider": "Brave Search API", "error": "API key not configured",
                "setup": "Set BRAVE_SEARCH_API_KEY in your environment."}
    params: dict[str, Any] = {"q": q[:300], "count": max(1, min(int(count), 20))}
    if extra:
        params.update(extra)
    data = request_json(url_with_params("https://api.search.brave.com/res/v1/" + path, params),
                        {"Accept": "application/json", "X-Subscription-Token": BRAVE_KEY})
    return {"ok": True, "provider": "Brave Search API", "query": q, "data": data}


def gnews(q: str, count: int = 10) -> dict[str, Any]:
    if not GNEWS_KEY:
        return {"ok": False, "provider": "GNews", "error": "API key not configured",
                "setup": "Set GNEWS_API_KEY in your environment. Local RSS news remains available through Orbit Market."}
    params = {"q": q[:200], "lang": "en", "max": max(1, min(int(count), 10)), "apikey": GNEWS_KEY}
    data = request_json(url_with_params("https://gnews.io/api/v4/search", params))
    return {"ok": True, "provider": "GNews", "query": q, "data": data}


def twelve_data_quote(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    if not TWELVE_DATA_KEY:
        return {"ok": False, "provider": "Twelve Data", "error": "API key not configured",
                "setup": "Set TWELVE_DATA_API_KEY in your environment."}
    data = request_json(url_with_params("https://api.twelvedata.com/quote", {
        "symbol": symbol[:40], "exchange": exchange[:20], "apikey": TWELVE_DATA_KEY}))
    if data.get("status") == "error":
        return {"ok": False, "provider": "Twelve Data", "error": data.get("message", "Provider error"), "data": data}
    return {"ok": True, "provider": "Twelve Data", "data": data,
            "note": "Check the provider plan and exchange coverage; values may be delayed depending on entitlement."}


def twelve_data_history(symbol: str, exchange: str = "NSE", interval: str = "1day", outputsize: int = 100) -> dict[str, Any]:
    if not TWELVE_DATA_KEY:
        return {"ok": False, "provider": "Twelve Data", "error": "API key not configured",
                "setup": "Set TWELVE_DATA_API_KEY in your environment."}
    allowed = {"1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week", "1month"}
    if interval not in allowed:
        return {"ok": False, "error": "Invalid interval", "allowed": sorted(allowed)}
    data = request_json(url_with_params("https://api.twelvedata.com/time_series", {
        "symbol": symbol[:40], "exchange": exchange[:20], "interval": interval,
        "outputsize": max(1, min(int(outputsize), 500)), "apikey": TWELVE_DATA_KEY}))
    if data.get("status") == "error":
        return {"ok": False, "provider": "Twelve Data", "error": data.get("message", "Provider error"), "data": data}
    return {"ok": True, "provider": "Twelve Data", "data": data,
            "note": "Check the provider plan and exchange coverage; values may be delayed depending on entitlement."}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        p = urllib.parse.parse_qs(parsed.query)
        q = p.get("q", [""])[0].strip()
        try:
            limit = int(p.get("limit", ["10"])[0])
            if parsed.path in {"/", "/api/orbit/status"}:
                self.send_json({"ok": True, "service": "Orbit API Hub", "version": VERSION,
                    "providers": {
                        "brave": bool(BRAVE_KEY), "gnews": bool(GNEWS_KEY),
                        "twelve_data": bool(TWELVE_DATA_KEY), "youtube": bool(YOUTUBE_KEY),
                        "local_market_api": MARKET_BASE},
                    "routes": ["/api/orbit/status", "/api/search/web?q=...", "/api/search/news?q=...",
                        "/api/search/images?q=...", "/api/search/videos?q=...", "/api/search/places?q=...",
                        "/api/weather?lat=18.5204&lon=73.8567", "/api/currency?from=USD&to=INR&amount=1",
                        "/api/knowledge?q=...", "/api/images/commons?q=...", "/api/countries?q=...",
                        "/api/market/quote?symbol=RELIANCE&exchange=NSE",
                        "/api/market/history?symbol=RELIANCE&exchange=NSE&interval=1day"]})
            elif parsed.path == "/api/search/web":
                self.send_json(brave_search("web/search", q, limit))
            elif parsed.path == "/api/search/news":
                result = gnews(q, limit)
                if result.get("ok"):
                    self.send_json(result)
                else:
                    try:
                        fallback = request_json(url_with_params(MARKET_BASE + "/api/market/news", {"q": q, "limit": limit}))
                        self.send_json({"ok": True, "provider": "Orbit Market RSS index", "query": q,
                            "data": fallback, "note": "GNews key is not configured; results come from locally collected RSS headlines."})
                    except ProviderError:
                        self.send_json({"ok": False, "provider": "GNews", "error": result.get("error"),
                            "setup": result.get("setup"), "fallback": "Start orbit_market.py and configure GNEWS_API_KEY for external news search."})
            elif parsed.path == "/api/search/images":
                self.send_json(brave_search("images/search", q, limit))
            elif parsed.path == "/api/search/videos":
                if YOUTUBE_KEY:
                    data = request_json(url_with_params("https://www.googleapis.com/youtube/v3/search", {
                        "part": "snippet", "type": "video", "maxResults": max(1, min(limit, 50)),
                        "q": q[:200], "key": YOUTUBE_KEY}))
                    self.send_json({"ok": True, "provider": "YouTube Data API", "data": data})
                else:
                    self.send_json(brave_search("videos/search", q, limit))
            elif parsed.path == "/api/search/places":
                data = request_json(url_with_params("https://nominatim.openstreetmap.org/search", {
                    "q": q[:200], "format": "jsonv2", "limit": max(1, min(limit, 10)), "addressdetails": 1}))
                self.send_json({"ok": True, "provider": "OpenStreetMap Nominatim", "query": q, "data": data,
                    "usage_note": "Respect Nominatim's usage policy; do not use for autocomplete or high-volume traffic."})
            elif parsed.path == "/api/weather":
                lat, lon = float(p.get("lat", ["18.5204"])[0]), float(p.get("lon", ["73.8567"])[0])
                data = request_json(url_with_params("https://api.open-meteo.com/v1/forecast", {
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto", "forecast_days": 7}))
                self.send_json({"ok": True, "provider": "Open-Meteo", "data": data,
                    "usage_note": "Check Open-Meteo terms for your use case, especially commercial use."})
            elif parsed.path == "/api/currency":
                source, target = p.get("from", ["USD"])[0].upper(), p.get("to", ["INR"])[0].upper()
                amount = float(p.get("amount", ["1"])[0])
                if amount < 0 or len(source) != 3 or len(target) != 3:
                    self.send_json({"ok": False, "error": "Use a non-negative amount and 3-letter currency codes."}, 400)
                    return
                data = request_json(f"https://api.frankfurter.dev/v2/rate/{urllib.parse.quote(source)}/{urllib.parse.quote(target)}")
                rate = float(data["rate"])
                self.send_json({"ok": True, "provider": "Frankfurter", "from": source, "to": target,
                    "amount": amount, "rate": rate, "converted": amount * rate, "date": data.get("date"),
                    "note": "Reference exchange rate, not a guaranteed bank or live trading quote."})
            elif parsed.path == "/api/knowledge":
                data = request_json(url_with_params("https://en.wikipedia.org/w/api.php", {
                    "action": "query", "list": "search", "srsearch": q[:200], "format": "json",
                    "srlimit": max(1, min(limit, 20))}))
                self.send_json({"ok": True, "provider": "Wikipedia", "query": q, "data": data})
            elif parsed.path == "/api/images/commons":
                data = request_json(url_with_params("https://commons.wikimedia.org/w/api.php", {
                    "action": "query", "generator": "search", "gsrsearch": "filetype:bitmap " + q[:150],
                    "gsrnamespace": 6, "gsrlimit": max(1, min(limit, 20)),
                    "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 500,
                    "format": "json"}))
                self.send_json({"ok": True, "provider": "Wikimedia Commons", "query": q, "data": data,
                    "note": "Check each file's license and attribution requirements before reuse."})
            elif parsed.path == "/api/countries":
                data = request_json("https://restcountries.com/v3.1/all?fields=name,cca2,cca3,capital,region,subregion,population,currencies,languages,flags")
                if q:
                    needle = q.casefold()
                    data = [c for c in data if needle in c.get("name", {}).get("common", "").casefold()
                            or needle in c.get("region", "").casefold()
                            or needle in c.get("cca2", "").casefold()]
                self.send_json({"ok": True, "provider": "REST Countries", "query": q, "count": len(data),
                    "results": data[:max(1, min(limit, 50))]})
            elif parsed.path == "/api/market/quote":
                symbol, exchange = p.get("symbol", [""])[0], p.get("exchange", ["NSE"])[0]
                if TWELVE_DATA_KEY:
                    self.send_json(twelve_data_quote(symbol, exchange))
                else:
                    try:
                        data = request_json(url_with_params(MARKET_BASE + "/api/market/quote",
                            {"symbol": symbol, "exchange": exchange}))
                        self.send_json({"ok": True, "provider": "Orbit Market local adapter", "data": data})
                    except ProviderError:
                        self.send_json(twelve_data_quote(symbol, exchange))
            elif parsed.path == "/api/market/history":
                symbol, exchange = p.get("symbol", [""])[0], p.get("exchange", ["NSE"])[0]
                if TWELVE_DATA_KEY:
                    self.send_json(twelve_data_history(symbol, exchange, p.get("interval", ["1day"])[0], limit))
                else:
                    period_map = {"1min": "1mo", "5min": "1mo", "15min": "3mo", "30min": "3mo",
                                  "1h": "6mo", "4h": "1y", "1day": "1y", "1week": "5y", "1month": "max"}
                    try:
                        data = request_json(url_with_params(MARKET_BASE + "/api/market/history",
                            {"symbol": symbol, "exchange": exchange, "period": period_map.get(p.get("interval", ["1day"])[0], "1y")}))
                        self.send_json({"ok": True, "provider": "Orbit Market local adapter", "data": data,
                            "note": "Local prototype data; source may be unofficial or delayed."})
                    except ProviderError:
                        self.send_json(twelve_data_history(symbol, exchange, p.get("interval", ["1day"])[0], limit))
            else:
                self.send_json({"ok": False, "error": "Not found", "status": "/api/orbit/status"}, 404)
        except (ValueError, TypeError, KeyError):
            self.send_json({"ok": False, "error": "Invalid or missing query parameter."}, 400)
        except ProviderError as exc:
            self.send_json({"ok": False, "error": "Provider request failed", "detail": str(exc)}, 502)
        except Exception as exc:
            self.send_json({"ok": False, "error": "Internal error", "detail": type(exc).__name__}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="Orbit API Hub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18092)
    parser.add_argument("--share", action="store_true", help="Permit binding beyond localhost")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"} and not args.share:
        parser.error("Non-local binding requires --share; add authentication and rate limits before exposure.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Orbit API Hub listening on http://{args.host}:{args.port}")
    print("Optional keys: BRAVE_SEARCH_API_KEY, GNEWS_API_KEY, TWELVE_DATA_API_KEY, YOUTUBE_API_KEY")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
