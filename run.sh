#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PORT="${1:-8071}"
python3 search_engine.py init
exec python3 search_engine.py serve --port "$PORT"
