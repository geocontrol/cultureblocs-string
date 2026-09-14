"""A connector re-run must never erase what a person did to its proposal.

LOOM §7: proposals are not facts, and only a person keeps them. Editing a
proposal is standing behind it, so the edit keeps it; after that the
connector that proposed it cannot touch it again. A re-run that says
nothing new writes nothing at all, and a proposal that already has a
public twin is never revised underneath it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.db import Store  # noqa: E402

BEAD = "com.cultureblocs.bead"
KEY = "scrobble:me:1"
AT = "2026-08-15T21:04:00Z"


def body(note: str = "8 tracks") -> dict:
    return {"$type": BEAD, "createdAt": AT, "kind": "listen", "note": note}


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "string.db"), node_id="testnode")


def propose(store: Store, note: str = "8 tracks") -> tuple[str, str]:
    return store.upsert(KEY, BEAD, "scrobbler", AT, body(note), state="proposal")


def test_editing_a_proposal_keeps_it_and_a_re_run_leaves_the_edit_alone(store):
    rid, _ = propose(store)
    media = [{"uri": "/media/abc.jpg", "mime": "image/jpeg"}]
    store.patch(rid, {"note": "the one where it rained", "media": media})
    assert store.get(rid)["state"] == "kept"

    _, status = propose(store, "8 tracks")
    assert status == "duplicate"
    rec = store.get(rid)
    assert rec["body"]["note"] == "the one where it rained"
    assert rec["body"]["media"] == media
    assert rec["state"] == "kept"


def test_the_keep_is_in_the_same_write_as_the_edit(store):
    """One PATCH, one change row, one stamp: the record never exists as an
    edited proposal a re-run could slip in against."""
    rid, _ = propose(store)
    before = len(store.changes_since(0))
    rec = store.patch(rid, {"note": "mine now"})
    assert rec["state"] == "kept"
    assert len(store.changes_since(0)) == before + 1


def test_an_identical_re_proposal_writes_nothing(store):
    rid, _ = propose(store)
    rec = store.get(rid)
    changes = len(store.changes_since(0))

    _, status = propose(store)
    assert status == "duplicate"
    again = store.get(rid)
    assert again["revision"] == rec["revision"]
    assert again["hlc"] == rec["hlc"]
    assert len(store.changes_since(0)) == changes


def test_identical_means_the_same_parsed_body_not_the_same_key_order(store):
    rid, _ = propose(store)
    reordered = {"note": "8 tracks", "kind": "listen", "createdAt": AT, "$type": BEAD}
    _, status = store.upsert(KEY, BEAD, "scrobbler", AT, reordered, state="proposal")
    assert status == "duplicate"
    assert store.get(rid)["revision"] == 1


def test_a_published_proposal_is_never_revised(store):
    rid, _ = propose(store)
    store.set_published(rid, "at://did:plc:me/com.cultureblocs.bead/3lq", "abc123")
    rec = store.get(rid)

    _, status = propose(store, "11 tracks")
    assert status == "duplicate"
    again = store.get(rid)
    assert again["body"]["note"] == "8 tracks"
    assert again["revision"] == rec["revision"]


def test_a_different_body_still_revises_an_untouched_proposal(store):
    rid, _ = propose(store)
    _, status = propose(store, "11 tracks")
    assert status == "updated"
    assert store.get(rid)["body"]["note"] == "11 tracks"


def test_editing_a_record_that_is_not_a_proposal_leaves_its_state(store):
    rid, _ = store.upsert("mint:1", BEAD, "pocket", AT, body())
    store.set_state(rid, "draft")
    assert store.patch(rid, {"note": "edited"})["state"] == "draft"
