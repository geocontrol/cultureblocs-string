"""POST /import/pds — the round trip for born-public beads.

The network is a fake: a dict of collection -> records, served through
pds_import._get, so nothing here leaves the machine.
"""
import pytest

DID = "did:plc:mark"
PDS = "https://pds.example"
EVENT = "at://did:plc:cultureblocs/community.lexicon.calendar.event/frieze"


def went_bead(note="Great booths", rkey="3lwent"):
    return {"uri": f"at://{DID}/com.cultureblocs.bead/{rkey}", "cid": "bafy" + rkey,
            "value": {"$type": "com.cultureblocs.bead", "kind": "visit",
                      "createdAt": "2026-10-16T12:00:00.000Z", "note": note,
                      "subject": {"$type": "com.cultureblocs.defs#strongRef", "uri": EVENT, "cid": "bafyevent"},
                      "provenance": {"app": "com.cultureblocs.went", "mintedAt": "2026-10-16T12:01:00.000Z",
                                     "timeAnchored": False}}}


@pytest.fixture
def net(client, monkeypatch):
    import app.pds_import as pds_import
    repo = {"com.cultureblocs.bead": [], "com.cultureblocs.annotation": [], "com.cultureblocs.strand": []}

    def fake_get(url):
        if "resolveHandle" in url:
            return {"did": DID}
        if url.startswith("https://plc.directory/"):
            return {"service": [{"id": "#atproto_pds", "serviceEndpoint": PDS}]}
        if "listRecords" in url:
            coll = next(c for c in repo if f"collection={c}&" in url or url.endswith(f"collection={c}"))
            return {"records": repo[coll]}
        raise AssertionError(f"unexpected fetch {url}")

    monkeypatch.setattr(pds_import, "_get", fake_get)
    client.put("/identities/mark", json={"handle": "mark.example", "appPassword": "x", "pds": "https://bsky.social"})
    return repo


def run(client, **kw):
    r = client.post("/import/pds", json={"identity": "mark", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_born_public_bead_arrives_kept_and_published(client, net):
    net["com.cultureblocs.bead"].append(went_bead())
    out = run(client)
    assert out["did"] == DID and out["pds"] == PDS
    assert out["counts"]["created"] == 1
    rec = client.get(f"/records/{out['created'][0]['id']}").json()
    assert rec["state"] == "kept"
    assert rec["publishedUri"] == went_bead()["uri"]
    assert rec["sourceApp"] == "com.cultureblocs.went"
    assert rec["body"]["subject"]["uri"] == EVENT


def test_rerunning_imports_nothing_twice(client, net):
    net["com.cultureblocs.bead"].append(went_bead())
    run(client)
    out = run(client)
    assert out["counts"]["created"] == 0 and out["counts"]["unchanged"] == 1
    assert len(client.get("/records", params={"type": "com.cultureblocs.bead"}).json()["records"]) == 1


def test_a_bead_the_string_published_is_not_imported_again(client, net):
    created = client.post("/records", json={"records": [{
        "dedupeKey": "loom:abc", "type": "com.cultureblocs.bead", "sourceApp": "loom",
        "createdAt": "2026-10-16T12:00:00Z",
        "body": {"$type": "com.cultureblocs.bead", "kind": "note", "createdAt": "2026-10-16T12:00:00Z",
                 "note": "mine", "provenance": {"app": "loom", "mintedAt": "2026-10-16T12:00:00Z"}}}]}).json()
    rid = created["results"][0]["id"]
    from app.strip import drift_hash
    import app.main as main
    body = main.store.get(rid)["body"]
    uri = f"at://{DID}/com.cultureblocs.bead/{rid}"
    main.store.set_published(rid, uri, drift_hash(body))
    from app.strip import strip_bead
    net["com.cultureblocs.bead"].append({"uri": uri, "cid": "bafy", "value": strip_bead(body)})
    out = run(client)
    assert out["counts"]["own"] == 1 and out["counts"]["created"] == 0


def test_an_edit_made_on_the_network_refreshes_an_unedited_copy(client, net):
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    net["com.cultureblocs.bead"][0] = went_bead("second thoughts")
    out = run(client)
    assert out["counts"]["refreshed"] == 1
    rec = client.get(f"/records/{rid}").json()
    assert rec["body"]["note"] == "second thoughts"
    assert rec["body"]["provenance"]["app"] == "com.cultureblocs.went"   # private fields kept
    assert run(client)["counts"]["unchanged"] == 1                         # and not drifted


def test_edited_on_both_sides_is_a_conflict_left_alone(client, net):
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    client.patch(f"/records/{rid}", json={"fields": {"note": "edited in Loom"}})
    net["com.cultureblocs.bead"][0] = went_bead("edited on the site")
    out = run(client)
    assert out["counts"]["conflict"] == 1
    assert client.get(f"/records/{rid}").json()["body"]["note"] == "edited in Loom"


def test_edited_here_only_is_waiting_for_a_republish_not_a_conflict(client, net):
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    client.patch(f"/records/{rid}", json={"fields": {"note": "edited in Loom"}})
    out = run(client)
    assert out["counts"]["conflict"] == 0 and out["counts"]["unchanged"] == 1


def test_dry_run_writes_nothing(client, net):
    net["com.cultureblocs.bead"].append(went_bead())
    out = run(client, dryRun=True)
    assert out["counts"]["created"] == 1
    assert client.get("/records").json()["records"] == []


def test_strands_are_counted_not_imported(client, net):
    net["com.cultureblocs.strand"].append({"uri": f"at://{DID}/com.cultureblocs.strand/s", "value": {
        "$type": "com.cultureblocs.strand", "createdAt": "2026-10-16T00:00:00Z", "items": []}})
    out = run(client)
    assert out["counts"]["strands"] == 1 and out["counts"]["created"] == 0


def test_since_skips_older_records(client, net):
    net["com.cultureblocs.bead"].append(went_bead())
    out = run(client, since="2026-10-17")
    assert out["counts"]["older"] == 1 and out["counts"]["created"] == 0


def test_unknown_identity_is_404(client, net):
    assert client.post("/import/pds", json={"identity": "nobody"}).status_code == 404


def test_republishing_keeps_the_event_subject(client, net, monkeypatch):
    """The strip used to reduce `subject` to a name, so an "I went" bead lost its event."""
    from app.strip import strip_bead
    out = strip_bead(went_bead()["value"])
    assert out["subject"] == {"$type": "com.cultureblocs.defs#strongRef", "uri": EVENT, "cid": "bafyevent"}
    assert "provenance" not in out


def test_republishing_a_born_public_bead_keeps_its_photos(monkeypatch):
    import app.publisher as publisher
    images = [{"image": {"$type": "blob", "ref": {"$link": "bafyimg"}, "mimeType": "image/jpeg", "size": 10}}]
    rec = {"publishedUri": f"at://{DID}/com.cultureblocs.bead/x", "body": {"images": images}}
    assert publisher._born_public_images(rec, DID) == images
    assert publisher._born_public_images(rec, "did:plc:someone-else") == []


def test_a_refresh_keeps_what_the_strip_withheld(client, net):
    """Review finding: refreshing from the stripped network copy must not erase private parts."""
    import app.main as main
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    # Locally: a place with coordinates, and a private person ref — both withheld by the strip.
    rec = main.store.get(rid)
    body = {**rec["body"], "subject": {"name": "Regent's Park", "geo": {"lat": 51.53, "lng": -0.15, "precision": "exact"}},
            "refs": [{"type": "person", "role": "mention", "descriptor": {"label": "Mum"}}]}
    main.store.patch(rid, {"subject": body["subject"], "refs": body["refs"]})
    from app.strip import drift_hash
    main.store.set_published(rid, rec["publishedUri"], drift_hash(body))
    # On the network: the same public subject, a new note.
    edited = went_bead("second thoughts")
    edited["value"]["subject"] = {"name": "Regent's Park"}
    net["com.cultureblocs.bead"][0] = edited
    out = run(client)
    assert out["counts"]["refreshed"] == 1, (out["counts"], out["invalid"])
    after = main.store.get(rid)["body"]
    assert after["note"] == "second thoughts"
    assert after["subject"]["geo"]["lat"] == 51.53
    assert after["refs"] == [{"type": "person", "role": "mention", "descriptor": {"label": "Mum"}}]


def test_a_photo_added_on_the_network_after_an_edit_here_is_a_conflict(client, net):
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    client.patch(f"/records/{rid}", json={"fields": {"note": "edited in Loom"}})
    with_photo = went_bead("first")
    with_photo["value"]["images"] = [{"image": {"$type": "blob", "ref": {"$link": "bafyimg"}, "mimeType": "image/jpeg", "size": 10}}]
    net["com.cultureblocs.bead"][0] = with_photo
    assert run(client)["counts"]["conflict"] == 1


def test_a_refresh_never_lands_on_a_version_it_did_not_plan_against(client, net, monkeypatch):
    import app.main as main
    import app.pds_import as pds_import
    net["com.cultureblocs.bead"].append(went_bead("first"))
    rid = run(client)["created"][0]["id"]
    net["com.cultureblocs.bead"][0] = went_bead("from the site")
    real = main.store.by_published_uri

    def racing(uri):
        held = real(uri)
        main.store.patch(rid, {"note": "a Loom edit arriving mid-import"})   # lands after the read
        return held
    monkeypatch.setattr(main.store, "by_published_uri", racing)
    out = run(client)
    assert out["counts"]["conflict"] == 1 and out["counts"]["refreshed"] == 0
    assert main.store.get(rid)["body"]["note"] == "a Loom edit arriving mid-import"


def test_republishing_with_a_new_local_photo_keeps_the_born_public_ones(monkeypatch):
    import app.publisher as publisher
    born = [{"image": {"$type": "blob", "ref": {"$link": "bafyold"}, "mimeType": "image/jpeg", "size": 10}}]
    store_rec = {"id": "r1", "type": "com.cultureblocs.bead", "publishedUri": f"at://{DID}/com.cultureblocs.bead/x",
                 "body": {"$type": "com.cultureblocs.bead", "kind": "visit", "createdAt": "2026-10-16T12:00:00Z",
                          "images": born, "media": [{"uri": "/media/" + "a" * 64 + ".jpg"}]}}
    monkeypatch.setattr(publisher, "_image_refs", lambda *a, **k: [{"image": {"ref": {"$link": "bafynew"}}}])
    got = publisher._born_public_images(store_rec, DID) + publisher._image_refs(store_rec["body"], None, PDS, "jwt")
    assert [i["image"]["ref"]["$link"] for i in got] == ["bafyold", "bafynew"]


def test_the_change_feed_says_where_it_ends(client):
    assert client.get("/changes", params={"since": 99}).json()["latest"] == 0
    client.post("/records", json={"records": [{"dedupeKey": "x", "type": "com.cultureblocs.bead", "sourceApp": "t",
        "createdAt": "2026-10-16T12:00:00Z", "body": {"$type": "com.cultureblocs.bead", "kind": "note",
        "createdAt": "2026-10-16T12:00:00Z", "note": "n"}}]})
    out = client.get("/changes", params={"since": 0}).json()
    assert out["latest"] == out["cursor"] == 1
