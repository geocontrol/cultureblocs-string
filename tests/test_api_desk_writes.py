"""What Loom's desk needs from the String to manage records it did not just
create: a PATCH that can remove a field, and a DELETE that refuses to remove
a version the client has not seen."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))

BEAD = "com.cultureblocs.bead"


def ingest(client, key, **fields):
    body = {"$type": BEAD, "createdAt": "2026-08-15T21:04:00Z", "kind": "listen",
            "note": "a note", **fields}
    rec = {"dedupeKey": key, "type": BEAD, "sourceApp": "rounds",
           "createdAt": "2026-08-15T21:04:00Z", "body": body}
    return client.post("/records", json={"records": [rec]}).json()["results"][0]["id"]


# -- PATCH: null removes a field ---------------------------------------------

def test_a_null_field_is_removed_from_the_body(client):
    rid = ingest(client, "k1", tags=["jazz"])
    resp = client.patch(f"/records/{rid}", json={"fields": {"tags": None, "note": "kept"}})
    assert resp.status_code == 200
    body = client.get(f"/records/{rid}").json()["body"]
    assert "tags" not in body
    assert body["note"] == "kept"


def test_removing_a_field_that_is_not_there_is_harmless(client):
    rid = ingest(client, "k1")
    assert client.patch(f"/records/{rid}", json={"fields": {"tags": None}}).status_code == 200
    assert "tags" not in client.get(f"/records/{rid}").json()["body"]


def test_removing_a_required_field_is_refused_and_nothing_changes(client):
    rid = ingest(client, "k1")
    resp = client.patch(f"/records/{rid}", json={"fields": {"kind": None, "note": "changed"}})
    assert resp.status_code == 422
    body = client.get(f"/records/{rid}").json()["body"]
    assert body["kind"] == "listen" and body["note"] == "a note"


def test_null_removal_honours_if_match(client):
    rid = ingest(client, "k1", tags=["jazz"])
    stale = client.get(f"/records/{rid}").json()["hlc"]
    client.patch(f"/records/{rid}", json={"fields": {"note": "moved on"}})
    resp = client.patch(f"/records/{rid}", json={"fields": {"tags": None}}, headers={"If-Match": stale})
    assert resp.status_code == 412
    assert client.get(f"/records/{rid}").json()["body"]["tags"] == ["jazz"]


# -- DELETE: If-Match --------------------------------------------------------

def test_delete_with_the_current_stamp_deletes(client):
    rid = ingest(client, "k1")
    current = client.get(f"/records/{rid}").json()["hlc"]
    resp = client.delete(f"/records/{rid}", headers={"If-Match": f'"{current}"'})
    assert resp.status_code == 200 and resp.json() == {"deleted": rid}
    assert client.get(f"/records/{rid}").status_code == 404


def test_delete_with_a_stale_stamp_is_refused_with_the_current_record(client):
    rid = ingest(client, "k1")
    stale = client.get(f"/records/{rid}").json()["hlc"]
    client.patch(f"/records/{rid}", json={"fields": {"note": "edited elsewhere"}})
    resp = client.delete(f"/records/{rid}", headers={"If-Match": stale})
    assert resp.status_code == 412
    detail = resp.json()["detail"]
    assert detail["yourHlc"] == stale
    assert detail["current"]["body"]["note"] == "edited elsewhere"
    assert client.get(f"/records/{rid}").status_code == 200


def test_delete_without_if_match_behaves_as_it_always_did(client):
    rid = ingest(client, "k1")
    client.patch(f"/records/{rid}", json={"fields": {"note": "edited"}})
    assert client.delete(f"/records/{rid}").status_code == 200
    assert client.get(f"/records/{rid}").status_code == 404


def test_delete_of_a_missing_record_is_404_with_or_without_if_match(client):
    assert client.delete("/records/nope").status_code == 404
    assert client.delete("/records/nope", headers={"If-Match": "x"}).status_code == 404


def test_a_refused_delete_writes_nothing_to_the_change_feed(client):
    rid = ingest(client, "k1")
    before = len(client.get("/changes").json()["changes"])
    client.delete(f"/records/{rid}", headers={"If-Match": "0000000000000-00000-other"})
    assert len(client.get("/changes").json()["changes"]) == before
