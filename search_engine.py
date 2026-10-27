#!/usr/bin/env python3
"""
Our Own Web Search API
- Self-hosted public-web crawler
- SQLite + FTS5 search index
- Local REST API and browser UI
- Python standard library only (no external search APIs)
- Respect robots.txt, same-host crawling, bounded pages, and crawl delays

Default binding is 127.0.0.1 for safety. Public deployment should be protected
with a reverse proxy/auth layer and appropriate operational controls.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from advanced_features import ai_answer, index_pdf, news_search, research_search, semantic_search, url_safety_check

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "search.sqlite3"
DEFAULT_SEEDS = ROOT / "sites.txt"
USER_AGENT = "OurOwnSearchBot/0.1 (+self-hosted educational search engine)"
MAX_BODY_BYTES = 2_000_000
DEFAULT_DELAY = 1.5
FETCH_TIMEOUT = 12
MAX_QUERY_CHARS = 300
MAX_LIMIT = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL,
    status_code INTEGER NOT NULL DEFAULT 200
);
CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, body, content='pages', content_rowid='id',
    tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
    INSERT INTO pages_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TABLE IF NOT EXISTS crawl_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    url TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS seeds (
    url TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def normalize_url(raw: str, base: str | None = None) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if base:
        raw = urllib.parse.urljoin(base, raw)
    try:
        p = urllib.parse.urlsplit(raw)
    except ValueError:
        return None
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return None
    if p.username or p.password:
        return None
    host = p.hostname.lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or "." not in host:
        return None
    port = p.port
    netloc = host
    if port and not ((p.scheme.lower() == "http" and port == 80) or
                     (p.scheme.lower() == "https" and port == 443)):
        netloc += f":{port}"
    path = p.path or "/"
    # Avoid endless URL spaces and common tracking/session query parameters.
    query_items = urllib.parse.parse_qsl(p.query, keep_blank_values=False)
    filtered = [(k, v) for k, v in query_items
                if not re.match(r"^(utm_.+|fbclid|gclid|mc_cid|mc_eid|sessionid|phpsessid)$",
                                k.lower())]
    query = urllib.parse.urlencode(filtered, doseq=True)
    return urllib.parse.urlunsplit((p.scheme.lower(), netloc, path, query, ""))


def is_public_host(host: str) -> bool:
    """Reject localhost/private/reserved IPs, including hostnames resolving to them."""
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return False
    found = set()
    for record in records:
        address = record[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
        found.add(address)
    return bool(found)


def url_host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")


class PageParser(HTMLParser):
    DROP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template", "iframe"}
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._title = False
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = dict(attrs)
        if tag in self.DROP_TAGS:
            self._drop_depth += 1
        if tag == "title":
            self._title = True
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"] or "")
        if tag in {"br", "p", "div", "li", "h1", "h2", "h3", "section", "article"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.DROP_TAGS and self._drop_depth:
            self._drop_depth -= 1
        if tag == "title":
            self._title = False
        if tag in {"p", "div", "li", "h1", "h2", "h3", "section", "article"}:
            self.text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        data = re.sub(r"\s+", " ", data).strip()
        if not data:
            return
        if self._title:
            self.title_parts.append(data)
        self.text_parts.append(data)

    def results(self) -> tuple[str, str, list[str]]:
        title = re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()[:500]
        body = re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()[:500_000]
        return title, body, self.links


class PublicCrawler:
    def __init__(self, db_path: Path, user_delay: float = DEFAULT_DELAY,
                 max_per_domain: int = 10, max_pages: int = 100) -> None:
        self.db_path = db_path
        self.user_delay = max(1.0, user_delay)
        self.max_per_domain = max(1, max_per_domain)
        self.max_pages = max(1, max_pages)
        self.robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.domain_last_request: dict[str, float] = {}
        self.domain_counts: dict[str, int] = {}

    def _log(self, conn: sqlite3.Connection, url: str, result: str, detail: str = "") -> None:
        conn.execute(
            "INSERT INTO crawl_log(timestamp, url, result, detail) VALUES (?, ?, ?, ?)",
            (utc_now(), url, result, detail[:500])
        )
        conn.commit()

    def _fetch(self, url: str, max_bytes: int = MAX_BODY_BYTES) -> tuple[bytes, str, int] | None:
        host = url_host(url)
        if not is_public_host(host):
            return None
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        })
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(x in content_type for x in ("text/html", "application/xhtml+xml", "text/xml", "application/xml")):
                    return None
                payload = resp.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    payload = payload[:max_bytes]
                charset = resp.headers.get_content_charset() or "utf-8"
                return payload, charset, getattr(resp, "status", 200)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def _robots(self, base_url: str) -> urllib.robotparser.RobotFileParser:
        parsed = urllib.parse.urlsplit(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self.robots_cache:
            return self.robots_cache[origin]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = origin + "/robots.txt"
        rp.set_url(robots_url)
        # Fail closed if robots.txt cannot be read: skip crawling this host.
        try:
            req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                txt = resp.read(256_000).decode("utf-8", "replace")
            rp.parse(txt.splitlines())
        except Exception:
            rp.parse(["User-agent: *", "Disallow: /"])
        self.robots_cache[origin] = rp
        return rp

    def _polite_wait(self, host: str, robots: urllib.robotparser.RobotFileParser) -> None:
        delay = max(self.user_delay, robots.crawl_delay(USER_AGENT) or 0,
                    robots.crawl_delay("*") or 0)
        last = self.domain_last_request.get(host, 0.0)
        wait = delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        self.domain_last_request[host] = time.monotonic()

    def _sitemap_links(self, seed_url: str, rp: urllib.robotparser.RobotFileParser) -> list[str]:
        site_maps = list(rp.site_maps() or [])
        p = urllib.parse.urlsplit(seed_url)
        origin = f"{p.scheme}://{p.netloc}"
        if not site_maps:
            site_maps = [origin + "/sitemap.xml"]
        out: list[str] = []
        for sm in site_maps[:5]:
            fetched = self._fetch(sm, max_bytes=2_000_000)
            if not fetched:
                continue
            payload, charset, _ = fetched
            try:
                # Some servers advertise invalid charset names (for example,
                # "urtf-8"). Fall back to UTF-8 instead of aborting the crawl.
                try:
                    decoded = payload.decode(charset or "utf-8", "replace")
                except (LookupError, TypeError):
                    decoded = payload.decode("utf-8", "replace")
                root = ElementTree.fromstring(decoded)
            except ElementTree.ParseError:
                continue
            for elem in root.iter():
                if elem.tag.rsplit("}", 1)[-1].lower() == "loc" and elem.text:
                    norm = normalize_url(elem.text.strip())
                    if norm:
                        out.append(norm)
                        if len(out) >= self.max_per_domain * 3:
                            return out
        return out

    def add_seeds_file(self, seeds_file: Path) -> int:
        if not seeds_file.exists():
            raise FileNotFoundError(f"Seed file not found: {seeds_file}")
        added = 0
        with db_connect(self.db_path) as conn:
            for line in seeds_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "://" not in line:
                    line = "https://" + line
                url = normalize_url(line)
                if not url or not is_public_host(url_host(url)):
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO seeds(url, added_at) VALUES (?, ?)",
                    (url, utc_now())
                )
                added += cur.rowcount
            conn.commit()
        return added

    def crawl(self) -> dict[str, Any]:
        with db_connect(self.db_path) as conn:
            seeds = [r["url"] for r in conn.execute("SELECT url FROM seeds ORDER BY url")]
        queue: list[tuple[str, str]] = []
        for seed in seeds:
            queue.append((seed, url_host(seed)))
        seen: set[str] = set()
        indexed = 0
        skipped = 0
        errors = 0

        while queue and indexed + skipped + errors < self.max_pages:
            url, allowed_host = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if url_host(url) != allowed_host:
                skipped += 1
                continue
            if self.domain_counts.get(allowed_host, 0) >= self.max_per_domain:
                skipped += 1
                continue

            rp = self._robots(url)
            if not rp.can_fetch(USER_AGENT, url):
                skipped += 1
                with db_connect(self.db_path) as conn:
                    self._log(conn, url, "robots_disallowed")
                continue

            self._polite_wait(allowed_host, rp)
            fetched = self._fetch(url)
            if not fetched:
                errors += 1
                with db_connect(self.db_path) as conn:
                    self._log(conn, url, "fetch_failed_or_non_html")
                continue

            payload, charset, status_code = fetched
            try:
                decoded = payload.decode(charset or "utf-8", "replace")
            except (LookupError, TypeError):
                # Invalid or missing charset supplied by a remote website.
                decoded = payload.decode("utf-8", "replace")
            parser = PageParser()
            try:
                parser.feed(decoded)
                title, body, links = parser.results()
            except Exception:
                errors += 1
                continue

            if not title and not body:
                skipped += 1
                continue
            with db_connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO pages(url, domain, title, body, fetched_at, status_code)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        domain=excluded.domain, title=excluded.title, body=excluded.body,
                        fetched_at=excluded.fetched_at, status_code=excluded.status_code
                """, (url, allowed_host, title, body, utc_now(), status_code))
                self._log(conn, url, "indexed", f"title={title[:150]}")
                conn.commit()
            indexed += 1
            self.domain_counts[allowed_host] = self.domain_counts.get(allowed_host, 0) + 1

            for link in links:
                link_url = normalize_url(link, url)
                if not link_url or url_host(link_url) != allowed_host or link_url in seen:
                    continue
                # Avoid crawling common unbounded/search/action URLs.
                path = urllib.parse.urlsplit(link_url).path.lower()
                if any(part in path for part in ("/logout", "/signin", "/login", "/cart", "/checkout")):
                    continue
                queue.append((link_url, allowed_host))

            # Sitemaps can seed deeper public pages, still constrained to the same hostname.
            if self.domain_counts[allowed_host] == 1:
                for sitemap_url in self._sitemap_links(url, rp):
                    if url_host(sitemap_url) == allowed_host and sitemap_url not in seen:
                        queue.append((sitemap_url, allowed_host))

        return {
            "seed_domains": len({url_host(s) for s in seeds}),
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
            "queued_remaining": len(queue),
            "limits": {"max_pages_per_run": self.max_pages, "max_pages_per_domain": self.max_per_domain,
                       "minimum_delay_seconds": self.user_delay},
            "note": "Only publicly accessible HTML pages permitted by robots.txt are considered."
        }


def search_pages(db_path: Path, q: str, limit: int = 10, site: str | None = None) -> dict[str, Any]:
    q = q.strip()[:MAX_QUERY_CHARS]
    if not q:
        return {"query": q, "count": 0, "results": []}
    # Build safe FTS terms instead of accepting raw FTS operators from clients.
    terms = re.findall(r"[\w@.+-]+", q, flags=re.UNICODE)
    terms = [t for t in terms if t.strip("+-")]
    if not terms:
        return {"query": q, "count": 0, "results": []}
    fts_query = " AND ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])
    limit = max(1, min(int(limit), MAX_LIMIT))
    with db_connect(db_path) as conn:
        sql = """
            SELECT p.url, p.domain, p.title,
                   snippet(pages_fts, 1, '[', ']', ' … ', 18) AS snippet,
                   p.fetched_at, bm25(pages_fts) AS rank
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
        """
        params: list[Any] = [fts_query]
        if site:
            clean_site = site.lower().strip()
            if not re.fullmatch(r"[a-z0-9.-]+", clean_site):
                return {"query": q, "count": 0, "results": [], "error": "Invalid site filter"}
            sql += " AND p.domain = ?"
            params.append(clean_site)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        results.append({
            "url": r["url"],
            "domain": r["domain"],
            "title": r["title"],
            "snippet": r["snippet"],
            "indexed_at": r["fetched_at"],
        })
    return {"query": q, "count": len(results), "results": results}


def external_json(url: str, timeout: float = 8.0) -> Any:
    """Fetch a public JSON API with a descriptive user agent and bounded timeout."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "OurOwnSearch/2.0 (educational multi-source search; contact: local-admin)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise urllib.error.HTTPError(url, response.status, "API request failed", response.headers, None)
        return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))


def multi_source_search(db_path: Path, q: str, limit: int = 8,
                        sources: list[str] | None = None) -> dict[str, Any]:
    """Combine local indexed pages with selected public discovery APIs."""
    q = q.strip()[:MAX_QUERY_CHARS]
    limit = max(1, min(int(limit), 20))
    allowed = {"web", "wikipedia", "books", "github", "images", "news", "research"}
    selected = set(sources or allowed) & allowed
    results: list[dict[str, Any]] = []
    source_status: dict[str, str] = {}

    if "web" in selected:
        try:
            local = search_pages(db_path, q, limit)
            for item in local.get("results", []):
                results.append({**item, "source": "local_web", "kind": "web"})
            source_status["web"] = "ok"
        except sqlite3.OperationalError:
            source_status["web"] = "local index not initialized"

    encoded = urllib.parse.quote(q)
    if q:
        if "wikipedia" in selected:
            try:
                data = external_json(f"https://en.wikipedia.org/w/rest.php/v1/search/page?q={encoded}&limit={limit}")
                for item in data.get("pages", []):
                    results.append({"title": item.get("title", "Wikipedia result"),
                                    "url": item.get("key") and "https://en.wikipedia.org/wiki/" + urllib.parse.quote(item["key"].replace(" ", "_"), safe="()_-") or "https://en.wikipedia.org/",
                                    "snippet": re.sub(r"<[^>]+>", "", item.get("excerpt", "") or item.get("description", "")),
                                    "source": "wikipedia", "kind": "knowledge"})
                source_status["wikipedia"] = "ok"
            except Exception as exc:
                source_status["wikipedia"] = f"unavailable: {type(exc).__name__}"

        if "books" in selected:
            try:
                data = external_json(f"https://openlibrary.org/search.json?q={encoded}&limit={limit}")
                for item in data.get("docs", []):
                    key = item.get("key", "")
                    authors = ", ".join(item.get("author_name", [])[:3])
                    results.append({"title": item.get("title", "Untitled book"),
                                    "url": "https://openlibrary.org" + key if key.startswith("/") else "https://openlibrary.org/",
                                    "snippet": (f"Authors: {authors}. " if authors else "") + (f"First published: {item.get('first_publish_year')}." if item.get("first_publish_year") else "Book catalog record."),
                                    "source": "open_library", "kind": "book"})
                source_status["books"] = "ok"
            except Exception as exc:
                source_status["books"] = f"unavailable: {type(exc).__name__}"

        if "github" in selected:
            try:
                data = external_json(f"https://api.github.com/search/repositories?q={encoded}&sort=stars&per_page={limit}")
                for item in data.get("items", []):
                    results.append({"title": item.get("full_name", "GitHub repository"),
                                    "url": item.get("html_url", "https://github.com/"),
                                    "snippet": item.get("description") or "No description provided.",
                                    "source": "github", "kind": "code", "stars": item.get("stargazers_count", 0)})
                source_status["github"] = "ok"
            except Exception as exc:
                source_status["github"] = f"unavailable: {type(exc).__name__}"

        if "images" in selected:
            try:
                commons_q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": q,
                    "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 320, "format": "json", "origin": "*"})
                data = external_json("https://commons.wikimedia.org/w/api.php?" + commons_q)
                pages = (data.get("query") or {}).get("pages") or {}
                for item in pages.values():
                    info = (item.get("imageinfo") or [{}])[0]
                    results.append({"title": item.get("title", "Image"), "url": info.get("descriptionurl", "https://commons.wikimedia.org/"),
                                    "image_url": info.get("thumburl") or info.get("url", ""),
                                    "snippet": "Wikimedia Commons media file. Check the file page for licensing and attribution.",
                                    "source": "wikimedia_commons", "kind": "image"})
                source_status["images"] = "ok"
            except Exception as exc:
                source_status["images"] = f"unavailable: {type(exc).__name__}"

    if q and "news" in selected:
        try:
            data = news_search(q, limit)
            results.extend(data.get("results", []))
            source_status["news"] = "ok"
        except Exception as exc:
            source_status["news"] = f"unavailable: {type(exc).__name__}"

    if q and "research" in selected:
        try:
            data = research_search(q, limit)
            results.extend(data.get("results", []))
            source_status["research"] = "ok"
        except Exception as exc:
            source_status["research"] = f"unavailable: {type(exc).__name__}"

    return {"query": q, "count": len(results), "results": results,
            "sources": sorted(selected), "source_status": source_status,
            "note": "External sources may be rate-limited or temporarily unavailable. Verify facts and image licenses at the original source."}


def get_stats(db_path: Path) -> dict[str, Any]:
    with db_connect(db_path) as conn:
        pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        domains = conn.execute("SELECT COUNT(DISTINCT domain) FROM pages").fetchone()[0]
        seeds = conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
        last = conn.execute("SELECT MAX(fetched_at) FROM pages").fetchone()[0]
        recent = [dict(r) for r in conn.execute(
            "SELECT timestamp, url, result, detail FROM crawl_log ORDER BY id DESC LIMIT 10"
        )]
    return {"indexed_pages": pages, "indexed_domains": domains, "seed_urls": seeds,
            "last_indexed_at": last, "recent_crawl_events": recent}


INDEX_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#090d18"><title>Orbit Search — Your Search, Your Server</title><style>
:root{color-scheme:dark;--bg:#090d18;--panel:#111827;--line:#273449;--text:#f4f7ff;--muted:#9baac2;--accent:#9eabff;--mint:#71e0c1}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% -20%,#25345c 0,transparent 55%),var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}.wrap{max-width:1100px;margin:auto;padding:28px 22px 60px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:55px}.brand{font-weight:800;font-size:18px;display:flex;gap:10px;align-items:center}.orb{display:grid;place-items:center;width:36px;height:36px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--mint));color:#07101c;font-size:20px}.badge,.chip{border:1px solid var(--line);border-radius:99px;padding:5px 10px;color:var(--muted);font-size:12px}.hero{text-align:center;max-width:820px;margin:auto}.eyebrow{color:var(--mint);font-size:12px;text-transform:uppercase;letter-spacing:2px;font-weight:800}.hero h1{font-size:clamp(38px,7vw,66px);line-height:1.04;letter-spacing:-2px;margin:15px 0}.hero h1 span{background:linear-gradient(100deg,#fff,var(--accent),var(--mint));-webkit-background-clip:text;background-clip:text;color:transparent}.hero p{color:var(--muted);max-width:590px;margin:auto}.searchbox{margin:28px auto 15px;max-width:790px;background:#111827;border:1px solid #34425c;border-radius:18px;padding:8px;display:flex;gap:8px;box-shadow:0 22px 80px #0006}.searchbox input{flex:1;min-width:0;background:transparent;border:0;outline:0;color:var(--text);font-size:16px;padding:13px}.searchbox button{border:0;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--mint));color:#07101c;font-weight:800;padding:0 22px;cursor:pointer}.tabs{display:flex;justify-content:center;flex-wrap:wrap;gap:8px;margin:20px auto 25px}.tab{border:1px solid var(--line);background:#111827;color:#b6c2d7;border-radius:99px;padding:8px 13px;cursor:pointer}.tab.active{background:#dfe5ff;color:#0a1020;font-weight:750}.layout{display:grid;grid-template-columns:minmax(0,1fr) 255px;gap:18px;align-items:start}.panel{background:#101725e8;border:1px solid var(--line);border-radius:18px;padding:18px}.panelhead{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:4px}.panelhead h2{font-size:15px;margin:0}.muted,#status{color:var(--muted);font-size:12px}.result{padding:17px 0;border-bottom:1px solid #202d40}.result a{color:#b7c5ff;text-decoration:none;font-size:17px;font-weight:650}.result a:hover{text-decoration:underline}.url{font-size:12px;color:var(--mint);overflow-wrap:anywhere;margin:4px 0}.snippet{color:#c3cede;margin:7px 0;overflow-wrap:anywhere}.meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.chip{font-size:11px;padding:2px 7px}.thumb{display:block;max-width:100%;max-height:210px;border-radius:10px;margin:10px 0;object-fit:contain}.empty{padding:36px 8px;text-align:center;color:var(--muted)}.answer{white-space:pre-wrap;color:#e1e8f6;line-height:1.7}.statgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.stat{background:#172033;border-radius:12px;padding:12px}.stat strong{display:block;font-size:22px}.stat span,.side p{font-size:11px;color:var(--muted)}.side h3{font-size:14px;margin:0 0 12px}.sideblock{padding:15px 0;border-bottom:1px solid var(--line)}.sideblock:last-child{border:0}.side p{font-size:12px;margin:7px 0}.side code{color:#b9c5ff;font-size:11px;overflow-wrap:anywhere}.side button{background:#1d2b43;border:1px solid #34425c;color:#e8edff;border-radius:9px;padding:8px 10px;cursor:pointer;font-size:12px}.foot{text-align:center;color:#687891;font-size:12px;margin-top:35px}@media(max-width:760px){.wrap{padding:18px 13px 40px}.top{margin-bottom:40px}.layout{grid-template-columns:1fr}.hero h1{letter-spacing:-1px}.searchbox input{padding:10px 8px}.searchbox button{padding:0 14px}.panel{padding:14px}}
</style></head><body><div class="wrap"><header class="top"><div class="brand"><span class="orb">✦</span> Orbit Search <span class="badge">SELF-HOSTED</span></div><span class="badge" id="connection">Connecting…</span></header><section class="hero"><div class="eyebrow">Search beyond the obvious</div><h1>Your curiosity.<br><span>Your own search engine.</span></h1><p>Search your local web index, discover books and code, explore images and research, or ask AI to explain what you find.</p></section><form class="searchbox" id="searchForm"><input id="q" placeholder="Try ‘how do stars shine?’" autocomplete="off" autofocus><button id="go" type="submit">Search ↗</button></form><nav class="tabs" id="tabs"><button class="tab active" data-mode="all">✦ All</button><button class="tab" data-mode="ai">✧ AI answer</button><button class="tab" data-mode="images">▧ Images</button><button class="tab" data-mode="news">◷ News</button><button class="tab" data-mode="research">⌘ Research</button><button class="tab" data-mode="books">▤ Books</button><button class="tab" data-mode="github">⌘ Code</button><button class="tab" data-mode="semantic">◎ Semantic</button><button class="tab" data-mode="web">⌕ My index</button></nav><div class="layout"><main class="panel"><div class="panelhead"><h2 id="resultTitle">Ready when you are</h2><span id="status">Enter a search above</span></div><div id="answer" hidden></div><div id="results"><div class="empty">🔎<br><strong>What do you want to discover?</strong><br>Search discovery sources and your locally indexed pages.</div></div></main><aside class="panel side"><div class="sideblock"><h3>📊 Your local index</h3><div class="statgrid"><div class="stat"><strong id="pages">—</strong><span>Pages indexed</span></div><div class="stat"><strong id="domains">—</strong><span>Domains</span></div><div class="stat"><strong id="seeds">—</strong><span>Seed URLs</span></div><div class="stat"><strong id="last">—</strong><span>Last indexed</span></div></div><p>Your local index grows as you crawl permitted public pages.</p><button id="refreshStats">↻ Refresh stats</button></div><div class="sideblock"><h3>🧰 Build your index</h3><p>Run a small crawl from the project folder:</p><code>python3 search_engine.py crawl --file sites_top2000.txt --max-pages 50 --max-per-domain 2 --delay 1.5</code><p>Increase limits gradually.</p></div><div class="sideblock"><h3>📄 Your PDFs</h3><p>Install optional packages:</p><code>python3 -m pip install -r requirements-advanced.txt</code><p>Then run <code>python3 search_engine.py index-pdf "/path/to/file.pdf"</code>.</p></div><div class="sideblock"><h3>🔐 Local by default</h3><p>External discovery needs internet; AI generation needs a configured model. Keep the server local unless you add authentication and rate limits.</p></div></aside></div><footer class="foot">Orbit Search · Built to run on your machine · External results retain original providers and terms.</footer></div><script>
const $=id=>document.getElementById(id);let mode='all',lastQuery='';const src={all:'web,wikipedia,books,github,images,news,research',images:'images',news:'news',research:'research',books:'books',github:'github',web:'web'};function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function setMode(m){mode=m;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===m));if(lastQuery)runSearch(lastQuery)}document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));function render(items){const box=$('results');box.innerHTML='';if(!items||!items.length){box.innerHTML='<div class="empty">No results returned.<br><span class="muted">A provider may be unavailable, or your local index may not have matching pages yet.</span></div>';return}for(const x of items){const el=document.createElement('article');el.className='result';let url=x.url||'#';el.innerHTML=`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.title||url)}</a><div class="url">${esc(url)}</div>${x.image_url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer"><img class="thumb" loading="lazy" src="${esc(x.image_url)}" alt="${esc(x.title||'Search result image')}"></a>`:''}<p class="snippet">${esc(x.snippet||x.description||'Open the source for details.')}</p><div class="meta"><span class="chip">${esc(String(x.source||x.kind||'local result').replaceAll('_',' '))}</span>${x.stars!==undefined?`<span class="chip">★ ${esc(x.stars)}</span>`:''}${x.indexed_at?`<span class="chip">Indexed ${esc(x.indexed_at.slice(0,10))}</span>`:''}</div>`;box.appendChild(el)}}async function runSearch(q){lastQuery=q;$('q').value=q;$('go').disabled=true;$('status').textContent='Searching…';$('resultTitle').textContent=`Results for “${q}”`;$('answer').hidden=true;$('answer').innerHTML='';$('results').innerHTML='<div class="empty">Searching sources…</div>';try{let r,d;if(mode==='ai'){r=await fetch('/api/answer?q='+encodeURIComponent(q));d=await r.json();if(!r.ok)throw Error(d.error||'AI endpoint failed');$('answer').hidden=false;$('answer').innerHTML='<h3>✧ AI answer</h3><div class="answer">'+esc(d.answer||d.text||'No answer was returned.')+'</div>'+(d.model?'<p class="muted">Model: '+esc(d.model)+'</p>':'');render(d.sources||d.results||[]);$('resultTitle').textContent='AI answer & sources';$('status').textContent=(d.mode||'answer')+' · '+((d.sources||d.results||[]).length)+' sources'}else if(mode==='semantic'){r=await fetch('/api/semantic-search?q='+encodeURIComponent(q));d=await r.json();if(!r.ok)throw Error(d.error||'Semantic search failed');render(d.results);$('status').textContent=(d.mode||'semantic')+' · '+(d.count||0)+' results'}else{r=await fetch('/api/multi-search?q='+encodeURIComponent(q)+'&sources='+encodeURIComponent(src[mode]));d=await r.json();if(!r.ok)throw Error(d.error||'Search failed');render(d.results);$('status').textContent=(d.count||0)+' results · '+Object.entries(d.source_status||{}).map(([k,v])=>k+': '+v).join(' · ');if(mode==='all')$('resultTitle').textContent='Search results'}}catch(e){$('results').innerHTML='<div class="empty">⚠️ '+esc(e.message)+'<br><span class="muted">Check the server and internet connection.</span></div>';$('status').textContent='Search error'}finally{$('go').disabled=false}}$('searchForm').addEventListener('submit',e=>{e.preventDefault();let q=$('q').value.trim();if(q)runSearch(q)});async function refreshStats(){try{let r=await fetch('/api/stats'),d=await r.json();$('pages').textContent=Number(d.indexed_pages||0).toLocaleString();$('domains').textContent=Number(d.indexed_domains||0).toLocaleString();$('seeds').textContent=Number(d.seed_urls||0).toLocaleString();$('last').textContent=d.last_indexed_at?d.last_indexed_at.slice(0,10):'Never';$('connection').textContent='● API connected';$('connection').style.color='#71e0c1'}catch(e){$('connection').textContent='API offline';$('connection').style.color='#ff9d9d'}}$('refreshStats').addEventListener('click',refreshStats);refreshStats();</script></body></html>"""


class APIHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep standard server logging but avoid dumping potentially sensitive search queries.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path in ("/", "/index.html"):
            raw = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/search":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            site = params.get("site", [None])[0]
            try:
                limit = int(params.get("limit", ["10"])[0])
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, 400)
                return
            try:
                self.send_json(search_pages(self.db_path, q, limit, site))
            except sqlite3.OperationalError:
                self.send_json({"error": "Search index unavailable; initialize the database first."}, 500)
            return
        if parsed.path == "/api/multi-search":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            try:
                limit = int(params.get("limit", ["8"])[0])
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, 400)
                return
            requested = params.get("sources", ["web,wikipedia,books,github,images,news,research"])[0]
            sources = [name.strip().lower() for name in requested.split(",") if name.strip()]
            self.send_json(multi_source_search(self.db_path, q, limit, sources))
            return
        if parsed.path in ("/api/news", "/api/research"):
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            try:
                limit = int(params.get("limit", ["8"])[0])
                data = news_search(q, limit) if parsed.path == "/api/news" else research_search(q, limit)
                self.send_json(data)
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, 400)
            except Exception as exc:
                self.send_json({"error": "External source unavailable", "detail": type(exc).__name__}, 502)
            return
        if parsed.path == "/api/semantic-search":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            try:
                self.send_json(semantic_search(self.db_path, q, int(params.get("limit", ["10"])[0])))
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, 400)
            except Exception as exc:
                self.send_json({"error": "Semantic search failed", "detail": type(exc).__name__}, 500)
            return
        if parsed.path == "/api/answer":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            try:
                gathered = multi_source_search(self.db_path, q, 8,
                    ["web", "wikipedia", "books", "github", "research"])
                self.send_json(ai_answer(q, gathered.get("results", [])))
            except Exception as exc:
                self.send_json({"error": "Answer generation failed", "detail": type(exc).__name__}, 502)
            return
        if parsed.path == "/api/url-check":
            params = urllib.parse.parse_qs(parsed.query)
            url = params.get("url", [""])[0]
            try:
                self.send_json(url_safety_check(url))
            except Exception as exc:
                self.send_json({"error": "URL safety provider unavailable", "detail": type(exc).__name__}, 502)
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "Orbit Search", "version": "3.0.0"})
            return
        if parsed.path == "/api/stats":
            self.send_json(get_stats(self.db_path))
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/crawl":
            self.send_json({"error": "Not found"}, 404)
            return
        # API crawling is intentionally disabled to keep crawl jobs explicit in the CLI.
        self.send_json({
            "error": "Remote crawl control is disabled. Run the crawler locally from the CLI.",
            "command": "python3 search_engine.py crawl --max-pages 100 --max-per-domain 5"
        }, 403)


def load_seeds(crawler: PublicCrawler, seed_arg: str | None) -> int:
    file = Path(seed_arg).expanduser() if seed_arg else DEFAULT_SEEDS
    return crawler.add_seeds_file(file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-hosted public web crawler and search API")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize the local database")
    add_parser = sub.add_parser("add-seeds", help="Import allowed starting URLs/domains from a text file")
    add_parser.add_argument("--file", help="Seed file path (defaults to sites.txt)")
    crawl_parser = sub.add_parser("crawl", help="Crawl and index public pages permitted by robots.txt")
    crawl_parser.add_argument("--file", help="Seed file to import before crawl (defaults to sites.txt)")
    crawl_parser.add_argument("--max-pages", type=int, default=100, help="Maximum URLs considered per run")
    crawl_parser.add_argument("--max-per-domain", type=int, default=5, help="Maximum pages indexed per host per run")
    crawl_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Minimum seconds between requests per host (at least 1)")
    pdf_parser = sub.add_parser("index-pdf", help="Index a local PDF into your search database")
    pdf_parser.add_argument("path", help="Path to a PDF file")
    serve_parser = sub.add_parser("serve", help="Start local web UI and REST API")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address; default is local-only")
    serve_parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    serve_parser.add_argument("--share", action="store_true", help="Allow binding beyond localhost (not recommended without a firewall/auth proxy)")

    args = parser.parse_args()
    db_path = Path(args.db).expanduser().resolve()
    db_connect(db_path).close()

    if args.command == "init":
        print(f"Initialized database: {db_path}")
        return 0

    if args.command == "add-seeds":
        crawler = PublicCrawler(db_path)
        try:
            added = load_seeds(crawler, args.file)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"Added {added} new seed URL(s).")
        return 0

    if args.command == "crawl":
        crawler = PublicCrawler(db_path, args.delay, args.max_per_domain, args.max_pages)
        try:
            added = load_seeds(crawler, args.file)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"Added {added} new seed URL(s). Starting crawl...")
        stats = crawler.crawl()
        print(json.dumps(stats, indent=2))
        print(f"Database: {db_path}")
        return 0

    if args.command == "index-pdf":
        try:
            result = index_pdf(db_path, Path(args.path))
        except Exception as exc:
            print(f"PDF indexing failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "serve":
        host = args.host
        if host not in {"127.0.0.1", "::1", "localhost"} and not args.share:
            print("Refusing to bind to a non-local interface without --share.", file=sys.stderr)
            print("Use 127.0.0.1 by default, or explicitly pass --share if you understand the risks.", file=sys.stderr)
            return 2
        handler = type("ConfiguredAPIHandler", (APIHandler,), {"db_path": db_path})
        server = ThreadingHTTPServer((host, args.port), handler)
        print(f"Search UI: http://{host}:{args.port}/")
        print(f"Search API: http://{host}:{args.port}/api/search?q=example")
        print(f"Multi-source API: http://{host}:{args.port}/api/multi-search?q=python")
        print(f"Stats API:  http://{host}:{args.port}/api/stats")
        print(f"AI answer API: http://{host}:{args.port}/api/answer?q=example")
        print(f"Semantic API:  http://{host}:{args.port}/api/semantic-search?q=example")
        print(f"Database: {db_path}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server.")
        finally:
            server.server_close()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
