"""Seeded fair data (sourceApp: seed-*, or tagged seed:artworld) must never
reach the publish path. Network calls are stubbed: this proves the refusal
happens before any network call is made, not just that a real PDS would
reject it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402


class FakeStore:
    """Duck-types just enough of app.db.Store for publisher.py to use."""

    def __init__(self, records: dict):
        self.records = records
        self.published = {}

    def get(self, rid):
        return self.records.get(rid)

    def set_published(self, rid, uri, phash):
        self.published[rid] = (uri, phash)
        if rid in self.records:
            self.records[rid]["publishedUri"] = uri
            self.records[rid]["publishedHash"] = phash
        return True


IDENTITY = {"name": "test", "handle": "test.bsky.social",
            "app_password": "x", "pds": "https://pds.example"}


def fake_login(_identity):
    return "did:plc:fake", "jwt-token", "https://pds.example"


def fake_xrpc(_pds, method, *, body=None, token=None):
    if method == "com.atproto.server.createSession":
        return {"did": "did:plc:fake", "accessJwt": "jwt-token"}
    if method == "com.atproto.repo.putRecord":
        return {"uri": "at://did:plc:fake/collection/rkey", "cid": "bafycid"}
    raise AssertionError(f"unexpected xrpc call: {method}")


def seeded_by_source_app():
    return {
        "id": "rec1", "type": "com.cultureblocs.venue.lineup",
        "sourceApp": "seed-frieze", "publishedUri": None,
        "body": {"$type": "com.cultureblocs.venue.lineup",
                 "billing": [{"name": "Alison Jacques", "role": "gallery"}],
                 "tags": ["fair:frieze-london-2026"]},
    }


def seeded_by_tag():
    return {
        "id": "rec2", "type": "com.cultureblocs.venue.lineup",
        "sourceApp": "someone-else", "publishedUri": None,
        "body": {"$type": "com.cultureblocs.venue.lineup",
                 "billing": [{"name": "Alison Jacques", "role": "gallery"}],
                 "tags": ["seed:artworld", "fair:frieze-london-2026"]},
    }


def ordinary_record():
    return {
        "id": "rec3", "type": "com.cultureblocs.venue.lineup",
        "sourceApp": "rounds", "publishedUri": None,
        "body": {"$type": "com.cultureblocs.venue.lineup",
                 "billing": [{"name": "Some Gallery", "role": "gallery"}],
                 "tags": ["fair:frieze-london-2026"]},
    }


def test_publish_record_refuses_a_record_with_seed_source_app():
    publisher._login = fake_login
    publisher._xrpc = fake_xrpc
    store = FakeStore({"rec1": seeded_by_source_app()})
    try:
        publisher.publish_record(store, "rec1", IDENTITY)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "seeded" in str(exc), exc
    assert store.records["rec1"].get("publishedUri") is None


def test_publish_record_refuses_a_record_tagged_seed_artworld():
    publisher._login = fake_login
    publisher._xrpc = fake_xrpc
    store = FakeStore({"rec2": seeded_by_tag()})
    try:
        publisher.publish_record(store, "rec2", IDENTITY)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "seeded" in str(exc), exc
    assert store.records["rec2"].get("publishedUri") is None


def test_publish_record_still_publishes_an_ordinary_record_of_the_same_type():
    """The guard must not become a blanket refusal of venue.lineup — only
    records that are actually seeded."""
    publisher._login = fake_login
    publisher._xrpc = fake_xrpc
    store = FakeStore({"rec3": ordinary_record()})
    result = publisher.publish_record(store, "rec3", IDENTITY)
    assert result["uri"] == "at://did:plc:fake/collection/rkey"
    assert store.records["rec3"]["publishedUri"] == "at://did:plc:fake/collection/rkey"


def test_publish_strand_refuses_a_seeded_bead_in_its_item_list():
    publisher._login = fake_login
    publisher._xrpc = fake_xrpc
    bead = {
        "id": "bead1", "type": "com.cultureblocs.bead",
        "sourceApp": "seed-frieze", "publishedUri": None,
        "body": {"$type": "com.cultureblocs.bead", "kind": "note",
                 "note": "hello", "createdAt": "2026-08-15T10:00:00Z",
                 "tags": ["seed:artworld"]},
    }
    strand = {
        "id": "strand1", "type": publisher.STRAND, "publishedUri": None,
        "body": {"$type": publisher.STRAND, "createdAt": "2026-08-15T10:00:00Z",
                 "items": [{"uri": "spine://records/bead1"}]},
    }
    store = FakeStore({"strand1": strand, "bead1": bead})
    try:
        publisher.publish_strand(store, "strand1", IDENTITY)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "seeded" in str(exc), exc


if __name__ == "__main__":
    test_publish_record_refuses_a_record_with_seed_source_app()
    test_publish_record_refuses_a_record_tagged_seed_artworld()
    test_publish_record_still_publishes_an_ordinary_record_of_the_same_type()
    test_publish_strand_refuses_a_seeded_bead_in_its_item_list()
    print("OK: publish refuses seeded data")
