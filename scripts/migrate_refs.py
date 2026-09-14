#!/usr/bin/env python3
"""One-shot migration: give existing annotations a subject ref for their `work`.

New writes are mirrored at ingest (string/app/refs.py); this backfills
records written before refs existed. Beads need nothing: no bead carries
a #workRef subject, and the undeclared `bead.work` field is simply no
longer published.

Run with the stack STOPPED (or at least nothing writing):

    docker compose stop string
    python scripts/migrate_refs.py data/string.db
    docker compose up -d --build

Safe to re-run: a second pass finds nothing to change. A timestamped backup
copy of the database is written next to it before any change.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "string"))
from app.db import Store  # noqa: E402
from app.refs import ANNOTATION, mirror_annotation_work  # noqa: E402


def migrate(store: Store) -> int:
    """Mirror `work` into `refs` on every annotation that lacks it. Returns the count changed."""
    changed = 0
    for rec in store.query(rtype=ANNOTATION, limit=1_000_000):
        mirrored = mirror_annotation_work(ANNOTATION, rec["body"])
        if mirrored is not rec["body"]:
            store.patch(rec["id"], {"refs": mirrored["refs"]})
            changed += 1
    return changed


def backup_database(source: Path, target: Path) -> None:
    """Copy a live SQLite database, including writes still in its WAL.

    Copying the .db file alone is not a backup: the String runs in WAL mode,
    and until a checkpoint the newest records exist only in the -wal file.
    SQLite's online backup API reads through the WAL and yields one
    self-contained file.
    """
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def main(db_path: str) -> None:
    p = Path(db_path)
    if not p.exists():
        sys.exit(f"no database at {p}")
    backup = p.with_name(f"{p.stem}.pre-refs-{int(time.time())}{p.suffix}")
    backup_database(p, backup)
    print(f"backup: {backup}")
    print(f"annotations given a subject ref: {migrate(Store(str(p)))}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: migrate_refs.py <path/to/string.db>")
    main(sys.argv[1])
