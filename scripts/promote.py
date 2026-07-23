#!/usr/bin/env python3
"""The promoter (Stage F): publish strands from the Spine to an ATProto repo.

Takes a strand you've told in the timeline, privacy-strips it, and writes it
into a real ATProto repository as signed public records — beads first, then
the strand referencing them by strongRef. The resulting at:// URIs are
written back into the Spine, so local records know their published twin
(the timeline shows a "published" chip) and edits can be detected later.

The Spine remains the source of truth. The published copy is the signed
press release about it. Unpublish deletes the public records and clears
the link; the local records are untouched.

Release-one scope:
  - Target: any PDS (default Bluesky-hosted), any account — use your
    PERSONAL account for personal strands (e.g. mark.geekyoto.com), the
    org account for org strands. See PROMOTER.md.
  - Media is NOT published yet (ATProto blobs need a lexicon evolution to
    reference correctly); photos stay on your static-site exports.
  - Idempotent: rkeys are the Spine record ids, so re-publishing after an
    edit overwrites in place.

Usage:
    python scripts/promote.py list
    BSKY_HANDLE=mark.geekyoto.com BSKY_APP_PASSWORD=... \
        python scripts/promote.py publish <strand-id> [...]
    python scripts/promote.py unpublish <strand-id>
    python scripts/promote.py status
Options: --pds URL  --spine URL  --token SPINE_TOKEN  --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

STRAND = "com.cultureblocs.strand"
BEAD_TYPES = ("com.cultureblocs.bead", "com.cultureblocs.annotation")


# ---------------- HTTP helpers ----------------
def http(url: str, *, body: dict | None = None, token: str | None = None,
         method: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def spine(args, path: str, **kw) -> dict:
    return http(args.spine.rstrip("/") + path, token=args.token, **kw)


def spine_writeback(args, path: str, **kw) -> bool:
    """Record published state in the Spine; never fatal. A publish that
    succeeded on the PDS must complete even if the Spine can't be told —
    re-running publish later repairs the link (idempotent rkeys)."""
    try:
        spine(args, path, **kw)
        return True
    except Exception as exc:
        print(f"  WARNING: spine write-back failed for {path}: {exc}\n"
              f"           (is the Spine running the latest build? "
              f"re-run publish after updating to repair)", file=sys.stderr)
        return False


def xrpc(args, method: str, *, params: dict | None = None,
         body: dict | None = None, token: str | None = None) -> dict:
    url = f"{args.pds.rstrip('/')}/xrpc/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return http(url, body=body, token=token)


# ---------------- privacy strip ----------------
def strip_bead(body: dict) -> dict:
    """Public subset of a bead/annotation. Same discipline as the static
    exporter: geo out, provenance out, media out (release one), device
    internals out. Place names, notes, tags, links, works survive."""
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
    out["items"] = items                       # strongRefs, filled at publish
    return out


def content_hash(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------- commands ----------------
def get_strands(args) -> list[dict]:
    return spine(args, f"/records?type={STRAND}&limit=2000")["records"]


def cmd_list(args) -> None:
    for s in get_strands(args):
        b = s["body"]
        mark = "published" if s.get("publishedUri") else "local    "
        print(f"{s['id']}  {mark}  {b.get('day','')[:10]}  "
              f"{b.get('title','(untitled)')}  [{len(b.get('items') or [])} items]")


def login(args) -> tuple[str, str]:
    handle = os.environ.get("BSKY_HANDLE")
    password = os.environ.get("BSKY_APP_PASSWORD")
    if not (handle and password):
        sys.exit("set BSKY_HANDLE and BSKY_APP_PASSWORD (an app password)")
    s = xrpc(args, "com.atproto.server.createSession",
             body={"identifier": handle, "password": password})
    print(f"authenticated as {s.get('handle', handle)} ({s['did']})")
    return s["did"], s["accessJwt"]


def cmd_publish(args) -> None:
    strands = {s["id"]: s for s in get_strands(args)}
    chosen = []
    for sid in args.ids:
        if sid not in strands:
            sys.exit(f"strand not found: {sid}")
        chosen.append(strands[sid])
    if args.dry_run:
        for s in chosen:
            print(f"would publish '{s['body'].get('title')}' "
                  f"({len(s['body'].get('items') or [])} items) as "
                  f"com.cultureblocs.* records, rkeys = spine ids")
        return
    did, jwt = login(args)
    for s in chosen:
        item_refs = []
        for it in (s["body"].get("items") or []):
            rid = it["uri"].replace("spine://records/", "")
            rec = spine(args, f"/records/{rid}")
            if rec["type"] not in BEAD_TYPES:
                continue
            stripped = strip_bead(rec["body"])
            res = xrpc(args, "com.atproto.repo.putRecord", token=jwt, body={
                "repo": did, "collection": rec["type"], "rkey": rid,
                "record": stripped})
            spine_writeback(args, f"/records/{rid}/published",
                            body={"uri": res["uri"], "hash": content_hash(stripped)})
            item_refs.append({"uri": res["uri"], "cid": res["cid"]})
            print(f"  bead  {res['uri']}")
        stripped_strand = strip_strand(s["body"], item_refs)
        res = xrpc(args, "com.atproto.repo.putRecord", token=jwt, body={
            "repo": did, "collection": STRAND, "rkey": s["id"],
            "record": stripped_strand})
        spine_writeback(args, f"/records/{s['id']}/published",
                        body={"uri": res["uri"], "hash": content_hash(stripped_strand)})
        print(f"  strand {res['uri']}")
        print(f"published: {s['body'].get('title')}")


def cmd_unpublish(args) -> None:
    strands = {s["id"]: s for s in get_strands(args)}
    did, jwt = login(args)
    for sid in args.ids:
        s = strands.get(sid)
        if not s or not s.get("publishedUri"):
            print(f"skip {sid}: not published")
            continue
        for it in (s["body"].get("items") or []):
            rid = it["uri"].replace("spine://records/", "")
            rec = spine(args, f"/records/{rid}")
            if rec.get("publishedUri"):
                coll = rec["publishedUri"].split("/")[-2]
                xrpc(args, "com.atproto.repo.deleteRecord", token=jwt, body={
                    "repo": did, "collection": coll, "rkey": rid})
                spine_writeback(args, f"/records/{rid}/published", method="DELETE")
        xrpc(args, "com.atproto.repo.deleteRecord", token=jwt, body={
            "repo": did, "collection": STRAND, "rkey": sid})
        spine_writeback(args, f"/records/{sid}/published", method="DELETE")
        print(f"unpublished: {s['body'].get('title')}")


def cmd_status(args) -> None:
    """Detect local edits since publication (hash drift)."""
    for s in get_strands(args):
        if not s.get("publishedUri"):
            continue
        drift = []
        for it in (s["body"].get("items") or []):
            rid = it["uri"].replace("spine://records/", "")
            rec = spine(args, f"/records/{rid}")
            if rec.get("publishedUri") and \
               content_hash(strip_bead(rec["body"])) != rec.get("publishedHash"):
                drift.append(rid)
        state = f"{len(drift)} beads edited since publish — re-publish to update" \
                if drift else "in sync"
        print(f"{s['id']}  {s['body'].get('title','')}  ·  {state}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["list", "publish", "unpublish", "status"])
    p.add_argument("ids", nargs="*")
    p.add_argument("--pds", default=os.environ.get("PDS_URL", "https://bsky.social"))
    p.add_argument("--string", "--spine", dest="spine", default=os.environ.get("STRING_URL") or os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--identity",
                   help="use an identity held by the String (server-side "
                        "publish; no BSKY_* env needed)")
    args = p.parse_args()
    if args.identity and args.cmd in ("publish", "unpublish"):
        for sid in args.ids:
            res = spine(args, f"/{args.cmd}/{sid}",
                        body={"identity": args.identity})
            print(f"{args.cmd}ed {sid}: {res}")
        return
    {"list": cmd_list, "publish": cmd_publish,
     "unpublish": cmd_unpublish, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
