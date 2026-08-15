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


def _upload_blob(pds: str, token: str, data: bytes, mime: str) -> dict:
    req = urllib.request.Request(
        f"{pds.rstrip('/')}/xrpc/com.atproto.repo.uploadBlob",
        data=data, method="POST",
        headers={"Content-Type": mime, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["blob"]


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


def strip_bead(body: dict, *, images: list | None = None) -> dict:
    """Public subset. Local `media` refs never publish; if the caller has
    uploaded them, they arrive as `images` — imageRefs carrying the blob plus
    the alt text and dimensions from the local record."""
    out = {"$type": body["$type"]}
    for k in ("createdAt", "kind", "note", "tags", "links", "work"):
        if k in body:
            out[k] = body[k]
    subj = body.get("subject")
    if isinstance(subj, dict) and subj.get("name"):
        out["subject"] = {"name": subj["name"]}
    if images:
        out["images"] = images
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


def _rkey_for(rec: dict, fallback: str) -> str:
    """Which key to write under.

    A record that already has a published twin keeps that twin's rkey, so
    re-publishing after an edit updates the public record in place instead
    of leaving an orphan beside it. This matters for beads that were born
    on the network — minted on a phone, imported here later — whose rkey
    was assigned elsewhere and is not our record id.
    """
    uri = rec.get("publishedUri")
    if uri:
        return uri.rsplit("/", 1)[-1]
    return fallback


def _login(identity: dict) -> tuple[str, str, str]:
    s = _xrpc(identity["pds"], "com.atproto.server.createSession",
              body={"identifier": identity["handle"],
                    "password": identity["app_password"]})
    return s["did"], s["accessJwt"], identity["pds"]


MIME_BY_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".gif": "image/gif", ".heic": "image/heic"}


def _valid_aspect_ratio(ar) -> dict | None:
    """Only publish dimensions we can trust. A half-specified or non-integer
    ratio is worse than none: a reader would size a box wrongly and shift the
    page anyway."""
    if not isinstance(ar, dict):
        return None
    w, h = ar.get("width"), ar.get("height")
    for v in (w, h):
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            return None
    return {"width": w, "height": h}


def _image_refs(rec_body: dict, media_dir, pds: str, jwt: str) -> list:
    """Upload a record's local media files and return them as `imageRef`s.

    Alt text and dimensions are carried across from the local `mediaRef`
    rather than derived here: the surface that attached the image had a
    decoded bitmap in hand, and this process has only bytes on disk. Anything
    missing or oversized is skipped rather than failing the publish.
    """
    import pathlib
    refs = []
    if media_dir is None:
        return refs
    for m in (rec_body.get("media") or []):
        name = (m.get("uri") or "").split("/")[-1]
        path = pathlib.Path(media_dir) / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if len(data) > 2_000_000:      # lexicon maxSize; resize upstream someday
            continue
        mime = m.get("mime") or MIME_BY_EXT.get(path.suffix.lower(),
                                                "application/octet-stream")
        ref = {"image": _upload_blob(pds, jwt, data, mime)}
        alt = m.get("alt")
        if isinstance(alt, str) and alt.strip():
            ref["alt"] = alt.strip()
        ar = _valid_aspect_ratio(m.get("aspectRatio"))
        if ar:
            ref["aspectRatio"] = ar
        refs.append(ref)
    return refs


PUBLIC_TYPES = ("com.cultureblocs.creative.profile", "com.cultureblocs.creative.work",
                "com.cultureblocs.creative.connection", "com.cultureblocs.venue.profile",
                "com.cultureblocs.venue.lineup", "com.cultureblocs.venue.listing",
                "community.lexicon.calendar.event", "community.lexicon.calendar.rsvp")

SELF_KEYED = ("com.cultureblocs.creative.profile", "com.cultureblocs.venue.profile")


def strip_public(body: dict) -> dict:
    """Records that are public by intent (creative claims, venue listings).

    These are written to be read by strangers, so the body publishes as
    authored — minus local-only machinery: provenance (device/app internals)
    and `media` refs that point at files on the author's own String. A venue's
    address and coordinates are the point of the record and stay.
    """
    return {k: v for k, v in body.items() if k not in ("provenance", "media")}


def publish_record(store, record_id: str, identity: dict) -> dict:
    """Publish a single non-strand record under a held identity."""
    rec = store.get(record_id)
    if rec is None:
        raise ValueError("not found")
    if rec["type"] not in PUBLIC_TYPES:
        raise ValueError(f"{rec['type']} is not publishable on its own; "
                         "beads and annotations publish as part of a strand")
    did, jwt, pds = _login(identity)
    stripped = strip_public(rec["body"])
    rkey = ("self" if rec["type"] in SELF_KEYED
            else _rkey_for(rec, record_id))
    res = _xrpc(pds, "com.atproto.repo.putRecord", token=jwt, body={
        "repo": did, "collection": rec["type"], "rkey": rkey, "record": stripped})
    store.set_published(record_id, res["uri"], content_hash(stripped))
    return {"identity": identity["name"], "handle": identity["handle"],
            "did": did, "records": [res["uri"]], "uri": res["uri"]}


def unpublish_record(store, record_id: str, identity: dict) -> dict:
    rec = store.get(record_id)
    if rec is None or not rec.get("publishedUri"):
        return {"removed": 0}
    did, jwt, pds = _login(identity)
    parts = rec["publishedUri"].split("/")
    _xrpc(pds, "com.atproto.repo.deleteRecord", token=jwt, body={
        "repo": did, "collection": parts[-2], "rkey": parts[-1]})
    store.set_published(record_id, None, None)
    return {"removed": 1}


def publish_strand(store, strand_id: str, identity: dict,
                   media_dir=None) -> dict:
    strand = store.get(strand_id)
    if strand is None:
        raise ValueError("not found")
    if strand["type"] != STRAND:
        return publish_record(store, strand_id, identity)
    did, jwt, pds = _login(identity)
    published = []
    item_refs = []
    for it in (strand["body"].get("items") or []):
        rid = it["uri"].replace("spine://records/", "")
        rec = store.get(rid)
        if rec is None or rec["type"] not in BEAD_TYPES:
            continue
        images = _image_refs(rec["body"], media_dir, pds, jwt)
        stripped = strip_bead(rec["body"], images=images)
        res = _xrpc(pds, "com.atproto.repo.putRecord", token=jwt, body={
            "repo": did, "collection": rec["type"],
            "rkey": _rkey_for(rec, rid), "record": stripped})
        store.set_published(rid, res["uri"], content_hash(stripped))
        item_refs.append({"uri": res["uri"], "cid": res["cid"]})
        published.append(res["uri"])
    stripped_strand = strip_strand(strand["body"], item_refs)
    res = _xrpc(pds, "com.atproto.repo.putRecord", token=jwt, body={
        "repo": did, "collection": STRAND,
        "rkey": _rkey_for(strand, strand_id), "record": stripped_strand})
    store.set_published(strand_id, res["uri"], content_hash(stripped_strand))
    published.append(res["uri"])
    return {"identity": identity["name"], "handle": identity["handle"],
            "did": did, "records": published, "strandUri": res["uri"]}


def unpublish_strand(store, strand_id: str, identity: dict) -> dict:
    strand = store.get(strand_id)
    if strand is None:
        raise ValueError("not found")
    if strand["type"] != STRAND:
        return unpublish_record(store, strand_id, identity)
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
