#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m py_compile search_engine.py advanced_features.py import_top_domains.py
python3 search_engine.py --help >/dev/null
python3 search_engine.py --db data/test-check.sqlite3 init
python3 - <<'PY'
from pathlib import Path
p=Path("data/test-check.sqlite3")
if p.exists(): p.unlink()
for suffix in ("-wal","-shm"):
    q=Path(str(p)+suffix)
    if q.exists(): q.unlink()
print("Syntax and CLI smoke checks passed.")
PY
