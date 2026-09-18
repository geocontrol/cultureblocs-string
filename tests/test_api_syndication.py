"""POST /publish with destinations, and GET /destinations, end to end with
the network stubbed. Spec §4 (two phases), §8 (error handling)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))

STRAND = "com.cultureblocs.strand"
BEAD = "com.cultureblocs.bead"
DAY = "2026-09-18T10:00:00Z"


@pytest.fixture
def api(client, monkeypatch):
    """The client, a held identity, a strand with one bead, and a recorded network."""
    import app.main as main
    calls = []

    def fake_xrpc(_pds, method, *, body=None, token=None):
        calls.append(method)
        if method == "com.atproto.server.createSession":
            return {"did": "did:plc:me", "accessJwt": "jwt"}
        if method == "com.atproto.repo.putRecord":
            return {"uri": f"at://did:plc:me/{body['collection']}/{body['rkey']}", "cid": "bafycid"}
        if method == "com.atproto.repo.createRecord":
            return {"uri": "at://did:plc:me/app.bsky.feed.post/3post", "cid": "bafypost"}
        raise AssertionError(f"unexpected xrpc call: {method}")

    monkeypatch.setattr(main.publisher, "_xrpc", fake_xrpc)
    client.put("/identities/personal", json={"handle": "me.example", "appPassword": "x",
                                             "pds": "https://pds.example"})
    [bead] = client.post("/records", json={"records": [{
        "dedupeKey": "b1", "type": BEAD, "sourceApp": "loom", "createdAt": DAY,
        "body": {"$type": BEAD, "kind": "bloc", "note": "first", "createdAt": DAY}}]}).json()["results"]
    [strand] = client.post("/records", json={"records": [{
        "dedupeKey": "s1", "type": STRAND, "sourceApp": "loom", "createdAt": DAY,
        "body": {"$type": STRAND, "createdAt": DAY, "title": "A day out",
                 "items": [{"uri": f"spine://records/{bead['id']}"}]}}]}).json()["results"]
    client.calls = calls
    client.main = main
    client.strand = strand["id"]
    client.bead = bead["id"]
    return client


def publish(api, **extra):
    return api.post(f"/publish/{api.strand}", json={"identity": "personal", **extra})


def test_destinations_are_listed_with_their_limits(api):
    body = api.get("/destinations").json()
    assert {"name": "bluesky", "limits": {"text": 300, "images": 4, "wants_link": False}} \
        in body["destinations"]


def test_publish_without_destinations_is_exactly_as_before(api):
    body = publish(api).json()
    assert body["strandUri"].startswith("at://")
    assert "syndications" not in body
    assert "com.atproto.repo.createRecord" not in api.calls


def test_publish_with_bluesky_reports_both_phases_separately(api):
    body = publish(api, destinations=["bluesky"], postText="A day out").json()
    assert body["strandUri"] == f"at://did:plc:me/{STRAND}/{api.strand}"
    [s] = body["syndications"]
    assert s["destination"] == "bluesky" and s["status"] == "posted"
    assert s["remoteUrl"] == "https://bsky.app/profile/me.example/post/3post"
    assert api.calls.count("com.atproto.server.createSession") == 1, "phase 2 reuses the session"


def test_the_record_then_carries_its_syndication_singly_and_in_lists(api):
    publish(api, destinations=["bluesky"], postText="A day out")
    one = api.get(f"/records/{api.strand}").json()
    assert one["syndications"][0]["remoteUrl"] == "https://bsky.app/profile/me.example/post/3post"
    listed = [r for r in api.get("/records?day=2026-09-18").json()["records"]
              if r["id"] == api.strand]
    assert listed[0]["syndications"] == one["syndications"]


def test_republishing_skips_a_used_destination_and_never_double_posts(api):
    publish(api, destinations=["bluesky"], postText="A day out")
    [s] = publish(api, destinations=["bluesky"], postText="A day out").json()["syndications"]
    assert s["status"] == "already"
    assert api.calls.count("com.atproto.repo.createRecord") == 1


def test_a_failing_destination_leaves_the_publish_intact_and_records_nothing(api, monkeypatch):
    def down(*_a, **_k):
        raise RuntimeError("bsky is down")
    monkeypatch.setattr(api.main.syndicate.bluesky, "post", down)
    resp = publish(api, destinations=["bluesky"], postText="A day out")
    assert resp.status_code == 200
    assert resp.json()["syndications"] == [
        {"destination": "bluesky", "status": "failed", "reason": "bsky is down"}]
    rec = api.get(f"/records/{api.strand}").json()
    assert rec["publishedUri"].startswith("at://"), "phase 2 cannot fail phase 1"
    assert rec["syndications"] == []


@pytest.mark.parametrize("extra, words", [
    ({"destinations": ["myspace"], "postText": "hi"}, "unknown destination"),
    ({"destinations": ["bluesky"], "postText": "a" * 301}, "301"),
    ({"destinations": ["bluesky"], "postText": "   "}, "empty"),
    ({"destinations": ["bluesky"]}, "empty"),
])
def test_a_bad_request_is_refused_before_anything_publishes(api, extra, words):
    resp = publish(api, **extra)
    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], str) and words in resp.json()["detail"]
    assert api.calls == [], "no network call at all"
    assert api.get(f"/records/{api.strand}").json()["publishedUri"] is None


def test_destinations_on_a_record_that_is_not_a_strand_are_refused(api):
    resp = api.post(f"/publish/{api.bead}", json={"identity": "personal",
                                                  "destinations": ["bluesky"], "postText": "hi"})
    assert resp.status_code == 422
    assert "strand" in resp.json()["detail"]
    assert api.calls == []
