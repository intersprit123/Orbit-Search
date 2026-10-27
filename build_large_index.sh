#!/usr/bin/env bash
# Create a 6,000-domain seed list and start a conservative first indexing pass.
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/4] Downloading the current top 6,000 domains into sites_top6000.txt..."
python3 import_top_domains.py --count 6000 --output sites_top6000.txt

echo "[2/4] Adding curated science, education, reference, and developer sites..."
cat sites_curated.txt >> sites_top6000.txt

echo "[3/4] Initializing the local index (existing database is retained)..."
python3 search_engine.py init

echo "[4/4] Crawling up to 300 URLs in this pass, at a polite delay..."
python3 search_engine.py crawl --file sites_top6000.txt --max-pages 300 --max-per-domain 2 --delay 1.5

echo
echo "First pass finished. Check: http://127.0.0.1:8071/api/stats"
echo "To grow the index further, repeat with a larger page budget, for example:"
echo "  python3 search_engine.py crawl --file sites_top6000.txt --max-pages 1000 --max-per-domain 2 --delay 1.5"
echo "This seed list contains domains, not 6,000 already-indexed websites. Pages are added only when fetching succeeds and robots.txt permits crawling."
