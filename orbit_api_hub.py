#!/usr/bin/env python3
"""Orbit API Hub: no-key public data adapters for the local Orbit Search UI.

This educational prototype uses public endpoints and the local Orbit Market RSS/
price adapter. It does not require API keys or third-party developer accounts.
Respect each provider's terms, rate limits, attribution, and licensing.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from orbit_free_apis import ai_answer, handle_api

VERSION = "0.3"
USER_AGENT = "OrbitSearch/0.3 (educational project; https://github.com/intersprit123/Orbit-Search)"
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


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "")
        parts = urllib.parse.urlsplit(origin)
        if parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "")
        parts = urllib.parse.urlsplit(origin)
        self.send_response(204)
        if parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/ai/answer":
            self.send_json({"ok": False, "error": "Not found", "status": "/api/orbit/status"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 2_000_000:
                self.send_json({"ok": False, "error": "Request body too large."}, 413)
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                self.send_json({"ok": False, "error": "Expected a JSON object."}, 400)
                return
            question = str(body.get("question", "")).strip()
            sources = body.get("sources", [])
            if not question or len(question) > 1500:
                self.send_json({"ok": False, "error": "question is required and must be at most 1500 characters."}, 400)
                return
            if not isinstance(sources, list) or not all(isinstance(x, dict) for x in sources):
                self.send_json({"ok": False, "error": "sources must be an array of result objects."}, 400)
                return
            self.send_json(ai_answer(question, sources))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"ok": False, "error": "Invalid JSON request body."}, 400)
        except Exception as exc:
            self.send_json({"ok": False, "error": "AI adapter failed", "detail": type(exc).__name__}, 502)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        p = urllib.parse.parse_qs(parsed.query)
        q = p.get("q", [""])[0].strip()
        try:
            limit = max(1, min(int(p.get("limit", ["10"])[0]), 50))
            # Free provider adapters take precedence over legacy placeholders.
            handled = handle_api(parsed.path, p)
            if handled is not None:
                status, payload = handled
                self.send_json(payload, status)
                return
            if parsed.path in {"/", "/api/orbit/status"}:
                self.send_json({"ok": True, "service": "Orbit API Hub", "version": VERSION,
                    "api_keys_required": False, "market_base": MARKET_BASE,
                    "providers": ["DuckDuckGo via optional DDGS client", "GDELT News", "YouTube via optional yt-dlp",
                                  "arXiv", "Open-Meteo", "OpenStreetMap Nominatim", "Wikipedia",
                                  "Wikimedia Commons", "REST Countries", "Frankfurter",
                                  "Local Ollama (optional)", "Orbit Market local adapter"],
                    "routes": ["/api/orbit/status", "/api/orbit/catalog",
                        "/api/search/web?q=...", "/api/search/images?q=...", "/api/search/suggest?q=...",
                        "/api/search/news?q=...", "/api/search/videos?q=...", "/api/search/research?q=...",
                        "/api/search/books?q=...", "/api/ai/answer (POST JSON)", "/api/search/places?q=...",
                        "/api/weather?lat=18.5204&lon=73.8567", "/api/currency?from=USD&to=INR&amount=1",
                        "/api/knowledge?q=...", "/api/images/commons?q=...", "/api/countries?q=...",
                        "/api/market/quote?symbol=RELIANCE&exchange=NSE",
                        "/api/market/history?symbol=RELIANCE&exchange=NSE&interval=1day"]})
            elif parsed.path == "/api/search/web":
                self.send_json({"ok": False, "provider": "Orbit Search local crawler",
                    "error": "Use Orbit Search's built-in Web tab for crawler results.",
                    "note": "No external search API or API key is configured."}, 501)
            elif parsed.path == "/api/search/news":
                try:
                    data = request_json(url_with_params(MARKET_BASE + "/api/market/news", {"q": q, "limit": limit}))
                    self.send_json({"ok": True, "provider": "Orbit Market RSS index", "query": q,
                        "data": data, "note": "Headlines are from locally collected RSS feeds; coverage depends on feed sources."})
                except ProviderError:
                    self.send_json({"ok": False, "provider": "Orbit Market RSS index",
                        "error": "Local RSS news is unavailable. Start orbit_market.py and run collect-news.",
                        "setup": "python3 orbit_market.py collect-news"}, 503)
            elif parsed.path == "/api/search/images":
                self.send_json({"ok": True, "provider": "Wikimedia Commons",
                    "note": "Use /api/images/commons?q=... for reusable media candidates."})
            elif parsed.path == "/api/search/videos":
                self.send_json({"ok": False, "provider": "No-key public adapters",
                    "error": "Video search is not enabled because the current suitable providers require an API key or have separate terms."}, 501)
            elif parsed.path == "/api/search/places":
                data = request_json(url_with_params("https://nominatim.openstreetmap.org/search", {
                    "q": q[:200], "format": "jsonv2", "limit": min(limit, 10), "addressdetails": 1}))
                self.send_json({"ok": True, "provider": "OpenStreetMap Nominatim", "query": q, "data": data,
                    "usage_note": "Public Nominatim is rate-limited: no autocomplete or bulk requests; use attribution."})
            elif parsed.path == "/api/weather":
                lat, lon = float(p.get("lat", ["18.5204"])[0]), float(p.get("lon", ["73.8567"])[0])
                data = request_json(url_with_params("https://api.open-meteo.com/v1/forecast", {
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto", "forecast_days": 7}))
                self.send_json({"ok": True, "provider": "Open-Meteo", "data": data,
                    "usage_note": "Free for non-commercial use under provider terms; attribution and usage limits apply."})
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
                    "srlimit": min(limit, 20)}))
                self.send_json({"ok": True, "provider": "Wikipedia", "query": q, "data": data})
            elif parsed.path == "/api/images/commons":
                data = request_json(url_with_params("https://commons.wikimedia.org/w/api.php", {
                    "action": "query", "generator": "search", "gsrsearch": "filetype:bitmap " + q[:150],
                    "gsrnamespace": 6, "gsrlimit": min(limit, 20),
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
                    "results": data[:limit]})
            elif parsed.path == "/api/market/quote":
                symbol, exchange = p.get("symbol", [""])[0], p.get("exchange", ["NSE"])[0]
                data = request_json(url_with_params(MARKET_BASE + "/api/market/quote",
                    {"symbol": symbol, "exchange": exchange}))
                self.send_json({"ok": True, "provider": "Orbit Market local adapter", "data": data,
                    "note": "Unofficial prototype data may be delayed, incomplete, or unavailable."})
            elif parsed.path == "/api/market/history":
                symbol, exchange = p.get("symbol", [""])[0], p.get("exchange", ["NSE"])[0]
                period_map = {"1min": "1mo", "5min": "1mo", "15min": "3mo", "30min": "3mo",
                              "1h": "6mo", "4h": "1y", "1day": "1y", "1week": "5y", "1month": "max"}
                interval = p.get("interval", ["1day"])[0]
                data = request_json(url_with_params(MARKET_BASE + "/api/market/history",
                    {"symbol": symbol, "exchange": exchange, "period": period_map.get(interval, "1y")}))
                self.send_json({"ok": True, "provider": "Orbit Market local adapter", "data": data,
                    "note": "Unofficial prototype data may be delayed, incomplete, or unavailable."})
            else:
                self.send_json({"ok": False, "error": "Not found", "status": "/api/orbit/status"}, 404)
        except (ValueError, TypeError, KeyError):
            self.send_json({"ok": False, "error": "Invalid or missing query parameter."}, 400)
        except ProviderError as exc:
            self.send_json({"ok": False, "error": "Provider request failed", "detail": str(exc)}, 502)
        except Exception as exc:
            self.send_json({"ok": False, "error": "Internal error", "detail": type(exc).__name__}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="Orbit API Hub (no API keys required)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18092)
    parser.add_argument("--share", action="store_true", help="Permit binding beyond localhost")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"} and not args.share:
        parser.error("Non-local binding requires --share; add authentication and rate limits before exposure.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Orbit API Hub listening on http://{args.host}:{args.port}")
    print("No API keys required. Respect each public provider's usage policy.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
