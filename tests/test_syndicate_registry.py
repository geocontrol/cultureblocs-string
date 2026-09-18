"""The registry: validate before phase 1, execute after it (spec §4, §8)."""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import syndicate  # noqa: E402
from app.db import Store  # noqa: E402

STRAND = "com.cultureblocs.strand"
HELD = {"session": {"did": "did:plc:me", "jwt": "jwt", "pds": "https://pds.example",
                    "handle": "me.example"},
        "strand": {"title": "A day out"}, "items": []}


def fake_adapter(name, limit=300, fail=None):
    calls = []

    def post(session, strand, items, text):
        calls.append(text)
        if fail:
            raise RuntimeError(fail)
        return {"id": f"{name}-{len(calls)}", "url": f"https://{name}.example/{len(calls)}",
                "dropped": 0}
    mod = types.SimpleNamespace(NAME=name, LIMITS={"text": limit, "images": 4,
                                                   "wants_link": False}, post=post)
    return mod, calls


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.upsert("k1", STRAND, "loom", "2026-09-18T10:00:00Z",
             {"$type": STRAND, "createdAt": "2026-09-18T10:00:00Z", "items": []})
    s.rid = s.query()[0]["id"]
    return s


def test_available_lists_bluesky_with_its_limits():
    assert {"name": "bluesky", "limits": {"text": 300, "images": 4, "wants_link": False}} \
        in syndicate.available()


def test_no_destinations_is_never_a_problem():
    assert syndicate.check([], None) == []


def test_an_unknown_destination_is_named_along_with_the_ones_that_exist():
    [problem] = syndicate.check(["myspace"], "hello")
    assert "myspace" in problem and "bluesky" in problem


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_text_is_a_problem(text):
    assert syndicate.check(["bluesky"], text) == ["post text is empty"]


def test_text_is_held_to_the_smallest_ticked_limit(monkeypatch):
    tiny, _ = fake_adapter("tiny", limit=10)
    monkeypatch.setitem(syndicate.DESTINATIONS, "tiny", tiny)
    assert syndicate.check(["bluesky", "tiny"], "a" * 10) == []
    [problem] = syndicate.check(["bluesky", "tiny"], "a" * 11)
    assert "11" in problem and "10" in problem


def test_run_posts_and_records_the_row(monkeypatch, store):
    mod, calls = fake_adapter("bluesky")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", mod)
    [r] = syndicate.run(store, store.rid, ["bluesky"], "hello", HELD)
    assert r["status"] == "posted" and r["remoteUrl"] == "https://bluesky.example/1"
    assert r["droppedImages"] == 0 and r["postedAt"]
    assert calls == ["hello"]
    assert store.syndication(store.rid, "bluesky")["remoteId"] == "bluesky-1"


def test_a_second_run_skips_a_used_destination_and_says_so(monkeypatch, store):
    mod, calls = fake_adapter("bluesky")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", mod)
    syndicate.run(store, store.rid, ["bluesky"], "hello", HELD)
    [r] = syndicate.run(store, store.rid, ["bluesky"], "hello again", HELD)
    assert r == {"destination": "bluesky", "status": "already",
                 "remoteUrl": "https://bluesky.example/1",
                 "postedAt": store.syndication(store.rid, "bluesky")["postedAt"]}
    assert calls == ["hello"], "never double-posts"


def test_a_failing_destination_records_nothing_and_stays_available(monkeypatch, store):
    bad, _ = fake_adapter("bluesky", fail="PDS said no")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", bad)
    [r] = syndicate.run(store, store.rid, ["bluesky"], "hello", HELD)
    assert r == {"destination": "bluesky", "status": "failed", "reason": "PDS said no"}
    assert store.syndications(store.rid) == []
    good, _ = fake_adapter("bluesky")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", good)
    [r] = syndicate.run(store, store.rid, ["bluesky"], "hello", HELD)
    assert r["status"] == "posted"


def test_one_failure_does_not_stop_the_next_destination(monkeypatch, store):
    bad, _ = fake_adapter("bluesky", fail="down")
    other, calls = fake_adapter("other")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", bad)
    monkeypatch.setitem(syndicate.DESTINATIONS, "other", other)
    out = syndicate.run(store, store.rid, ["bluesky", "other"], "hi", HELD)
    assert [r["status"] for r in out] == ["failed", "posted"]


def test_a_name_given_twice_posts_once(monkeypatch, store):
    mod, calls = fake_adapter("bluesky")
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky", mod)
    out = syndicate.run(store, store.rid, ["bluesky", "bluesky"], "hi", HELD)
    assert len(out) == 1 and calls == ["hi"]


def test_the_adapter_is_given_exactly_what_phase_1_held(monkeypatch, store):
    seen = {}

    def post(session, strand, items, text):
        seen.update(session=session, strand=strand, items=items, text=text)
        return {"id": "1", "url": None, "dropped": 0}
    monkeypatch.setitem(syndicate.DESTINATIONS, "bluesky",
                        types.SimpleNamespace(NAME="bluesky", LIMITS={"text": 300}, post=post))
    syndicate.run(store, store.rid, ["bluesky"], "hi", HELD)
    assert seen == {"session": HELD["session"], "strand": HELD["strand"],
                    "items": HELD["items"], "text": "hi"}
