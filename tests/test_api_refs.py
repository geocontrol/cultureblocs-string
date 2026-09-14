"""Ingest and PATCH run the refs checks the lexicon cannot express, and
mirror an annotation's `work` into a subject ref."""
T = "2026-08-15T21:04:00Z"


def ingest(client, rtype: str, body: dict, key: str = "k1") -> dict:
    res = client.post("/records", json={"records": [{
        "dedupeKey": key, "type": rtype, "sourceApp": "test", "createdAt": T,
        "body": {"$type": rtype, "createdAt": T, **body}}]})
    assert res.status_code == 200, res.text
    return res.json()["results"][0]


def test_annotation_work_is_mirrored_on_ingest(client):
    out = ingest(client, "com.cultureblocs.annotation", {"work": {"title": "Gasholder"}})
    assert out["status"] == "created", out
    stored = client.get(f"/records/{out['id']}").json()["body"]
    assert stored["refs"] == [
        {"type": "work", "role": "subject", "descriptor": {"label": "Gasholder"}}]


def test_anchor_outside_the_note_is_rejected(client):
    out = ingest(client, "com.cultureblocs.bead", {
        "kind": "watch", "note": "Severance",
        "refs": [{"type": "work", "role": "subject", "descriptor": {"label": "Severance"},
                  "index": {"byteStart": 0, "byteEnd": 99}}]})
    assert out["status"] == "invalid"
    assert out["problems"] == ["$.refs[0].index: 0..99 is outside note (9 bytes)"]


def test_patch_that_shortens_the_text_under_an_anchor_is_rejected(client):
    out = ingest(client, "com.cultureblocs.bead", {
        "kind": "watch", "note": "Saw Severance",
        "refs": [{"type": "work", "role": "subject", "descriptor": {"label": "Severance"},
                  "index": {"byteStart": 4, "byteEnd": 13}}]})
    res = client.patch(f"/records/{out['id']}", json={"fields": {"note": "Saw it"}})
    assert res.status_code == 422
    assert res.json()["detail"] == ["$.refs[0].index: 4..13 is outside note (6 bytes)"]


def test_patching_an_annotation_backfills_its_subject_ref(client):
    out = ingest(client, "com.cultureblocs.annotation", {
        "work": {"title": "Gasholder"},
        "refs": [{"type": "work", "role": "subject", "descriptor": {"label": "Gasholder"}}]})
    res = client.patch(f"/records/{out['id']}", json={"fields": {"refs": []}})
    assert res.status_code == 200, res.text
    assert res.json()["body"]["refs"] == [
        {"type": "work", "role": "subject", "descriptor": {"label": "Gasholder"}}]
