#!/usr/bin/env python3
"""Orbit Market API: self-hosted Indian-stock reference data and financial-news index.

Prices use the optional yfinance package as a prototype adapter; it is an unofficial
third-party source, may be delayed/incomplete, and is not licensed exchange redistribution.
Use a licensed NSE/BSE feed before public/commercial redistribution.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "orbit_market.sqlite3"
USER_AGENT = "OrbitMarket/0.1 (self-hosted educational project)"
NEWS_FEEDS = [
    "https://indianexpress.com/section/business/feed/",
    "https://www.business-standard.com/rss/markets-106.rss",
]
# Starter directory, not a complete exchange security master. Extend with verified symbols.
STARTER_STOCKS = [
    ("RELIANCE", "Reliance Industries", "NSE", "Energy"),
    ("TCS", "Tata Consultancy Services", "NSE", "Information Technology"),
    ("INFY", "Infosys", "NSE", "Information Technology"),
    ("HDFCBANK", "HDFC Bank", "NSE", "Banking"),
    ("ICICIBANK", "ICICI Bank", "NSE", "Banking"),
    ("SBIN", "State Bank of India", "NSE", "Banking"),
    ("ITC", "ITC Limited", "NSE", "Consumer Goods"),
    ("BHARTIARTL", "Bharti Airtel", "NSE", "Telecommunications"),
    ("LT", "Larsen & Toubro", "NSE", "Engineering"),
    ("TATAMOTORS", "Tata Motors", "NSE", "Automobiles"),
    ("WIPRO", "Wipro", "NSE", "Information Technology"),
    ("AXISBANK", "Axis Bank", "NSE", "Banking"),
    ("KOTAKBANK", "Kotak Mahindra Bank", "NSE", "Banking"),
    ("MARUTI", "Maruti Suzuki India", "NSE", "Automobiles"),
    ("SUNPHARMA", "Sun Pharmaceutical Industries", "NSE", "Healthcare"),
]
SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
 symbol TEXT NOT NULL, name TEXT NOT NULL, exchange TEXT NOT NULL,
 sector TEXT NOT NULL DEFAULT '', provider_symbol TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(symbol, exchange)
);
CREATE TABLE IF NOT EXISTS prices (
 symbol TEXT NOT NULL, exchange TEXT NOT NULL, date TEXT NOT NULL,
 open REAL, high REAL, low REAL, close REAL, adjusted_close REAL, volume INTEGER,
 provider TEXT NOT NULL, fetched_at TEXT NOT NULL,
 PRIMARY KEY(symbol, exchange, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE TABLE IF NOT EXISTS news (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
 summary TEXT NOT NULL DEFAULT '', publisher TEXT NOT NULL DEFAULT '',
 published TEXT NOT NULL DEFAULT '', collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published);
"""

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT OR IGNORE INTO stocks(symbol,name,exchange,sector,provider_symbol) VALUES(?,?,?,?,?)",
        [(s,n,e,sec,(s + ".NS") if e == "NSE" else s + ".BO") for s,n,e,sec in STARTER_STOCKS],
    )
    db.commit()
    return db

def stock_search(db_path: Path, q: str, limit: int = 10) -> dict[str, Any]:
    q = q.strip()[:100]
    limit = max(1, min(int(limit), 50))
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT symbol,name,exchange,sector,provider_symbol FROM stocks "
            "WHERE symbol LIKE ? OR name LIKE ? OR sector LIKE ? ORDER BY "
            "CASE WHEN symbol=? THEN 0 ELSE 1 END,name LIMIT ?",
            (f"%{q}%", f"%{q}%", f"%{q}%", q.upper(), limit),
        ).fetchall()
    return {"query": q, "count": len(rows), "results": [dict(r) for r in rows]}

def quote(db_path: Path, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM stocks WHERE symbol=? AND exchange=?", (symbol, exchange)).fetchone()
        if not row:
            # Permit explicit Yahoo-style symbols, but never claim they are verified exchange symbols.
            provider_symbol = symbol if "." in symbol else symbol + (".NS" if exchange == "NSE" else ".BO")
            name = symbol
        else:
            provider_symbol, name = row["provider_symbol"], row["name"]
        latest = db.execute(
            "SELECT * FROM prices WHERE symbol=? AND exchange=? ORDER BY date DESC LIMIT 1",
            (symbol, exchange),
        ).fetchone()
    try:
        import yfinance as yf
    except ImportError:
        if latest:
            return {"symbol": symbol, "exchange": exchange, "name": name, **dict(latest),
                    "data_status": "stored_snapshot", "warning": "Install yfinance to request a fresh prototype quote."}
        return {"error": "Price adapter is not installed and no stored price exists.",
                "install": "python3 -m pip install yfinance", "symbol": symbol, "exchange": exchange}, 503
    try:
        ticker = yf.Ticker(provider_symbol)
        hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
        if hist.empty:
            raise LookupError("Provider returned no price rows for this symbol.")
        last = hist.iloc[-1]
        record = {
            "symbol": symbol, "exchange": exchange, "name": name,
            "date": last.name.date().isoformat(),
            "open": number(last.get("Open")), "high": number(last.get("High")),
            "low": number(last.get("Low")), "close": number(last.get("Close")),
            "adjusted_close": number(last.get("Adj Close")), "volume": integer(last.get("Volume")),
            "provider": "Yahoo Finance via yfinance", "fetched_at": now(),
            "data_status": "provider_snapshot",
            "warning": "Unofficial prototype data; timing, coverage and redistribution rights are not guaranteed."
        }
        with connect(db_path) as db:
            db.execute("""INSERT OR REPLACE INTO prices
              (symbol,exchange,date,open,high,low,close,adjusted_close,volume,provider,fetched_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (symbol,exchange,record["date"],record["open"],record["high"],record["low"],
               record["close"],record["adjusted_close"],record["volume"],record["provider"],record["fetched_at"]))
        return record
    except Exception as exc:
        if latest:
            return {"symbol": symbol, "exchange": exchange, "name": name, **dict(latest),
                    "data_status": "stored_fallback", "warning": "Fresh quote failed; returning stored data.",
                    "provider_error": type(exc).__name__}
        return {"error": "Could not retrieve a quote from the prototype provider.",
                "detail": type(exc).__name__, "symbol": symbol, "exchange": exchange}, 502

def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result else None
    except (TypeError, ValueError):
        return None

def integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def history(db_path: Path, symbol: str, exchange: str = "NSE", period: str = "1y") -> dict[str, Any]:
    allowed = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y", "5y": "5y", "max": "max"}
    if period not in allowed:
        return {"error": "period must be one of " + ", ".join(allowed)}
    symbol, exchange = symbol.strip().upper(), exchange.strip().upper()
    q = quote(db_path, symbol, exchange)
    if isinstance(q, tuple):
        return q[0], q[1]
    provider_symbol = symbol if "." in symbol else symbol + (".NS" if exchange == "NSE" else ".BO")
    try:
        import yfinance as yf
        frame = yf.Ticker(provider_symbol).history(period=allowed[period], interval="1d", auto_adjust=False)
        rows = []
        with connect(db_path) as db:
            for stamp, row in frame.iterrows():
                item = (symbol,exchange,stamp.date().isoformat(),number(row.get("Open")),number(row.get("High")),
                        number(row.get("Low")),number(row.get("Close")),number(row.get("Adj Close")),
                        integer(row.get("Volume")),"Yahoo Finance via yfinance",now())
                db.execute("INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?,?,?,?,?,?,?)", item)
                rows.append({"date":item[2],"open":item[3],"high":item[4],"low":item[5],
                             "close":item[6],"adjusted_close":item[7],"volume":item[8]})
        return {"symbol":symbol,"exchange":exchange,"period":period,"count":len(rows),
                "provider":"Yahoo Finance via yfinance","data_status":"historical_snapshot",
                "warning":"Unofficial prototype data; verify before relying on it.","results":rows}
    except Exception as exc:
        with connect(db_path) as db:
            rows = db.execute("SELECT date,open,high,low,close,adjusted_close,volume FROM prices "
                              "WHERE symbol=? AND exchange=? ORDER BY date DESC LIMIT 1500",
                              (symbol,exchange)).fetchall()
        if rows:
            return {"symbol":symbol,"exchange":exchange,"period":period,"count":len(rows),
                    "data_status":"stored_fallback","warning":"Provider unavailable; stored rows may not cover the requested period.",
                    "results":[dict(r) for r in reversed(rows)]}
        return {"error":"Historical data unavailable","detail":type(exc).__name__}, 502

def collect_news(db_path: Path, feeds: list[str] | None = None) -> dict[str, Any]:
    added, errors = 0, []
    for feed in feeds or NEWS_FEEDS:
        try:
            req = urllib.request.Request(feed, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                root = ET.fromstring(resp.read(3_000_000))
            for item in root.findall(".//item"):
                title = text_of(item, "title")
                link = text_of(item, "link")
                summary = text_of(item, "description")
                published = text_of(item, "pubDate")
                if not title or not link.startswith(("http://", "https://")):
                    continue
                host = urllib.parse.urlsplit(link).hostname or ""
                with connect(db_path) as db:
                    cur = db.execute("INSERT OR IGNORE INTO news(title,url,summary,publisher,published,collected_at) VALUES(?,?,?,?,?,?)",
                                     (title[:500],link,summary[:2000],host,published[:200] if published else "",now()))
                    added += cur.rowcount
        except Exception as exc:
            errors.append({"feed":feed,"error":type(exc).__name__})
        time.sleep(0.5)
    with connect(db_path) as db:
        total = db.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    return {"added":added,"total":total,"errors":errors,
            "note":"Stored headlines, summaries and source links only; publisher terms apply."}

def text_of(node: ET.Element, tag: str) -> str:
    el = node.find(tag)
    return " ".join("".join(el.itertext()).split()) if el is not None else ""

def news_search(db_path: Path, q: str, limit: int = 10) -> dict[str, Any]:
    q = q.strip()[:200]
    limit = max(1, min(int(limit), 50))
    pattern = "%" + q.replace("%", "\\%").replace("_", "\\_") + "%"
    with connect(db_path) as db:
        rows = db.execute("SELECT title,url,summary,publisher,published,collected_at FROM news "
                          "WHERE title LIKE ? OR summary LIKE ? OR publisher LIKE ? "
                          "ORDER BY published DESC,collected_at DESC LIMIT ?",
                          (pattern,pattern,pattern,limit)).fetchall()
    return {"query":q,"count":len(rows),"results":[dict(r) for r in rows]}

class Handler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB
    def send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data,ensure_ascii=False,default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(),fmt % args))
    def do_GET(self) -> None:
        p = urllib.parse.urlsplit(self.path)
        args = urllib.parse.parse_qs(p.query)
        q = args.get("q",[""])[0]
        symbol = args.get("symbol",[""])[0]
        exchange = args.get("exchange",["NSE"])[0]
        try:
            limit = int(args.get("limit",["10"])[0])
            if p.path in {"/", "/api/market/status"}:
                with connect(self.db_path) as db:
                    data = {"ok":True,"service":"Orbit Market API","version":"0.1",
                            "stocks":db.execute("SELECT COUNT(*) FROM stocks").fetchone()[0],
                            "stored_price_rows":db.execute("SELECT COUNT(*) FROM prices").fetchone()[0],
                            "news_items":db.execute("SELECT COUNT(*) FROM news").fetchone()[0],
                            "price_provider":"unofficial yfinance prototype; licensed feed needed for redistribution",
                            "endpoints":["/api/market/status","/api/market/search?q=bank",
                                         "/api/market/quote?symbol=RELIANCE&exchange=NSE",
                                         "/api/market/history?symbol=TCS&period=1y",
                                         "/api/market/news?q=markets"]}
                self.send_json(data)
            elif p.path == "/api/market/search":
                self.send_json(stock_search(self.db_path,q,limit))
            elif p.path == "/api/market/quote":
                result = quote(self.db_path,symbol,exchange)
                if isinstance(result,tuple): self.send_json(result[0],result[1])
                else: self.send_json(result)
            elif p.path == "/api/market/history":
                result = history(self.db_path,symbol,exchange,args.get("period",["1y"])[0])
                if isinstance(result,tuple): self.send_json(result[0],result[1])
                else: self.send_json(result)
            elif p.path == "/api/market/news":
                self.send_json(news_search(self.db_path,q,limit))
            else:
                self.send_json({"error":"Not found","endpoints":["/api/market/status","/api/market/search?q=bank","/api/market/quote?symbol=RELIANCE&exchange=NSE","/api/market/history?symbol=TCS&period=1y","/api/market/news?q=markets"]},404)
        except (ValueError,TypeError):
            self.send_json({"error":"Invalid query parameter"},400)
        except Exception as exc:
            self.send_json({"error":"Internal error","detail":type(exc).__name__},500)

def main() -> int:
    parser = argparse.ArgumentParser(description="Orbit Market API (educational prototype)")
    parser.add_argument("--db",default=str(DEFAULT_DB),help="SQLite database path")
    sub = parser.add_subparsers(dest="command",required=True)
    sub.add_parser("init",help="Initialize database and starter stock directory")
    n = sub.add_parser("collect-news",help="Collect headlines from configured RSS feeds")
    n.add_argument("--feed",action="append",help="RSS URL (repeatable; defaults to built-in feeds)")
    s = sub.add_parser("serve",help="Start the local market REST API")
    s.add_argument("--host",default="127.0.0.1")
    s.add_argument("--port",type=int,default=8090)
    s.add_argument("--share",action="store_true",help="Allow binding beyond localhost")
    args = parser.parse_args()
    db_path = Path(args.db).expanduser().resolve()
    with connect(db_path): pass
    if args.command == "init":
        print(json.dumps({"database":str(db_path),"starter_stocks":len(STARTER_STOCKS)},indent=2))
    elif args.command == "collect-news":
        print(json.dumps(collect_news(db_path,args.feed),indent=2))
    elif args.command == "serve":
        if args.host not in {"127.0.0.1","::1","localhost"} and not args.share:
            parser.error("Non-local binding requires --share; add authentication before exposing publicly.")
        Handler.db_path = db_path
        server = ThreadingHTTPServer((args.host,args.port),Handler)
        print(f"Orbit Market API listening on http://{args.host}:{args.port}")
        print("Press Ctrl+C to stop. Do not expose publicly without authentication and rate limits.")
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
