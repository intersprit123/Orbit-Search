#!/usr/bin/env python3
"""Import the previous Orbit/Search API project's local data into this project safely."""
from pathlib import Path
import argparse
import shutil
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
DEFAULT_OLD = Path.home() / "our_own_web_search_api"
TARGET_DB = HERE / "data" / "search.sqlite3"

def page_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            row = db.execute("SELECT COUNT(*) FROM pages").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0

def main():
    parser = argparse.ArgumentParser(description="Import existing database and seed files from your previous project.")
    parser.add_argument("--from-dir", type=Path, default=DEFAULT_OLD,
                        help=f"Old project directory (default: {DEFAULT_OLD})")
    args = parser.parse_args()
    source_dir = args.from_dir.expanduser().resolve()
    source_db = source_dir / "data" / "search.sqlite3"
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)

    print(f"Old project: {source_dir}")
    print(f"New project: {HERE}")
    imported_any = False

    if source_db.exists():
        old_pages = page_count(source_db)
        new_pages = page_count(TARGET_DB)
        print(f"Old database indexed pages: {old_pages}")
        print(f"New database indexed pages: {new_pages}")
        if old_pages and new_pages:
            print("\nBoth databases contain indexed pages, so I will not overwrite or merge them automatically.")
            print("Back up both databases first, then ask for a safe merge workflow.")
            return 2
        if old_pages and not new_pages:
            if TARGET_DB.exists():
                backup = TARGET_DB.with_suffix(".sqlite3.empty-backup")
                shutil.copy2(TARGET_DB, backup)
                print(f"Backed up the empty new database to: {backup}")
            shutil.copy2(source_db, TARGET_DB)
            print(f"Imported database with {old_pages} indexed pages.")
            imported_any = True
        elif not old_pages and not TARGET_DB.exists():
            shutil.copy2(source_db, TARGET_DB)
            print("Copied the old database (it currently contains no indexed pages).")
            imported_any = True
        elif not old_pages and TARGET_DB.exists():
            print("Both databases appear empty; leaving the new database unchanged.")
    else:
        print(f"No old database found at {source_db}")
        print("If your old project is in another location, pass --from-dir /path/to/our_own_web_search_api")

    # Preserve seed lists and other text-based crawl inputs if present.
    for filename in ("sites_top2000.txt", "sites.txt"):
        src = source_dir / filename
        dst = HERE / filename
        if src.exists():
            if dst.exists():
                # Only replace a tiny example/placeholder with a real seed file.
                if dst.stat().st_size > 500:
                    print(f"Keeping existing {dst.name}; source file also exists.")
                    continue
            shutil.copy2(src, dst)
            print(f"Imported {filename} ({src.stat().st_size:,} bytes).")
            imported_any = True

    if imported_any:
        print("\nImport finished. Your old project files and database were not deleted.")
    else:
        print("\nNo new data was imported. Check the old project path and try again.")
    print("Next: run `python3 search_engine.py init`, then start the server.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
