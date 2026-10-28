#!/usr/bin/env python3
"""Shared resilience primitives for Orbit's public JSON API adapters.

This module provides a small bounded TTL cache and privacy-conscious provider
telemetry. It never exposes request URLs or query strings in metrics.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

USER_AGENT = "OrbitSearch/1.1 (+https://github.com/intersprit123/Orbit-Search)"
MAX_RESPONSE_BYTES = 4_000_000


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(os.getenv(name, str(default))), high))
    except (TypeError, ValueError):
        return default


CACHE_TTL_SECONDS = _env_int("ORBIT_API_CACHE_TTL", 30, 0, 300)
CACHE_MAX_ENTRIES = _env_int("ORBIT_API_CACHE_MAX_ENTRIES", 512, 16, 2048)
_STARTED = time.monotonic()
_LOCK = threading.RLock()
_CACHE: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_METRICS: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "unknown").lower()[:253]
    except ValueError:
        return "unknown"


def _stats(host: str) -> dict[str, Any]:
    return _METRICS.setdefault(host, {
        "requests": 0,
        "cache_hits": 0,
        "failures": 0,
        "total_latency_ms": 0.0,
        "last_success_at": None,
        "last_error_at": None,
        "last_error": None,
        "last_outcome": "unknown",
    })


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 12,
    max_bytes: int = MAX_RESPONSE_BYTES,
    cache_ttl: int | None = None,
) -> Any:
    """Fetch public JSON with bounded caching and aggregate host-level metrics.

    Cache keys include the URL and representation headers, but metrics expose
    hostnames only (never paths, query strings, or user-supplied search terms).
    Failed responses are never cached.
    """
    host = _host(url)
    ttl = CACHE_TTL_SECONDS if cache_ttl is None else max(0, min(int(cache_ttl), 300))
    accept = (headers or {}).get("Accept", "application/json")
    cache_key = accept + "\n" + url
    now = time.monotonic()

    if ttl:
        with _LOCK:
            cached = _CACHE.get(cache_key)
            if cached is not None:
                expires, value = cached
                if expires > now:
                    _CACHE.move_to_end(cache_key)
                    stats = _stats(host)
                    stats["requests"] += 1
                    stats["cache_hits"] += 1
                    stats["last_outcome"] = "cached"
                    return copy.deepcopy(value)
                _CACHE.pop(cache_key, None)

    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Provider response exceeded the configured size limit.")
        payload = json.loads(raw.decode("utf-8", "replace"))
    except Exception as exc:
        elapsed = (time.monotonic() - started) * 1000
        with _LOCK:
            stats = _stats(host)
            stats["requests"] += 1
            stats["failures"] += 1
            stats["total_latency_ms"] += elapsed
            stats["last_error_at"] = _now_iso()
            stats["last_error"] = type(exc).__name__
            stats["last_outcome"] = "error"
        raise

    elapsed = (time.monotonic() - started) * 1000
    with _LOCK:
        stats = _stats(host)
        stats["requests"] += 1
        stats["total_latency_ms"] += elapsed
        stats["last_success_at"] = _now_iso()
        stats["last_error"] = None
        stats["last_outcome"] = "success"
        if ttl:
            _CACHE[cache_key] = (time.monotonic() + ttl, copy.deepcopy(payload))
            _CACHE.move_to_end(cache_key)
            while len(_CACHE) > CACHE_MAX_ENTRIES:
                _CACHE.popitem(last=False)
    return payload


def metrics_snapshot() -> dict[str, Any]:
    """Return safe, aggregate diagnostics; never returns URLs or query strings."""
    with _LOCK:
        providers: dict[str, Any] = {}
        for host, raw in sorted(_METRICS.items()):
            item = dict(raw)
            measured = max(0, item["requests"] - item["cache_hits"])
            item["average_network_latency_ms"] = round(
                item["total_latency_ms"] / measured, 2
            ) if measured else 0
            item.pop("total_latency_ms", None)
            item["status"] = (
                "degraded" if item["last_outcome"] == "error"
                else "healthy" if item["last_outcome"] in {"success", "cached"}
                else "unknown"
            )
            providers[host] = item
        return {
            "ok": True,
            "service": "Orbit API resilience metrics",
            "uptime_seconds": round(time.monotonic() - _STARTED, 2),
            "cache": {
                "enabled": CACHE_TTL_SECONDS > 0,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "max_entries": CACHE_MAX_ENTRIES,
                "entries": len(_CACHE),
            },
            "provider_metrics_are_passive": True,
            "provider_metrics_note": "Unknown means Orbit has not contacted that host since startup; this endpoint does not actively probe providers.",
            "providers": providers,
        }


def clear_cache() -> None:
    """Clear cached responses; intended for tests and local maintenance."""
    with _LOCK:
        _CACHE.clear()
