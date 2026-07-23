#!/usr/bin/env python3
"""Mint a bead by hand — no totem, no device, just a deliberate note.

The missing entry path: totems, the AR app and the scrobbler all mint
beads, but some moments are typed. Announcements from the org account,
a thought worth keeping, a bead about an event you're organising.

Usage:
    python scripts/mint.py --note "Summer meetup announced" \
        --kind note --tags meetup,announcement \
        --place "Dragon Hall, Covent Garden" \
        --link https://luma.com/4083pmnh --link-title "Register on Luma"
Options:
    --kind      bloc|visit|dwell|encounter|read|listen|watch|
                screening|performance|note        (default: bloc)
    --time      ISO datetime (default: now, UTC)
    --spine URL --token TOKEN                     (or SPINE_URL/SPINE_TOKEN)

The bead lands in the Spine as sourceApp "mint-cli" with provenance.app
"manual" — a deliberate act, so it sits on the main thread, not the
machine rail. Group it into a strand in the timeline, then publish with
promote.py as usual.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--note", required=True)
    p.add_argument("--kind", default="bloc",
                   choices=["bloc", "visit", "dwell", "encounter", "read",
                            "listen", "watch", "screening", "performance", "note"])
    p.add_argument("--tags", default="", help="comma separated")
    p.add_argument("--place")
    p.add_argument("--link")
    p.add_argument("--link-title")
    p.add_argument("--time", help="ISO datetime; default now (UTC)")
    p.add_argument("--string", "--spine", dest="spine", default=os.environ.get("STRING_URL") or os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN"))
    args = p.parse_args()

    created = args.time or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    body = {
        "$type": "com.cultureblocs.bead",
        "createdAt": created,
        "kind": args.kind,
        "note": args.note,
        "provenance": {"app": "manual", "mintedAt": created, "timeAnchored": True},
    }
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if tags:
        body["tags"] = tags[:8]
    if args.place:
        body["subject"] = {"name": args.place}
    if args.link:
        link = {"uri": args.link}
        if args.link_title:
            link["title"] = args.link_title
        body["links"] = [link]

    record = {"dedupeKey": f"manual:{uuid.uuid4()}", "type": "com.cultureblocs.bead",
              "sourceApp": "mint-cli", "createdAt": created, "body": body}
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    req = urllib.request.Request(
        args.spine.rstrip("/") + "/records",
        data=json.dumps({"records": [record]}).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())["results"][0]
    if res["status"] == "invalid":
        sys.exit(f"rejected: {res['problems']}")
    print(f"minted ({res['status']}): {created}  {args.kind}  — now visible "
          f"in the timeline; group into a strand to publish")


if __name__ == "__main__":
    main()
