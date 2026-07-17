"""SQLite (WAL) persistence for the Spine.

Two tables:
  records — current state, one row per record, deduped on dedupe_key
  changes — append-only log of every mutation (the upgrade path to
            CRDT/PDS promotion later: consumers read this with a cursor)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id          TEXT PRIMARY KEY,
    dedupe_key  TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL,
    tier        INTEGER NOT NULL DEFAULT 0,
    source_app  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    revision    INTEGER NOT NULL DEFAULT 1,
    published_uri TEXT,
    published_hash TEXT,
    body        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);

CREATE TABLE IF NOT EXISTS changes (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  TEXT NOT NULL,
    op         TEXT NOT NULL,          -- create | update
    at         TEXT NOT NULL,
    body       TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.row_factory = sqlite3.Row

    # -- writes ----------------------------------------------------------
    def upsert(self, dedupe_key: str, rtype: str, source_app: str,
               created_at: str, body: dict, tier: int = 0) -> tuple[str, str]:
        """Insert if new; no-op if dedupe_key exists. Returns (id, status)."""
        cur = self.conn.execute(
            "SELECT id FROM records WHERE dedupe_key = ?", (dedupe_key,))
        row = cur.fetchone()
        if row:
            return row["id"], "duplicate"
        rid = str(uuid.uuid4())
        payload = json.dumps(body, separators=(",", ":"))
        with self.conn:
            self.conn.execute(
                "INSERT INTO records (id, dedupe_key, type, tier, source_app,"
                " created_at, ingested_at, body) VALUES (?,?,?,?,?,?,?,?)",
                (rid, dedupe_key, rtype, tier, source_app,
                 created_at, now_iso(), payload))
            self.conn.execute(
                "INSERT INTO changes (record_id, op, at, body) VALUES (?,?,?,?)",
                (rid, "create", now_iso(), payload))
        return rid, "created"

    def patch(self, rid: str, fields: dict) -> dict | None:
        """Shallow-merge fields into body, bump revision. Last-writer-wins."""
        cur = self.conn.execute("SELECT body, revision FROM records WHERE id=?", (rid,))
        row = cur.fetchone()
        if row is None:
            return None
        body = json.loads(row["body"])
        body.update(fields)
        payload = json.dumps(body, separators=(",", ":"))
        with self.conn:
            self.conn.execute(
                "UPDATE records SET body=?, revision=revision+1 WHERE id=?",
                (payload, rid))
            self.conn.execute(
                "INSERT INTO changes (record_id, op, at, body) VALUES (?,?,?,?)",
                (rid, "update", now_iso(), payload))
        return self.get(rid)

    def delete(self, rid: str) -> bool:
        cur = self.conn.execute("SELECT body FROM records WHERE id=?", (rid,))
        row = cur.fetchone()
        if row is None:
            return False
        with self.conn:
            self.conn.execute("DELETE FROM records WHERE id=?", (rid,))
            self.conn.execute(
                "INSERT INTO changes (record_id, op, at, body) VALUES (?,?,?,?)",
                (rid, "delete", now_iso(), row["body"]))
        return True

    # -- reads -----------------------------------------------------------
    def get(self, rid: str) -> dict | None:
        cur = self.conn.execute("SELECT * FROM records WHERE id=?", (rid,))
        row = cur.fetchone()
        return self._row(row) if row else None

    def query(self, day: str | None = None, rtype: str | None = None,
              source_app: str | None = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM records WHERE 1=1"
        args: list = []
        if day:
            sql += " AND substr(created_at,1,10)=?"
            args.append(day)
        if rtype:
            sql += " AND type=?"
            args.append(rtype)
        if source_app:
            sql += " AND source_app=?"
            args.append(source_app)
        sql += " ORDER BY created_at ASC LIMIT ?"
        args.append(limit)
        return [self._row(r) for r in self.conn.execute(sql, args)]

    def changes_since(self, since: int, limit: int = 500) -> list[dict]:
        cur = self.conn.execute(
            "SELECT seq, record_id, op, at, body FROM changes WHERE seq>? "
            "ORDER BY seq ASC LIMIT ?", (since, limit))
        return [{"seq": r["seq"], "recordId": r["record_id"], "op": r["op"],
                 "at": r["at"], "body": json.loads(r["body"])} for r in cur]

    def days(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT substr(created_at,1,10) AS day, COUNT(*) AS n "
            "FROM records GROUP BY day ORDER BY day DESC")
        return [{"day": r["day"], "count": r["n"]} for r in cur]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "dedupeKey": row["dedupe_key"],
            "type": row["type"],
            "tier": row["tier"],
            "sourceApp": row["source_app"],
            "createdAt": row["created_at"],
            "ingestedAt": row["ingested_at"],
            "revision": row["revision"],
            "publishedUri": row["published_uri"],
            "body": json.loads(row["body"]),
        }
