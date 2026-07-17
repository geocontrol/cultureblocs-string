#!/usr/bin/env python3
"""One-shot migration: org.artmosphere.* -> com.cultureblocs.* in an existing
Spine database. Rewrites the `type` column and every occurrence inside record
bodies (the $type field and any lexicon refs), in both `records` and the
`changes` log. Dedupe keys, ids, timestamps and revisions are untouched.

Run with the stack STOPPED (or at least nothing writing):

    docker compose stop spine
    python scripts/migrate_to_cultureblocs.py data/spine.db
    docker compose up -d --build

Safe to re-run: a second pass finds nothing to change. A timestamped backup
copy of the database is written next to it before any change.
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

OLD, NEW = "org.artmosphere", "com.cultureblocs"


def main(db_path: str) -> None:
    p = Path(db_path)
    if not p.exists():
        sys.exit(f"no database at {p}")
    backup = p.with_name(f"{p.stem}.pre-cultureblocs-{int(time.time())}{p.suffix}")
    shutil.copy2(p, backup)
    print(f"backup: {backup}")

    conn = sqlite3.connect(p)
    with conn:
        n1 = conn.execute(
            "UPDATE records SET type = replace(type, ?, ?), "
            "body = replace(body, ?, ?) WHERE type LIKE ? OR body LIKE ?",
            (OLD, NEW, OLD, NEW, f"%{OLD}%", f"%{OLD}%")).rowcount
        n2 = conn.execute(
            "UPDATE changes SET body = replace(body, ?, ?) WHERE body LIKE ?",
            (OLD, NEW, f"%{OLD}%")).rowcount
    conn.execute("VACUUM")
    conn.close()
    print(f"migrated: {n1} records, {n2} change-log entries")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/spine.db")
