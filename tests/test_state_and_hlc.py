"""Phase 0 behaviour at the API edge: record state, revisable proposals,
If-Match preconditions, and the richer change feed.

Also covers the migration, which is the part that can quietly ruin a real
String: these columns are added to a database that already has a year of
beads in it.
"""
import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.db import Store  # noqa: E402


BEAD = "com.cultureblocs.bead"


def body(note="a note", kind="listen"):
    return {"$type": BEAD, "createdAt": "2026-08-15T21:04:00Z", "kind": kind, "note": note}


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "string.db"), node_id="testnode")


# -- state ---------------------------------------------------------------

def test_records_default_to_kept(store):
    rid, status = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    assert status == "created"
    assert store.get(rid)["state"] == "kept"


def test_a_proposal_may_be_revised_while_it_is_still_a_proposal(store):
    rid, _ = store.upsert("scrobble:me:1", BEAD, "scrobbler",
                          "2026-08-15T21:04:00Z", body("8 tracks"), state="proposal")
    _, status = store.upsert("scrobble:me:1", BEAD, "scrobbler",
                             "2026-08-15T21:04:00Z", body("11 tracks"), state="proposal")
    assert status == "updated"
    assert store.get(rid)["body"]["note"] == "11 tracks"


def test_once_kept_a_record_is_beyond_the_machine_that_proposed_it(store):
    rid, _ = store.upsert("scrobble:me:1", BEAD, "scrobbler",
                          "2026-08-15T21:04:00Z", body("8 tracks"), state="proposal")
    store.set_state(rid, "kept")
    _, status = store.upsert("scrobble:me:1", BEAD, "scrobbler",
                             "2026-08-15T21:04:00Z", body("rewritten"), state="proposal")
    assert status == "duplicate"
    assert store.get(rid)["body"]["note"] == "8 tracks"


def test_a_mint_fact_is_never_revised_even_by_another_mint(store):
    rid, _ = store.upsert("mint:abc", BEAD, "pocket", "2026-08-15T21:04:00Z", body("as minted"))
    _, status = store.upsert("mint:abc", BEAD, "pocket", "2026-08-15T21:04:00Z", body("second thoughts"))
    assert status == "duplicate"
    assert store.get(rid)["body"]["note"] == "as minted"


def test_unknown_state_is_refused(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    with pytest.raises(ValueError):
        store.set_state(rid, "vibes")


def test_query_filters_by_state(store):
    store.upsert("a", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    store.upsert("b", BEAD, "scrobbler", "2026-08-15T21:05:00Z", body(), state="proposal")
    assert len(store.query(state="proposal")) == 1
    assert len(store.query(state="kept")) == 1
    assert len(store.query()) == 2


# -- hlc / If-Match ------------------------------------------------------

def test_every_write_carries_a_stamp_and_stamps_move_forward(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    first = store.get(rid)["hlc"]
    store.patch(rid, {"note": "edited"})
    second = store.get(rid)["hlc"]
    assert first and second and second > first


def test_if_match_refuses_a_write_against_a_stale_version(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    stale = store.get(rid)["hlc"]
    store.patch(rid, {"note": "the other device got here first"})
    result = store.patch(rid, {"note": "my offline edit"}, expect_hlc=stale)
    assert result is Store.STALE
    assert store.get(rid)["body"]["note"] == "the other device got here first"


def test_if_match_allows_a_write_against_the_current_version(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    current = store.get(rid)["hlc"]
    result = store.patch(rid, {"note": "fine"}, expect_hlc=current)
    assert result is not Store.STALE
    assert result["body"]["note"] == "fine"


def test_without_if_match_the_old_last_writer_wins_behaviour_is_unchanged(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    store.patch(rid, {"note": "one"})
    store.patch(rid, {"note": "two"})
    assert store.get(rid)["body"]["note"] == "two"


def test_if_match_is_atomic_under_concurrent_writers(store):
    """FastAPI runs sync routes on a threadpool over one shared connection.
    Every writer holding the same If-Match must see exactly one winner per
    round, and no two writes may share a stamp."""
    threads, rounds = 8, 25
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    errors: list[BaseException] = []

    for r in range(rounds):
        expect = store.get(rid)["hlc"]
        barrier = threading.Barrier(threads)
        outcomes: list[object] = []

        def edit(n: int) -> None:
            try:
                barrier.wait()
                outcomes.append(store.patch(rid, {"note": f"round {r} writer {n}"},
                                            expect_hlc=expect))
            except BaseException as exc:          # surfaced below, not swallowed
                errors.append(exc)

        workers = [threading.Thread(target=edit, args=(n,)) for n in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        assert not errors, errors
        wins = [o for o in outcomes if o is not Store.STALE]
        assert len(wins) == 1, f"round {r}: {len(wins)} writers won against one If-Match"
        assert len(outcomes) - len(wins) == threads - 1

    stamps = [c["hlc"] for c in store.changes_since(0, limit=10_000)]
    assert len(stamps) == rounds + 1
    assert len(set(stamps)) == len(stamps)


def test_stamps_never_go_backwards_across_a_restart(tmp_path, monkeypatch):
    """The clock is seeded from the highest stamp on disk, so a host whose
    wall clock is behind the last write it made still stamps after it."""
    import app.hlc as hlc_module

    class Clock:
        def __init__(self, seconds: float):
            self.seconds = seconds

        def time(self) -> float:
            return self.seconds

    path = str(tmp_path / "string.db")
    monkeypatch.setattr(hlc_module, "time", Clock(1_800_000_000.0))
    first_store = Store(path, node_id="testnode")
    rid, _ = first_store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    first = first_store.get(rid)["hlc"]
    first_store.conn.close()

    monkeypatch.setattr(hlc_module, "time", Clock(1_700_000_000.0))   # three years behind
    reopened = Store(path, node_id="testnode")
    second = reopened.patch(rid, {"note": "after the restart"})["hlc"]
    assert second > first


# -- the change feed -----------------------------------------------------

def test_changes_carry_stamp_device_and_actor(store):
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body(),
                          device="phone", actor="local")
    store.patch(rid, {"note": "x"}, device="brick", actor="token")
    store.set_state(rid, "draft", device="brick", actor="token")
    ops = store.changes_since(0)
    assert [c["op"] for c in ops] == ["create", "update", "state"]
    assert [c["deviceId"] for c in ops] == ["phone", "brick", "brick"]
    assert [c["actor"] for c in ops] == ["local", "token", "token"]
    assert all(c["hlc"] for c in ops)
    assert [c["hlc"] for c in ops] == sorted(c["hlc"] for c in ops)


def test_publishing_appears_in_the_change_feed(store):
    """Without this a second device cannot learn that a record has a public
    twin, and would offer to publish it a second time."""
    rid, _ = store.upsert("k1", BEAD, "mint", "2026-08-15T21:04:00Z", body())
    store.set_published(rid, "at://did:plc:me/com.cultureblocs.bead/3lqk1", "abc123")
    store.set_published(rid, None, None)
    assert [c["op"] for c in store.changes_since(0)] == ["create", "publish", "unpublish"]


def test_a_device_can_filter_its_own_writes_out_of_the_feed(store):
    """The point of device_id: replaying the log on the device that wrote it
    must not re-apply its own ops."""
    store.upsert("a", BEAD, "mint", "2026-08-15T21:04:00Z", body(), device="phone")
    store.upsert("b", BEAD, "mint", "2026-08-15T21:05:00Z", body(), device="brick")
    mine = [c for c in store.changes_since(0) if c["deviceId"] != "phone"]
    assert len(mine) == 1


# -- migration -----------------------------------------------------------

def build_pre_phase0_db(path: Path) -> None:
    """A database in exactly the shape the String wrote before Phase 0."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE records (
            id TEXT PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
            tier INTEGER NOT NULL DEFAULT 0, source_app TEXT NOT NULL,
            created_at TEXT NOT NULL, ingested_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, published_uri TEXT,
            published_hash TEXT, body TEXT NOT NULL);
        CREATE TABLE changes (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL,
            op TEXT NOT NULL, at TEXT NOT NULL, body TEXT NOT NULL);
    """)
    rows = [
        ("r1", "mint:1", BEAD, "pocket", None),        # a hand-minted bead
        ("r2", "scrobble:me:1", BEAD, "scrobbler", None),   # a machine proposal
        ("r3", "scrobble:me:2", BEAD, "scrobbler",
         "at://did:plc:me/com.cultureblocs.bead/3lq"),      # proposal already published
    ]
    for rid, key, rtype, app_name, uri in rows:
        conn.execute(
            "INSERT INTO records (id, dedupe_key, type, source_app, created_at,"
            " ingested_at, published_uri, body) VALUES (?,?,?,?,?,?,?,?)",
            (rid, key, rtype, app_name, "2026-07-01T10:00:00Z", "2026-07-01T10:00:00Z",
             uri, json.dumps(body())))
    conn.commit()
    conn.close()


def test_migration_adds_columns_without_touching_the_data(tmp_path):
    path = tmp_path / "old.db"
    build_pre_phase0_db(path)
    store = Store(str(path), node_id="testnode")
    assert len(store.query()) == 3
    assert store.get("r1")["body"]["note"] == "a note"


def test_migration_backfills_state_so_the_dotted_rail_looks_the_same(tmp_path):
    path = tmp_path / "old.db"
    build_pre_phase0_db(path)
    store = Store(str(path), node_id="testnode")
    assert store.get("r1")["state"] == "kept"        # hand-minted
    assert store.get("r2")["state"] == "proposal"    # scrobbler, unreleased
    assert store.get("r3")["state"] == "kept"        # already published: not a proposal


def test_migration_is_idempotent_and_never_re_demotes_a_kept_proposal(tmp_path):
    path = tmp_path / "old.db"
    build_pre_phase0_db(path)
    store = Store(str(path), node_id="testnode")
    store.set_state("r2", "kept")
    del store
    reopened = Store(str(path), node_id="testnode")
    assert reopened.get("r2")["state"] == "kept"


def test_pre_phase0_rows_have_no_stamp_until_they_are_next_written(tmp_path):
    """Backfilling stamps onto historical rows would invent an ordering that
    never happened. They stay null and acquire one on first write."""
    path = tmp_path / "old.db"
    build_pre_phase0_db(path)
    store = Store(str(path), node_id="testnode")
    assert store.get("r1")["hlc"] is None
    store.patch("r1", {"note": "touched"})
    assert store.get("r1")["hlc"] is not None


def test_if_match_against_an_unstamped_legacy_record(tmp_path):
    """A client that reads hlc=null and sends no If-Match still works; one
    that sends a stamp for a record that has none is refused."""
    path = tmp_path / "old.db"
    build_pre_phase0_db(path)
    store = Store(str(path), node_id="testnode")
    assert store.patch("r1", {"note": "ok"}, expect_hlc=None) is not Store.STALE
    assert store.patch("r1", {"note": "no"}, expect_hlc="0000000000000-00000-x") is Store.STALE
