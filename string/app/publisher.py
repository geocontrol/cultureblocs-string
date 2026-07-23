"""Server-side publishing: strands from the String to an ATProto repo.

The same Stage F pipeline as scripts/promote.py, running inside the
service so the timeline can publish with one click using a held
identity. Strip rules are identical: geo, provenance and media never
leave; place names, notes, tags, links, works survive.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request

STRAND = "com.cultureblocs.strand"
BEAD_TYPES = ("com.cultureblocs.bead", "com.cultureblocs.annotation")


def _xrpc(pds: str, method: str, *, body: dict | None = None,
          token: str | None = None) -> dict:
    url = f"{pds.rstrip('/')}/xrpc/{method}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def strip_bead(body: dict) -> dict:
    out = {"$type": body["$type"]}
    for k in ("createdAt", "kind", "note", "tags", "links", "work"):
        if k in body:
            out[k] = body[k]
    subj = body.get("subject")
    if isinstance(subj, dict) and subj.get("name"):
        out["subject"] = {"name": subj["name"]}
    return out


def strip_strand(body: dict, items: list[dict]) -> dict:
    out = {"$type": body["$type"]}
    for k in ("createdAt", "title", "narrative", "day", "links"):
        if k in body:
            out[k] = body[k]
    place = body.get("place")
    if isinstance(place, dict) and place.get("name"):
        out["place"] = {"name": place["name"]}
    out["items"] = items
    return out


def content_hash(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _login(identity: dict) -> tuple[str, str, str]:
    s = _xrpc(identity["pds"], "com.atproto.server.createSession",
              body={"identifier": identity["handle"],
                    "password": identity["app_password"]})
    return s["did"], s["accessJwt"], identity["pds"]


def publish_strand(store, strand_id: str, identity: dict) -> dict:
    strand = store.get(strand_id)
    if strand is None or strand["type"] != STRAND:
        raise ValueError("not a strand")
    did, jwt, pds = _login(identity)
    published = []
    item_refs = []
    for it in (strand["body"].get("items") or []):
        rid = it["uri"].replace("spine://records/", "")
        rec = store.get(rid)
        if rec is None or rec["type"] not in BEAD_TYPES:
            continue
        stripped = strip_bead(rec["body"])
        res = _xrpc(pds, "com.atproto.repo.putRecord", token=jwt, body={
            "repo": did, "collection": rec["type"], "rkey": rid,
            "record": stripped})
        store.set_published(rid, res["uri"], content_hash(stripped))
        item_refs.append({"uri": res["uri"], "cid": res["cid"]})
        published.append(res["uri"])
    stripped_strand = strip_strand(strand["body"], item_refs)
    res = _xrpc(pds, "com.atproto.repo.putRecord", token=jwt, body={
        "repo": did, "collection": STRAND, "rkey": strand_id,
        "record": stripped_strand})
    store.set_published(strand_id, res["uri"], content_hash(stripped_strand))
    published.append(res["uri"])
    return {"identity": identity["name"], "handle": identity["handle"],
            "did": did, "records": published, "strandUri": res["uri"]}


def unpublish_strand(store, strand_id: str, identity: dict) -> dict:
    strand = store.get(strand_id)
    if strand is None or strand["type"] != STRAND:
        raise ValueError("not a strand")
    did, jwt, pds = _login(identity)
    removed = 0
    for it in (strand["body"].get("items") or []):
        rid = it["uri"].replace("spine://records/", "")
        rec = store.get(rid)
        if rec and rec.get("publishedUri"):
            coll = rec["publishedUri"].split("/")[-2]
            _xrpc(pds, "com.atproto.repo.deleteRecord", token=jwt, body={
                "repo": did, "collection": coll, "rkey": rid})
            store.set_published(rid, None, None)
            removed += 1
    if strand.get("publishedUri"):
        _xrpc(pds, "com.atproto.repo.deleteRecord", token=jwt, body={
            "repo": did, "collection": STRAND, "rkey": strand_id})
        store.set_published(strand_id, None, None)
        removed += 1
    return {"removed": removed}
