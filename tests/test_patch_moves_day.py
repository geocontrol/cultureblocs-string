"""Correcting a record's time with PATCH moves it to the right day: the
String's created_at (which /days and day listings read) follows the body."""
MON = "2026-10-26T20:00:00Z"
SAT = "2026-10-24T20:00:00Z"
BEAD = "com.cultureblocs.bead"
STRAND = "com.cultureblocs.strand"


def ingest(client, rtype: str, body: dict, key: str) -> str:
    res = client.post("/records", json={"records": [{
        "dedupeKey": key, "type": rtype, "sourceApp": "test", "createdAt": MON,
        "body": {"$type": rtype, "createdAt": MON, **body}}]})
    assert res.status_code == 200, res.text
    out = res.json()["results"][0]
    assert out["status"] == "created", out
    return out["id"]


def test_patching_a_beads_createdAt_moves_it_to_that_day(client):
    rid = ingest(client, BEAD, {"kind": "performance", "note": "Autechre"}, "autechre")
    res = client.patch(f"/records/{rid}", json={"fields": {"createdAt": SAT}})
    assert res.status_code == 200, res.text
    rec = client.get(f"/records/{rid}").json()
    assert rec["createdAt"] == SAT
    days = {d["day"] for d in client.get("/days").json()["days"]}
    assert "2026-10-24" in days and "2026-10-26" not in days


def test_patching_a_strand_keeps_its_created_at(client):
    rid = ingest(client, STRAND, {"title": "Saturday", "day": "2026-10-24T00:00:00Z", "items": []}, "strand")
    res = client.patch(f"/records/{rid}", json={"fields": {"title": "retitled", "createdAt": "2026-10-29T09:00:00Z"}})
    assert res.status_code == 200, res.text
    assert client.get(f"/records/{rid}").json()["createdAt"] == MON
