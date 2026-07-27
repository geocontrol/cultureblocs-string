"""Index storage: public records seen on the network, and who points at what.

Everything here is derived from public ATProto records. The AppView holds
no private data and no accounts: it is a lens over what people have
already chosen to publish.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    uri        TEXT PRIMARY KEY,
    did        TEXT NOT NULL,
    collection TEXT NOT NULL,
    rkey       TEXT NOT NULL,
    cid        TEXT,
    created_at TEXT,
    indexed_at TEXT NOT NULL,
    body       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_did  ON records(did, collection);
CREATE INDEX IF NOT EXISTS idx_records_coll ON records(collection, created_at DESC);

CREATE TABLE IF NOT EXISTS refs (
    src_uri  TEXT NOT NULL,
    src_did  TEXT NOT NULL,
    src_coll TEXT NOT NULL,
    dst_uri  TEXT NOT NULL,
    dst_did  TEXT,
    cid      TEXT,
    PRIMARY KEY (src_uri, dst_uri)
);
CREATE INDEX IF NOT EXISTS idx_refs_dst ON refs(dst_uri);
CREATE INDEX IF NOT EXISTS idx_refs_did ON refs(dst_did);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def uri_parts(uri: str) -> tuple[str, str, str]:
    """at://did/collection/rkey -> (did, collection, rkey)"""
    rest = uri[5:] if uri.startswith("at://") else uri
    bits = rest.split("/")
    while len(bits) < 3:
        bits.append("")
    return bits[0], bits[1], bits[2]


def find_refs(node, out: list[dict]) -> None:
    """Any {'uri': 'at://…'} object anywhere in a record is a reference.

    Deliberately structural rather than field-by-field: a bead's subject,
    a strand's items, a connection's subject, a listing's venue or event
    all use the same strongRef shape, and so will fields not yet invented.
    """
    if isinstance(node, dict):
        u = node.get("uri")
        if isinstance(u, str) and u.startswith("at://"):
            out.append({"uri": u, "cid": node.get("cid")})
        for v in node.values():
            find_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            find_refs(v, out)


class Index:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    # -- writes ----------------------------------------------------------
    def put(self, uri: str, cid: str | None, body: dict, indexed_at: str) -> None:
        did, coll, rkey = uri_parts(uri)
        with self.conn:
            self.conn.execute(
                "INSERT INTO records (uri,did,collection,rkey,cid,created_at,indexed_at,body) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(uri) DO UPDATE SET "
                "cid=excluded.cid, created_at=excluded.created_at, "
                "indexed_at=excluded.indexed_at, body=excluded.body",
                (uri, did, coll, rkey, cid, body.get("createdAt"), indexed_at,
                 json.dumps(body)))
            self.conn.execute("DELETE FROM refs WHERE src_uri=?", (uri,))
            found: list[dict] = []
            find_refs(body, found)
            for r in found:
                ddid, _, _ = uri_parts(r["uri"])
                self.conn.execute(
                    "INSERT OR REPLACE INTO refs (src_uri,src_did,src_coll,dst_uri,dst_did,cid) "
                    "VALUES (?,?,?,?,?,?)",
                    (uri, did, coll, r["uri"], ddid, r.get("cid")))

    def delete(self, uri: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM records WHERE uri=?", (uri,))
            self.conn.execute("DELETE FROM refs WHERE src_uri=?", (uri,))

    def set_cursor(self, cursor: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta (k,v) VALUES ('cursor',?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(cursor),))

    def cursor(self) -> str | None:
        row = self.conn.execute("SELECT v FROM meta WHERE k='cursor'").fetchone()
        return row["v"] if row else None

    # -- reads -----------------------------------------------------------
    @staticmethod
    def _rec(row: sqlite3.Row) -> dict:
        return {"uri": row["uri"], "did": row["did"], "collection": row["collection"],
                "cid": row["cid"], "createdAt": row["created_at"],
                "value": json.loads(row["body"])}

    def get(self, uri: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM records WHERE uri=?", (uri,)).fetchone()
        return self._rec(row) if row else None

    def records(self, collection: str | None = None, did: str | None = None,
                limit: int = 50) -> list[dict]:
        q = "SELECT * FROM records WHERE 1=1"
        args: list = []
        if collection:
            q += " AND collection=?"
            args.append(collection)
        if did:
            q += " AND did=?"
            args.append(did)
        q += " ORDER BY COALESCE(created_at, indexed_at) DESC LIMIT ?"
        args.append(min(limit, 200))
        return [self._rec(r) for r in self.conn.execute(q, args)]

    def referrers(self, uri: str, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT r.*, rec.body, rec.created_at FROM refs r "
            "LEFT JOIN records rec ON rec.uri = r.src_uri "
            "WHERE r.dst_uri=? LIMIT ?", (uri, limit)).fetchall()
        out = []
        for r in rows:
            out.append({"uri": r["src_uri"], "did": r["src_did"],
                        "collection": r["src_coll"], "createdAt": r["created_at"],
                        "value": json.loads(r["body"]) if r["body"] else None})
        return out

    def reference_count(self, uri: str) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT src_did) people FROM refs WHERE dst_uri=?",
            (uri,)).fetchone()
        return {"references": row["n"], "publishers": row["people"]}

    def reciprocal(self, did_a: str, did_b: str) -> bool:
        """Does each party point at the other? The closed loop that lets a
        reader compute a verified relationship without anyone approving it."""
        a2b = self.conn.execute(
            "SELECT 1 FROM refs WHERE src_did=? AND dst_did=? LIMIT 1",
            (did_a, did_b)).fetchone()
        b2a = self.conn.execute(
            "SELECT 1 FROM refs WHERE src_did=? AND dst_did=? LIMIT 1",
            (did_b, did_a)).fetchone()
        return bool(a2b and b2a)

    def stats(self) -> dict:
        by_coll = {r["collection"]: r["n"] for r in self.conn.execute(
            "SELECT collection, COUNT(*) n FROM records GROUP BY collection")}
        tot = self.conn.execute(
            "SELECT COUNT(*) n, COUNT(DISTINCT did) d FROM records").fetchone()
        refs = self.conn.execute("SELECT COUNT(*) n FROM refs").fetchone()["n"]
        return {"records": tot["n"], "publishers": tot["d"],
                "references": refs, "byCollection": by_coll}
