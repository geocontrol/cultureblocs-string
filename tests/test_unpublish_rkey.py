"""Unpublish must delete the rkey it actually published under.

A record born on the network — minted on a phone, imported here later — has an
rkey assigned elsewhere, so its local record id is not its public rkey.
`publish_strand` honours that through `_rkey_for`; unpublish has to agree, or
it deletes nothing and clears the local link anyway, leaving the record public
for good with nothing left pointing at it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402

STRAND = "com.cultureblocs.strand"
BEAD = "com.cultureblocs.bead"
DID = "did:plc:example"


class FakeStore:
    def __init__(self, records):
        self.records = records
        self.cleared = []

    def get(self, rid):
        return self.records.get(rid)

    def set_published(self, rid, uri, digest):
        self.cleared.append((rid, uri, digest))
        self.records[rid]["publishedUri"] = uri


def born_public_strand():
    """A strand and its bead, both published under rkeys assigned elsewhere."""
    return FakeStore({
        "local-strand-uuid": {
            "type": STRAND,
            "publishedUri": f"at://{DID}/{STRAND}/3strandtid",
            "body": {"items": [{"uri": "spine://records/local-bead-uuid"}]},
        },
        "local-bead-uuid": {
            "type": BEAD,
            "publishedUri": f"at://{DID}/{BEAD}/3beadtid",
            "body": {},
        },
    })


def record_deletes(monkeypatch):
    """Capture every deleteRecord body the publisher sends."""
    calls = []

    def fake_xrpc(pds, method, token=None, body=None):
        if method == "com.atproto.server.createSession":
            return {"did": DID, "accessJwt": "jwt"}
        calls.append((method, body))
        return {}

    monkeypatch.setattr(publisher, "_xrpc", fake_xrpc)
    return calls


IDENTITY = {"name": "personal", "handle": "someone.example",
            "app_password": "pw", "pds": "https://pds.example"}


def test_unpublish_deletes_the_bead_rkey_it_published_under(monkeypatch):
    calls = record_deletes(monkeypatch)
    store = born_public_strand()

    publisher.unpublish_strand(store, "local-strand-uuid", IDENTITY)

    bead_deletes = [b for _, b in calls if b["collection"] == BEAD]
    assert len(bead_deletes) == 1, calls
    assert bead_deletes[0]["rkey"] == "3beadtid", (
        "unpublish sent the local record id as the rkey, so the public bead survives")


def test_unpublish_deletes_the_strand_rkey_it_published_under(monkeypatch):
    calls = record_deletes(monkeypatch)
    store = born_public_strand()

    publisher.unpublish_strand(store, "local-strand-uuid", IDENTITY)

    strand_deletes = [b for _, b in calls if b["collection"] == STRAND]
    assert len(strand_deletes) == 1, calls
    assert strand_deletes[0]["rkey"] == "3strandtid", (
        "unpublish sent the local record id as the rkey, so the public strand survives")


def test_unpublish_still_uses_the_record_id_when_that_is_the_public_rkey(monkeypatch):
    """The ordinary case: a record published from here keeps id == rkey."""
    calls = record_deletes(monkeypatch)
    store = FakeStore({
        "s1": {"type": STRAND, "publishedUri": f"at://{DID}/{STRAND}/s1",
               "body": {"items": [{"uri": "spine://records/b1"}]}},
        "b1": {"type": BEAD, "publishedUri": f"at://{DID}/{BEAD}/b1", "body": {}},
    })

    result = publisher.unpublish_strand(store, "s1", IDENTITY)

    assert result == {"removed": 2}
    assert sorted(b["rkey"] for _, b in calls) == ["b1", "s1"]


def test_unpublish_reports_and_clears_both_records(monkeypatch):
    record_deletes(monkeypatch)
    store = born_public_strand()

    result = publisher.unpublish_strand(store, "local-strand-uuid", IDENTITY)

    assert result == {"removed": 2}
    assert store.cleared == [("local-bead-uuid", None, None),
                             ("local-strand-uuid", None, None)]
