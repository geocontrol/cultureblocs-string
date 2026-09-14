"""SQLite (WAL) persistence for the Spine.

Three tables:
  records    — current state, one row per record, deduped on dedupe_key
  identities — held publishing accounts
  changes    — append-only log of every mutation, carrying an HLC stamp,
               the device that made it and the actor it was made as, so a
               second device can replay the log without echoing its own
               writes back at itself

Two columns carry most of the new meaning:

  records.state  proposal | kept | draft | published | edited
        Explicit, stored, and synced — rather than inferred by each client
        from the producing app's name. A `proposal` is a machine's
        suggestion and may be revised on a later run; anything else is a
        mint fact and stays insert-once. This is the "proposals are not
        facts" rule expressed in the schema instead of in a UI constant.

  records.hlc    the stamp of the last write to this record
        Lets a client say "I am editing the version I last saw" and be told
        when that is no longer true, instead of silently overwriting a note
        another device wrote while it was offline.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .hlc import HLC

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
    state       TEXT NOT NULL DEFAULT 'kept',
    hlc         TEXT,
    published_uri TEXT,
    published_hash TEXT,
    body        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);

CREATE TABLE IF NOT EXISTS identities (
    name         TEXT PRIMARY KEY,
    handle       TEXT NOT NULL,
    app_password TEXT NOT NULL,
    pds          TEXT NOT NULL DEFAULT 'https://bsky.social'
);

CREATE TABLE IF NOT EXISTS changes (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id  TEXT NOT NULL,
    op         TEXT NOT NULL,          -- create | update | delete | state
    at         TEXT NOT NULL,
    hlc        TEXT,
    device_id  TEXT,
    actor      TEXT,
    body       TEXT NOT NULL
);
"""

# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", and CREATE TABLE IF NOT EXISTS silently does nothing on an
# existing table, so new columns have to be applied by hand against
# whatever an already-running String has on disk.
MIGRATIONS = [
    ("records", "state", "TEXT NOT NULL DEFAULT 'kept'"),
    ("records", "hlc", "TEXT"),
    ("changes", "hlc", "TEXT"),
    ("changes", "device_id", "TEXT"),
    ("changes", "actor", "TEXT"),
]

# Producing apps whose beads were proposals before `state` existed. Used once,
# to backfill; after that the column is the truth and this list is history.
# (The timeline carried the same list as a UI constant — that is the thing
# this column exists to retire.)
LEGACY_MACHINE_APPS = ("scrobbler",)

# Bumped when a one-time data migration is added below. Stored in the file as
# PRAGMA user_version, so each migration runs once per database, ever.
SCHEMA_VERSION = 1

STATES = ("proposal", "kept", "draft", "published", "edited")

# Indexes over migrated columns, applied AFTER _migrate(). They cannot live in
# SCHEMA: on a database written before Phase 0 the table exists already, so
# CREATE TABLE IF NOT EXISTS does nothing, and an index over a column that has
# not been added yet fails the whole script — taking the String down on the
# first start after an upgrade.
POST_MIGRATION_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_records_state ON records(state);
CREATE INDEX IF NOT EXISTS idx_changes_hlc ON changes(hlc);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    """The record store.

    Concurrency: one sqlite3 connection is shared by every request thread
    (FastAPI runs sync routes on a threadpool), and several methods read a
    row and then write on the strength of what they read. Every method that
    touches the connection — reads included, since the connection itself
    is not safe to use from two threads at once — runs under `self._lock`,
    one re-entrant lock per Store, so patch() can call get() inside it. The
    HLC serialises its own now()/observe() (see hlc.py); stamps are unique
    whether or not they are taken under this lock.
    """

    def __init__(self, path: str, *, node_id: str | None = None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._lock:
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self.conn.row_factory = sqlite3.Row
            self.hlc = HLC(node_id)
            self._migrate()
            self.conn.executescript(POST_MIGRATION_SCHEMA)
            self._backfill_state()
            self._seed_clock()

    def _seed_clock(self) -> None:
        """Start the clock above the highest stamp already on disk.

        The HLC lives in memory, so without this a restart on a host whose
        wall clock is behind its last write (NTP correction, a dead RTC
        battery) would issue stamps that sort beneath writes it already
        made. Stamps are fixed-width, so MAX() over the text is the causal
        maximum; rows that do not start with a digit cannot be stamps and
        are ignored.
        """
        top = self.conn.execute(
            "SELECT MAX(h) FROM ("
            " SELECT MAX(hlc) AS h FROM records WHERE hlc GLOB '[0-9]*'"
            " UNION ALL"
            " SELECT MAX(hlc) FROM changes WHERE hlc GLOB '[0-9]*')").fetchone()[0]
        if top is not None:
            self.hlc.observe(top)

    # -- migration -------------------------------------------------------
    def _migrate(self) -> None:
        for table, column, decl in MIGRATIONS:
            cur = self.conn.execute(f"PRAGMA table_info({table})")
            if column in {r["name"] for r in cur}:
                continue
            with self.conn:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def _backfill_state(self) -> None:
        """Give rows written before `state` existed the state they were being
        treated as. Every record was 'kept' except the machine proposals the
        timeline was picking out by producing-app name — those become
        'proposal', unless already published: a published scrobbler bead
        becomes 'kept', so it moves from the dotted rail to the solid one.

        Runs exactly once, marked by PRAGMA user_version. It must not be
        guarded on "are there any proposals yet", because keeping the last
        outstanding proposal would re-arm it and the next restart would
        demote that record back to a machine suggestion — undoing a decision
        the user had already made.
        """
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        placeholders = ",".join("?" for _ in LEGACY_MACHINE_APPS)
        with self.conn:
            self.conn.execute(
                f"UPDATE records SET state='proposal' WHERE source_app IN ({placeholders})"
                " AND published_uri IS NULL", LEGACY_MACHINE_APPS)
        # PRAGMA does not take a bound parameter, hence the interpolation of
        # a module constant.
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # -- writes ----------------------------------------------------------
    def _log(self, rid: str, op: str, payload: str, stamp: str,
             device: str | None, actor: str | None) -> None:
        self.conn.execute(
            "INSERT INTO changes (record_id, op, at, hlc, device_id, actor, body)"
            " VALUES (?,?,?,?,?,?,?)",
            (rid, op, now_iso(), stamp, device, actor, payload))

    def upsert(self, dedupe_key: str, rtype: str, source_app: str,
               created_at: str, body: dict, tier: int = 0,
               state: str = "kept", device: str | None = None,
               actor: str | None = None) -> tuple[str, str]:
        """Insert if new. Returns (id, status).

        An existing dedupe_key is normally left alone — a mint fact is
        witnessed once and never rewritten by a later run of anything.

        The exception is a **proposal being re-proposed**: a connector that
        polls a source can legitimately learn more about a moment it already
        described (a scrobble session that turned out to have three more
        tracks, a booking whose venue was corrected). While nobody has kept
        it, revising it loses nothing. The moment a person keeps it — or
        edits it, which keeps it (see patch) — it becomes theirs and the
        machine cannot touch it again.

        Two more cases are left alone. A re-run that sends the body already
        stored (compared as parsed JSON, so key order does not matter) says
        nothing new and writes nothing: no revision, no stamp, no change row
        — a connector re-sending the last 48 hours every hour must not churn
        the change feed. And a proposal that already has a public twin
        (published_uri set) is never revised underneath it.

        Returns status 'created', 'updated' (a proposal revised) or
        'duplicate' (left alone).
        """
        with self._lock:
            cur = self.conn.execute(
                "SELECT id, state, published_uri, body FROM records WHERE dedupe_key = ?",
                (dedupe_key,))
            row = cur.fetchone()
            payload = json.dumps(body, separators=(",", ":"))
            if row:
                revisable = (row["state"] == "proposal" and state == "proposal"
                             and row["published_uri"] is None
                             and json.loads(row["body"]) != body)
                if not revisable:
                    return row["id"], "duplicate"
                stamp = self.hlc.now()
                with self.conn:
                    self.conn.execute(
                        "UPDATE records SET body=?, revision=revision+1, hlc=? WHERE id=?",
                        (payload, stamp, row["id"]))
                    self._log(row["id"], "update", payload, stamp, device, actor)
                return row["id"], "updated"
            rid = str(uuid.uuid4())
            stamp = self.hlc.now()
            with self.conn:
                self.conn.execute(
                    "INSERT INTO records (id, dedupe_key, type, tier, source_app,"
                    " created_at, ingested_at, state, hlc, body)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rid, dedupe_key, rtype, tier, source_app,
                     created_at, now_iso(), state, stamp, payload))
                self._log(rid, "create", payload, stamp, device, actor)
            return rid, "created"

    #: patch() returns this when an If-Match precondition does not hold. A
    #: bare None already means "no such record", and the caller has to tell
    #: 404 from 412 apart.
    STALE = object()

    def patch(self, rid: str, fields: dict, *, expect_hlc: str | None = None,
              device: str | None = None, actor: str | None = None):
        """Shallow-merge fields into body, bump revision, restamp.

        `expect_hlc` is the caller saying which version it was editing. If
        the record has moved on since — another tab, another device, a
        connector — the write is refused rather than silently winning. Omit
        it and the old last-writer-wins behaviour applies, which is what
        every existing client still does.

        Editing a `proposal` keeps it: the state moves to `kept` in the same
        UPDATE as the body, so a later run of the connector that proposed it
        finds a kept record and leaves the edit alone (LOOM §7 — only a
        person keeps a proposal, and editing it is standing behind it). The
        change row is the one `update`; releasing a proposal is still DELETE.

        The precondition is enforced by the UPDATE itself (`WHERE id=? AND
        hlc matches`, then rowcount), not by comparing a value read earlier,
        so it holds even if the read and the write were ever to come apart.
        A legacy record with no stamp matches only an empty expectation, as
        before.
        """
        with self._lock:
            cur = self.conn.execute(
                "SELECT body, revision, hlc FROM records WHERE id=?", (rid,))
            row = cur.fetchone()
            if row is None:
                return None
            body = json.loads(row["body"])
            body.update(fields)
            payload = json.dumps(body, separators=(",", ":"))
            stamp = self.hlc.now()
            sql = ("UPDATE records SET body=?, revision=revision+1, hlc=?,"
                   " state=CASE WHEN state='proposal' THEN 'kept' ELSE state END"
                   " WHERE id=?")
            args: list = [payload, stamp, rid]
            if expect_hlc is not None:
                sql += " AND IFNULL(hlc, '') = ?"
                args.append(expect_hlc)
            with self.conn:
                if self.conn.execute(sql, args).rowcount == 0:
                    return self.STALE
                self._log(rid, "update", payload, stamp, device, actor)
            return self.get(rid)

    def set_state(self, rid: str, state: str, *, device: str | None = None,
                  actor: str | None = None) -> dict | None:
        """Move a record between proposal / kept / draft / published / edited.

        `proposal -> kept` is the affirmative act the README describes:
        machine-minted beads are "proposals, not facts, until you keep them".
        Until now there was no way to say so — the timeline offered only
        "release", which discards a proposal (it DELETEs the record). Keeping
        was simply not-discarding, and left no trace. This makes the decision
        explicit and, being in the change feed, syncable.
        """
        if state not in STATES:
            raise ValueError(f"unknown state: {state!r}")
        with self._lock:
            cur = self.conn.execute("SELECT body, state FROM records WHERE id=?", (rid,))
            row = cur.fetchone()
            if row is None:
                return None
            if row["state"] == state:
                return self.get(rid)
            stamp = self.hlc.now()
            with self.conn:
                self.conn.execute("UPDATE records SET state=?, hlc=? WHERE id=?",
                                  (state, stamp, rid))
                self._log(rid, "state", row["body"], stamp, device, actor)
            return self.get(rid)

    def delete(self, rid: str, *, device: str | None = None,
               actor: str | None = None) -> bool:
        with self._lock:
            cur = self.conn.execute("SELECT body FROM records WHERE id=?", (rid,))
            row = cur.fetchone()
            if row is None:
                return False
            with self.conn:
                self.conn.execute("DELETE FROM records WHERE id=?", (rid,))
                self._log(rid, "delete", row["body"], self.hlc.now(), device, actor)
            return True

    def set_published(self, rid: str, uri: str | None, phash: str | None, *,
                      device: str | None = None, actor: str | None = None) -> bool:
        with self._lock:
            cur = self.conn.execute("SELECT body FROM records WHERE id=?", (rid,))
            row = cur.fetchone()
            if row is None:
                return False
            stamp = self.hlc.now()
            with self.conn:
                self.conn.execute(
                    "UPDATE records SET published_uri=?, published_hash=?, hlc=? WHERE id=?",
                    (uri, phash, stamp, rid))
                # Logged so a second device learns that a record now has a public
                # twin — without this the change feed cannot describe publication
                # at all, and a syncing client would offer to publish it again.
                self._log(rid, "publish" if uri else "unpublish",
                          row["body"], stamp, device, actor)
            return True

    # -- reads -----------------------------------------------------------
    def get(self, rid: str) -> dict | None:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM records WHERE id=?", (rid,))
            row = cur.fetchone()
            return self._row(row) if row else None

    def query(self, day: str | None = None, rtype: str | None = None,
              source_app: str | None = None, state: str | None = None,
              limit: int = 500) -> list[dict]:
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
        if state:
            sql += " AND state=?"
            args.append(state)
        sql += " ORDER BY created_at ASC LIMIT ?"
        args.append(limit)
        with self._lock:
            return [self._row(r) for r in self.conn.execute(sql, args)]

    def changes_since(self, since: int, limit: int = 500) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT seq, record_id, op, at, hlc, device_id, actor, body FROM changes "
                "WHERE seq>? ORDER BY seq ASC LIMIT ?", (since, limit))
            return [{"seq": r["seq"], "recordId": r["record_id"], "op": r["op"],
                     "at": r["at"], "hlc": r["hlc"], "deviceId": r["device_id"],
                     "actor": r["actor"], "body": json.loads(r["body"])} for r in cur]

    def days(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT substr(created_at,1,10) AS day, COUNT(*) AS n "
                "FROM records GROUP BY day ORDER BY day DESC")
            return [{"day": r["day"], "count": r["n"]} for r in cur]

    # -- identities ------------------------------------------------------
    def identity_put(self, name: str, handle: str, app_password: str, pds: str) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO identities (name, handle, app_password, pds) VALUES (?,?,?,?) "
                    "ON CONFLICT(name) DO UPDATE SET handle=excluded.handle, "
                    "app_password=excluded.app_password, pds=excluded.pds",
                    (name, handle, app_password, pds))

    def identity_get(self, name: str) -> dict | None:
        with self._lock:
            cur = self.conn.execute(
                "SELECT name, handle, app_password, pds FROM identities WHERE name=?", (name,))
            row = cur.fetchone()
            return dict(row) if row else None

    def identities(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT name, handle, pds FROM identities ORDER BY name")
            return [dict(r) for r in cur]      # never returns app_password

    def identity_delete(self, name: str) -> bool:
        with self._lock:
            with self.conn:
                cur = self.conn.execute("DELETE FROM identities WHERE name=?", (name,))
            return cur.rowcount > 0

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
            "state": row["state"],
            "hlc": row["hlc"],
            "publishedUri": row["published_uri"],
            "publishedHash": row["published_hash"],
            "body": json.loads(row["body"]),
        }
