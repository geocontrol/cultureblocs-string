"""Phase 0 through the HTTP surface — the shapes clients actually see."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))

BEAD = "com.cultureblocs.bead"


def bead(note="a note"):
    return {"$type": BEAD, "createdAt": "2026-08-15T21:04:00Z", "kind": "listen", "note": note}


def ingest(client, key, note="a note", state=None, app_name="scrobbler", **kw):
    rec = {"dedupeKey": key, "type": BEAD, "sourceApp": app_name,
           "createdAt": "2026-08-15T21:04:00Z", "body": bead(note)}
    if state:
        rec["state"] = state
    return client.post("/records", json={"records": [rec]}, **kw).json()["results"][0]


def test_a_record_reports_its_state_and_stamp(client):
    r = ingest(client, "k1")
    rec = client.get(f"/records/{r['id']}").json()
    assert rec["state"] == "kept"
    assert rec["hlc"]


def test_the_scrobbler_cycle_propose_revise_keep_refuse(client):
    first = ingest(client, "scrobble:me:1", "8 tracks", state="proposal")
    assert first["status"] == "created"

    revised = ingest(client, "scrobble:me:1", "11 tracks", state="proposal")
    assert revised["status"] == "updated"
    assert client.get(f"/records/{first['id']}").json()["body"]["note"] == "11 tracks"

    kept = client.post(f"/records/{first['id']}/state", json={"state": "kept"})
    assert kept.status_code == 200 and kept.json()["state"] == "kept"

    again = ingest(client, "scrobble:me:1", "the machine tries again", state="proposal")
    assert again["status"] == "duplicate"
    assert client.get(f"/records/{first['id']}").json()["body"]["note"] == "11 tracks"


def test_a_patched_proposal_survives_the_next_connector_run(client):
    first = ingest(client, "scrobble:me:1", "8 tracks", state="proposal")
    edited = client.patch(f"/records/{first['id']}",
                          json={"fields": {"note": "the one where it rained"}})
    assert edited.status_code == 200 and edited.json()["state"] == "kept"

    again = ingest(client, "scrobble:me:1", "8 tracks", state="proposal")
    assert again["status"] == "duplicate"
    rec = client.get(f"/records/{first['id']}").json()
    assert rec["body"]["note"] == "the one where it rained" and rec["state"] == "kept"


def test_records_can_be_filtered_by_state(client):
    ingest(client, "a", state="proposal")
    ingest(client, "b", app_name="pocket")
    assert len(client.get("/records?state=proposal").json()["records"]) == 1
    assert len(client.get("/records").json()["records"]) == 2


def test_an_unknown_state_is_rejected_at_ingest(client):
    r = ingest(client, "k1", state="vibes")
    assert r["status"] == "invalid" and "unknown state" in r["problems"][0]


def test_an_unknown_state_is_rejected_on_transition(client):
    r = ingest(client, "k1")
    assert client.post(f"/records/{r['id']}/state", json={"state": "vibes"}).status_code == 422


def test_state_on_a_missing_record_is_404(client):
    assert client.post("/records/nope/state", json={"state": "kept"}).status_code == 404


def test_if_match_rejects_a_stale_edit_and_hands_back_the_current_record(client):
    r = ingest(client, "k1")
    stale = client.get(f"/records/{r['id']}").json()["hlc"]
    client.patch(f"/records/{r['id']}", json={"fields": {"note": "from the desk"}})

    resp = client.patch(f"/records/{r['id']}", json={"fields": {"note": "from the phone"}},
                        headers={"If-Match": stale})
    assert resp.status_code == 412
    detail = resp.json()["detail"]
    assert detail["yourHlc"] == stale
    assert detail["current"]["body"]["note"] == "from the desk"
    assert client.get(f"/records/{r['id']}").json()["body"]["note"] == "from the desk"


def test_if_match_accepts_the_current_stamp_and_quoted_forms(client):
    r = ingest(client, "k1")
    current = client.get(f"/records/{r['id']}").json()["hlc"]
    resp = client.patch(f"/records/{r['id']}", json={"fields": {"note": "ok"}},
                        headers={"If-Match": f'"{current}"'})
    assert resp.status_code == 200 and resp.json()["body"]["note"] == "ok"


def test_a_patch_without_if_match_still_wins_as_it_always_did(client):
    r = ingest(client, "k1")
    assert client.patch(f"/records/{r['id']}",
                        json={"fields": {"note": "unconditional"}}).status_code == 200


def test_the_change_feed_names_the_device_that_wrote_each_row(client):
    ingest(client, "k1", headers={"X-Device-Id": "phone"})
    changes = client.get("/changes").json()["changes"]
    assert changes[0]["deviceId"] == "phone"
    assert changes[0]["actor"] == "local"      # no token set in this fixture
    assert changes[0]["hlc"]


def test_validation_still_precedes_everything(client):
    r = client.post("/records", json={"records": [{
        "dedupeKey": "bad", "type": BEAD, "sourceApp": "pocket",
        "createdAt": "2026-08-15T21:04:00Z",
        "body": {"$type": BEAD, "createdAt": "not a date", "kind": "listen"}}]})
    assert r.json()["results"][0]["status"] == "invalid"
