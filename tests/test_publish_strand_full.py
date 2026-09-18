"""What phase 1 hands to phase 2 (spec §4.1): the session it already holds,
and the strand's members *as published* — stripped, with the image refs it
just uploaded. An adapter given only these cannot reach private data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402

DID = "did:plc:fake"
IDENTITY = {"name": "personal", "handle": "me.example", "app_password": "x",
            "pds": "https://pds.example"}
IMAGE = {"image": {"$type": "blob", "ref": {"$link": "bafkreiaaa"},
                   "mimeType": "image/jpeg", "size": 10},
         "alt": "Gasholder at dusk."}


class FakeStore:
    def __init__(self, records):
        self.records = records

    def get(self, rid):
        return self.records.get(rid)

    def set_published(self, rid, uri, phash):
        self.records[rid]["publishedUri"] = uri
        return True


def stub_network(monkeypatch):
    def fake_xrpc(_pds, method, *, body=None, token=None):
        if method == "com.atproto.server.createSession":
            return {"did": DID, "accessJwt": "jwt"}
        if method == "com.atproto.repo.putRecord":
            return {"uri": f"at://{DID}/{body['collection']}/{body['rkey']}", "cid": "bafycid"}
        raise AssertionError(f"unexpected xrpc call: {method}")
    def fake_login(_identity):
        return DID, "jwt", "https://pds.example"
    monkeypatch.setattr(publisher, "_xrpc", fake_xrpc)
    monkeypatch.setattr(publisher, "_login", fake_login)
    monkeypatch.setattr(publisher, "_image_refs", lambda body, *_: [IMAGE] if body.get("media") else [])


def a_day(monkeypatch):
    stub_network(monkeypatch)
    return FakeStore({
        "s1": {"id": "s1", "type": publisher.STRAND, "publishedUri": None, "sourceApp": "loom",
               "body": {"$type": publisher.STRAND, "createdAt": "2026-09-18T10:00:00Z",
                        "title": "A day out", "narrative": "private-ish prose",
                        "items": [{"uri": "spine://records/b1"}, {"uri": "spine://records/b2"}]}},
        "b1": {"id": "b1", "type": "com.cultureblocs.bead", "publishedUri": None, "sourceApp": "loom",
               "body": {"$type": "com.cultureblocs.bead", "kind": "bloc", "note": "first",
                        "createdAt": "2026-09-18T10:00:00Z", "geo": {"lat": 51.5, "lon": -0.1},
                        "provenance": {"app": "loom", "mintedAt": "2026-09-18T10:00:00Z"},
                        "media": [{"uri": "/media/abc.jpg"}]}},
        "b2": {"id": "b2", "type": "com.cultureblocs.bead", "publishedUri": None, "sourceApp": "loom",
               "body": {"$type": "com.cultureblocs.bead", "kind": "bloc", "note": "second",
                        "createdAt": "2026-09-18T11:00:00Z"}},
    })


def test_the_session_phase_1_logged_in_with_is_handed_on(monkeypatch):
    store = a_day(monkeypatch)
    _, held = publisher.publish_strand_full(store, "s1", IDENTITY)
    assert held["session"] == {"did": DID, "jwt": "jwt", "pds": "https://pds.example",
                               "handle": "me.example"}


def test_items_are_stripped_members_in_order_with_their_uploaded_images(monkeypatch):
    store = a_day(monkeypatch)
    _, held = publisher.publish_strand_full(store, "s1", IDENTITY)
    assert [i["note"] for i in held["items"]] == ["first", "second"]
    assert held["items"][0]["images"] == [IMAGE]
    assert "images" not in held["items"][1]
    for item in held["items"]:
        assert "geo" not in item and "provenance" not in item and "media" not in item


def test_the_strand_is_handed_on_stripped(monkeypatch):
    store = a_day(monkeypatch)
    _, held = publisher.publish_strand_full(store, "s1", IDENTITY)
    assert held["strand"]["title"] == "A day out"
    assert held["strand"]["items"][0]["uri"].startswith("at://")


def test_the_result_is_what_publish_strand_returns(monkeypatch):
    result, _ = publisher.publish_strand_full(a_day(monkeypatch), "s1", IDENTITY)
    assert result == publisher.publish_strand(a_day(monkeypatch), "s1", IDENTITY)
    assert result["strandUri"] == f"at://{DID}/{publisher.STRAND}/s1"


def test_a_record_that_is_not_a_strand_holds_nothing_for_phase_2(monkeypatch):
    stub_network(monkeypatch)
    store = FakeStore({"w1": {"id": "w1", "type": "com.cultureblocs.creative.work",
                              "publishedUri": None, "sourceApp": "loom",
                              "body": {"$type": "com.cultureblocs.creative.work", "title": "x"}}})
    result, held = publisher.publish_strand_full(store, "w1", IDENTITY)
    assert held is None
    assert result["uri"].startswith("at://")
