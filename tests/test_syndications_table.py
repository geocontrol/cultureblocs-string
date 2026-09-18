"""The syndications table: one row per (record, destination).

The row *is* the one-shot rule — it lives in the database rather than in
Loom's state so it holds across a reload, a second device and a re-import.
Spec §4.2."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import db  # noqa: E402
from app.db import Store  # noqa: E402

STRAND = "com.cultureblocs.strand"


def a_strand(s: Store, key: str = "k1") -> str:
    body = {"$type": STRAND, "createdAt": "2026-09-18T10:00:00Z", "title": "A day out",
            "items": []}
    rid, _ = s.upsert(key, STRAND, "loom", "2026-09-18T10:00:00Z", body)
    return rid


def test_a_record_starts_with_no_syndications(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    assert s.syndications(rid) == []
    assert s.get(rid)["syndications"] == []


def test_adding_one_stores_it_and_the_record_carries_it(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    row = s.add_syndication(rid, "bluesky", "3post",
                            "https://bsky.app/profile/me.example/post/3post")
    assert row["destination"] == "bluesky"
    assert row["remoteId"] == "3post"
    assert row["remoteUrl"] == "https://bsky.app/profile/me.example/post/3post"
    assert row["postedAt"].endswith("Z")
    assert s.syndication(rid, "bluesky") == row
    assert s.get(rid)["syndications"] == [row]


def test_adding_twice_is_idempotent_and_keeps_the_first(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    first = s.add_syndication(rid, "bluesky", "3first", "https://x/first")
    again = s.add_syndication(rid, "bluesky", "3second", "https://x/second")
    assert again == first, "a used destination is never overwritten"
    assert len(s.syndications(rid)) == 1


def test_one_record_can_go_to_two_destinations(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    s.add_syndication(rid, "bluesky", "3a", "https://x/a")
    s.add_syndication(rid, "mastodon", "109", None)
    assert [r["destination"] for r in s.syndications(rid)] == ["bluesky", "mastodon"]
    assert s.syndication(rid, "mastodon")["remoteUrl"] is None


def test_list_rows_carry_syndications_too(tmp_path):
    """Loom imports from GET /records?day=, not /records/{id}."""
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    s.add_syndication(rid, "bluesky", "3a", "https://x/a")
    [row] = s.query(day="2026-09-18")
    assert row["syndications"][0]["remoteId"] == "3a"


def test_an_unknown_record_is_refused(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    assert s.add_syndication("no-such-id", "bluesky", "3a", None) is None


def test_deleting_the_record_removes_its_rows(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    rid = a_strand(s)
    s.add_syndication(rid, "bluesky", "3a", None)
    assert s.delete(rid) is True
    n = s.conn.execute("SELECT COUNT(*) FROM syndications").fetchone()[0]
    assert n == 0


def test_a_database_from_before_this_gains_the_table(tmp_path):
    """A running String has a string.db without the table; opening it adds it."""
    path = tmp_path / "old.db"
    before = db.SCHEMA.split("CREATE TABLE IF NOT EXISTS syndications")[0]
    conn = sqlite3.connect(path)
    conn.executescript(before)
    conn.close()
    s = Store(str(path))
    rid = a_strand(s)
    assert s.add_syndication(rid, "bluesky", "3a", None)["remoteId"] == "3a"
