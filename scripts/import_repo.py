#!/usr/bin/env python3
"""Bring records published on the network back into your String.

Beads minted on a phone are born public: written straight to your own
ATProto repository, with no private original anywhere. This pulls them
back so the desk tools can do what the phone deliberately cannot —
annotate, attach photos, group into strands — and re-publishing after an
edit updates the same public record rather than making a second one.

    python scripts/import_repo.py --actor you.bsky.social
    python scripts/import_repo.py --actor you.bsky.social --dry-run
    python scripts/import_repo.py --actor you.bsky.social --since 2026-08-01

Imported records keep their public identity: dedupeKey is the at:// URI
(so re-running imports nothing twice) and publishedUri/publishedHash are
set, which is what makes the round trip work — the timeline shows the
published chip, and `promote.py status` reports drift once you edit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

COLLECTIONS = ["com.cultureblocs.bead", "com.cultureblocs.annotation",
               "com.cultureblocs.strand", "com.cultureblocs.creative.profile",
               "com.cultureblocs.creative.work",
               "com.cultureblocs.creative.connection",
               "com.cultureblocs.venue.profile", "com.cultureblocs.venue.lineup",
               "community.lexicon.calendar.event"]
PUBLIC_API = "https://public.api.bsky.app/xrpc"


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def resolve(actor: str) -> tuple[str, str]:
    did = actor
    if not actor.startswith("did:"):
        try:
            did = get(f"{PUBLIC_API}/com.atproto.identity.resolveHandle"
                      f"?handle={urllib.parse.quote(actor)}")["did"]
        except Exception:
            dns = get("https://dns.google/resolve?name="
                      f"{urllib.parse.quote('_atproto.' + actor)}&type=TXT")
            did = next((a["data"].strip('"')[4:] for a in dns.get("Answer", [])
                        if a["data"].strip('"').startswith("did=")), None)
            if not did:
                sys.exit(f"could not resolve {actor}")
    doc = get(f"https://plc.directory/{did}") if did.startswith("did:plc:") else \
        get(f"https://{did[8:].replace(':', '/')}/.well-known/did.json")
    pds = next(s["serviceEndpoint"] for s in doc["service"]
               if s["id"].endswith("#atproto_pds"))
    return did, pds


def content_hash(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--actor", required=True, help="handle or DID")
    p.add_argument("--since", help="only records createdAt >= this (ISO date)")
    p.add_argument("--collections", help="comma separated; default all ours")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--string", "--spine",
                   default=os.environ.get("STRING_URL")
                   or os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN")
                   or os.environ.get("SPINE_TOKEN"))
    args = p.parse_args()

    did, pds = resolve(args.actor)
    print(f"{args.actor} -> {did}\n  pds: {pds}")
    wanted = ([c.strip() for c in args.collections.split(",")]
              if args.collections else COLLECTIONS)

    records, skipped = [], 0
    for coll in wanted:
        cursor = None
        while True:
            q = {"repo": did, "collection": coll, "limit": 100}
            if cursor:
                q["cursor"] = cursor
            try:
                page = get(f"{pds}/xrpc/com.atproto.repo.listRecords?"
                           + urllib.parse.urlencode(q))
            except Exception:
                break
            for r in page.get("records", []):
                v = r["value"]
                if args.since and (v.get("createdAt") or "") < args.since:
                    skipped += 1
                    continue
                records.append({
                    "dedupeKey": f"atproto:{r['uri']}",
                    "type": coll,
                    "sourceApp": "import",
                    "createdAt": v.get("createdAt") or v.get("startsAt"),
                    "body": v,
                    "_uri": r["uri"], "_cid": r.get("cid"),
                })
            cursor = page.get("cursor")
            if not cursor or not page.get("records"):
                break

    if not records:
        print("nothing to import" + (f" ({skipped} older than --since)" if skipped else ""))
        return
    by_coll: dict[str, int] = {}
    for r in records:
        by_coll[r["type"]] = by_coll.get(r["type"], 0) + 1
    for k, v in sorted(by_coll.items()):
        print(f"  {k}: {v}")
    if args.dry_run:
        print(f"({len(records)} records; dry run, nothing written)")
        return

    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    payload = [{k: v for k, v in r.items() if not k.startswith("_")}
               for r in records]
    req = urllib.request.Request(
        args.string.rstrip("/") + "/records",
        data=json.dumps({"records": payload}).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        results = json.loads(r.read())["results"]

    created = dupes = invalid = 0
    for res, src in zip(results, records):
        if res["status"] == "invalid":
            invalid += 1
            print(f"  invalid {src['_uri']}: {res['problems']}")
            continue
        if res["status"] == "duplicate":
            dupes += 1
        else:
            created += 1
        # remember the public twin so edits re-publish in place
        body = json.dumps({"uri": src["_uri"],
                           "hash": content_hash(src["body"])}).encode()
        link = urllib.request.Request(
            args.string.rstrip("/") + f"/records/{res['id']}/published",
            data=body, headers=headers, method="POST")
        try:
            urllib.request.urlopen(link, timeout=15)
        except Exception as exc:
            print(f"  note: could not link {res['id']}: {exc}")
    print(f"{created} imported, {dupes} already held, {invalid} invalid")
    if created:
        print("edit them in the timeline; re-publish updates the same public record")


if __name__ == "__main__":
    main()
