#!/usr/bin/env python3
"""Export selected strands from the Spine as a public static bundle.

This is the Tier-2 promotion pipeline (snapshot -> privacy-strip ->
materialise) with a static site as the target instead of a PDS. The JSON
keeps records in com.cultureblocs.* lexicon shape, so the same web
component that renders this file can later render records fetched live
from a PDS — only the loader changes.

Usage:
    python scripts/export_public.py list
    python scripts/export_public.py export <strand-id> [<strand-id> ...] \
        --out /path/to/geekyoto/public/cultureblocs
    # options: --spine http://localhost:8100  --token X

Output:
    <out>/strands.json      strand + resolved item records (privacy-stripped)
    <out>/media/<hash>.<ext> copies of referenced images (content-addressed,
                             so re-exports are idempotent and cacheable)

Privacy strip (public web = strictest tier):
    - geo coordinates removed entirely (place *names* survive)
    - provenance removed (no device ids, mintIds, apps)
    - records not referenced by an exported strand never leave the Spine
The note text is published exactly as written — selection is consent.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STRAND = "com.cultureblocs.strand"


def api(base, path, token=None):
    req = urllib.request.Request(base.rstrip("/") + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def strip_item(body: dict) -> dict:
    """Public-safe subset of a bead/annotation body."""
    out = {}
    for k in ("$type", "createdAt", "kind", "note", "tags", "links", "work"):
        if k in body:
            out[k] = body[k]
    subj = body.get("subject")
    if isinstance(subj, dict) and subj.get("name"):
        out["subject"] = {"name": subj["name"]}          # name yes, geo no
    if body.get("media"):
        out["media"] = [{"uri": m["uri"], **({"alt": m["alt"]} if m.get("alt") else {})}
                        for m in body["media"]]
    return out


def strip_strand(body: dict) -> dict:
    out = {k: body[k] for k in ("$type", "createdAt", "title", "narrative", "day", "links")
           if k in body}
    place = body.get("place")
    if isinstance(place, dict) and place.get("name"):
        out["place"] = {"name": place["name"]}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["list", "export"])
    p.add_argument("strands", nargs="*", help="strand record ids to export")
    p.add_argument("--spine", default="http://localhost:8100")
    p.add_argument("--token")
    p.add_argument("--out", default="./public-export")
    p.add_argument("--media-src", default="./data/media",
                   help="Spine's media directory (for copying files)")
    args = p.parse_args()

    strands = api(args.spine, f"/records?type={STRAND}&limit=2000",
                  args.token)["records"]

    if args.cmd == "list":
        if not strands:
            print("no strands in the Spine yet")
        for s in strands:
            b = s["body"]
            print(f"{s['id']}  {b.get('day','')[:10]}  "
                  f"{b.get('title','(untitled)')}  "
                  f"[{len(b.get('items') or [])} items]")
        return

    if not args.strands:
        sys.exit("export needs at least one strand id (see: list)")

    chosen = [s for s in strands if s["id"] in set(args.strands)]
    missing = set(args.strands) - {s["id"] for s in chosen}
    if missing:
        sys.exit(f"not found: {', '.join(missing)}")

    out_dir = Path(args.out)
    media_out = out_dir / "media"
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle, copied = [], 0
    for s in chosen:
        items = []
        for it in (s["body"].get("items") or []):
            rid = it["uri"].replace("spine://records/", "")
            rec = api(args.spine, f"/records/{rid}", args.token)
            body = strip_item(rec["body"])
            # rewrite + copy media to the bundle
            for m in body.get("media", []):
                name = m["uri"].split("/")[-1]
                src = Path(args.media_src) / name
                if src.exists():
                    media_out.mkdir(parents=True, exist_ok=True)
                    dst = media_out / name
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied += 1
                m["uri"] = f"media/{name}"
            items.append(body)
        items.sort(key=lambda x: x.get("createdAt", ""))
        bundle.append({"strand": strip_strand(s["body"]), "items": items})

    bundle.sort(key=lambda x: x["strand"].get("createdAt", ""), reverse=True)
    doc = {"$type": "com.cultureblocs.export",
           "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "strands": bundle}
    (out_dir / "strands.json").write_text(json.dumps(doc, indent=1))
    print(f"wrote {out_dir/'strands.json'} "
          f"({len(bundle)} strands, {sum(len(b['items']) for b in bundle)} items, "
          f"{copied} media files copied)")


if __name__ == "__main__":
    main()
