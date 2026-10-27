#!/usr/bin/env python3
"""
Import the top N domains from the public Tranco ranking into a seed file.

This retrieves a ranked domain list, not search results. It makes no requests
to the domains themselves. The search crawler later visits only pages allowed
by each host's robots.txt and obeys the crawler's rate limits.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://tranco-list.eu/top-1m.csv.zip"
USER_AGENT = "OurOwnSearchDomainListImporter/1.0 (educational self-hosted search project)"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024


def is_domain(value: str) -> bool:
    """Validate a normal DNS hostname; skip malformed list entries."""
    value = value.strip().lower().rstrip(".")
    if not value or len(value) > 253 or "." not in value:
        return False
    try:
        ascii_name = value.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_name.split(".")
    if any(not label or len(label) > 63 for label in labels):
        return False
    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
    return all(label_pattern.fullmatch(label) for label in labels)


def download_ranking(source_url: str) -> bytes:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip,application/octet-stream,*/*"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("Ranking download exceeded the 80 MB safety limit.")
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise RuntimeError("Download was not a ZIP file. The ranking source may have changed.")
    return content


def parse_top_domains(zipped_bytes: bytes, count: int) -> list[tuple[int, str]]:
    with zipfile.ZipFile(io.BytesIO(zipped_bytes)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError("No CSV file was found inside the downloaded ranking ZIP.")
        # Official export is normally top-1m.csv.
        preferred = next((n for n in names if Path(n).name.lower() == "top-1m.csv"), names[0])
        with archive.open(preferred) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.reader(text)
            ranked: list[tuple[int, str]] = []
            seen: set[str] = set()
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    rank = int(row[0].strip())
                except (ValueError, TypeError):
                    continue
                domain = row[1].strip().lower().rstrip(".")
                if rank < 1 or not is_domain(domain) or domain in seen:
                    continue
                seen.add(domain)
                ranked.append((rank, domain))
                if len(ranked) >= count:
                    break
    if len(ranked) < count:
        raise RuntimeError(f"Only {len(ranked)} valid unique domains were found; wanted {count}.")
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the global Tranco ranking and write the top N domains as crawler seeds."
    )
    parser.add_argument("--count", type=int, default=2000, help="Number of top domains to import (default: 2000)")
    parser.add_argument("--output", default="sites_top2000.txt", help="Output seed-file path (default: sites_top2000.txt)")
    parser.add_argument("--source", default=SOURCE_URL, help="Ranking ZIP URL; defaults to Tranco's current top-1M export")
    args = parser.parse_args()

    if not 1 <= args.count <= 100_000:
        parser.error("--count must be between 1 and 100000.")
    out = Path(args.output).expanduser().resolve()

    print(f"Downloading public domain ranking from: {args.source}")
    print(f"Selecting the first {args.count:,} valid unique domains...")
    try:
        blob = download_ranking(args.source)
        ranked = parse_top_domains(blob, args.count)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        print("Check your internet connection and try again. No seed file has been written.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".tmp")
    generated_at = datetime.now(timezone.utc).isoformat()
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top domains imported from Tranco's public global ranking.\n")
        handle.write(f"# Source: {args.source}\n")
        handle.write(f"# Generated locally at UTC: {generated_at}\n")
        handle.write("# Ranking list is dynamic; rerun this script to refresh it.\n")
        handle.write("# Each line below is a starting URL for the local crawler.\n")
        for rank, domain in ranked:
            handle.write(f"https://{domain}/\n")
    temp.replace(out)

    print(f"\nSuccess: wrote {len(ranked):,} domains to:")
    print(out)
    print(f"First domain:  #{ranked[0][0]} {ranked[0][1]}")
    print(f"Last domain:   #{ranked[-1][0]} {ranked[-1][1]}")
    print("\nThis only imports seed URLs. It does not crawl them yet.")
    print("Next, start cautiously, e.g.:")
    print(f"  python3 search_engine.py crawl --file {out} --max-pages 50 --max-per-domain 2 --delay 1.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
