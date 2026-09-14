#!/usr/bin/env python3
"""Add alt text and pixel dimensions to a bead's existing media entries.

Timeline captures alt text and aspectRatio when a photo is *attached*, and it
has no control for removing one — so beads whose photos predate those fields
have no route to them through the UI. This script is that route: it rewrites
each record's `media` array in place over the String's API, so nothing is
re-uploaded and no blob changes.

Dimensions are read from the JPEG/PNG/WebP header in pure stdlib. The String
deliberately has no image library, and the promoter cannot measure an image it
is handed, so the dimensions have to be recorded here or not at all.

Usage:
    python scripts/add_media_alt.py --list
    python scripts/add_media_alt.py --interactive
    python scripts/add_media_alt.py --id <record-id> --alt "first" --alt "second"

Env: STRING_URL (default http://localhost:8100), STRING_TOKEN if the String
is running with auth enabled.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import urllib.error
import urllib.request

STRING = os.environ.get("STRING_URL") or os.environ.get("SPINE_URL", "http://localhost:8100")
TOKEN = os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN")


def _req(path: str, *, method: str = "GET", body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"{STRING}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        # The String returns its validation problems in the body; a bare status
        # code sends you looking in the wrong place entirely.
        detail = e.read().decode(errors="replace")[:1000]
        raise SystemExit(f"{method} {path} failed: HTTP {e.code}\n  {detail}")


def _bytes(path: str) -> bytes:
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    req = urllib.request.Request(f"{STRING}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG, PNG or WebP header. None if unreadable.

    Unreadable is a normal outcome, not an error: aspectRatio is optional in
    the lexicon, and a wrong ratio is worse than an absent one.
    """
    # PNG: 8-byte signature, then IHDR with width/height as big-endian uint32.
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return (w, h) if w and h else None

    # WebP: 'RIFF' .... 'WEBP', then a VP8/VP8L/VP8X chunk.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return (w, h) if w and h else None
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            w = int.from_bytes(data[26:28], "little") & 0x3FFF
            h = int.from_bytes(data[28:30], "little") & 0x3FFF
            return (w, h) if w and h else None
        if chunk == b"VP8L" and data[20:21] == b"\x2f":
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        return None

    # JPEG: walk the marker segments to a start-of-frame, which carries the size.
    if data[:2] == b"\xff\xd8":
        i, n = 2, len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seglen = int.from_bytes(data[i + 2:i + 4], "big")
            # SOF0-SOF15, excluding DHT (C4), JPG (C8) and DAC (CC).
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return (w, h) if w and h else None
            if seglen <= 0:
                return None
            i += 2 + seglen
    return None


def media_records() -> list[dict]:
    recs = _req("/records?type=com.cultureblocs.bead&limit=500")
    recs = recs if isinstance(recs, list) else recs.get("records", [])
    return [r for r in recs if (r.get("body") or {}).get("media")]


def describe(rec: dict) -> None:
    body = rec.get("body") or {}
    pub = rec.get("published_uri") or rec.get("publishedUri")
    print(f"\n{rec['id']}  [{'published' if pub else 'local only'}]")
    note = (body.get("note") or "").strip().replace("\n", " ")
    if note:
        print(f"  note: {note[:70]}")
    for i, m in enumerate(body.get("media") or []):
        alt = m.get("alt")
        ar = m.get("aspectRatio")
        state = f"alt={alt!r}" if alt else "NO ALT"
        print(f"  [{i}] {m.get('uri','').split('/')[-1]}  {state}  ar={ar}")


def enrich(rec: dict, alts: list[str], *, dry: bool = False) -> bool:
    """Rewrite one record's media array with alt text and dimensions."""
    body = rec.get("body") or {}
    media = list(body.get("media") or [])
    changed = False
    for i, m in enumerate(media):
        entry = dict(m)
        if i < len(alts) and alts[i].strip():
            entry["alt"] = alts[i].strip()
            changed = True
        if not entry.get("aspectRatio"):
            name = (entry.get("uri") or "").split("/")[-1]
            try:
                dims = dimensions(_bytes(f"/media/{name}"))
            except urllib.error.URLError as e:
                print(f"    ! could not fetch {name}: {e}")
                dims = None
            if dims:
                entry["aspectRatio"] = {"width": dims[0], "height": dims[1]}
                changed = True
            else:
                print(f"    ! no dimensions readable for {name} — leaving it out")
        media[i] = entry
    if not changed:
        print("    nothing to change")
        return False
    if dry:
        print(f"    would PATCH: {json.dumps(media, indent=6)[:400]}")
        return True
    # The endpoint wraps the shallow-merge payload: PatchIn is {"fields": {...}}.
    _req(f"/records/{rec['id']}", method="PATCH", body={"fields": {"media": media}})
    print(f"    patched {len(media)} media entry/entries")
    return True


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="show beads that carry media")
    p.add_argument("--interactive", action="store_true", help="prompt for alt text per image")
    p.add_argument("--id", help="a single record id to update")
    p.add_argument("--alt", action="append", default=[],
                   help="alt text, repeated once per image in order")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    try:
        recs = media_records()
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach the String at {STRING}: {e}\n"
                 "start it with: docker compose up -d string")

    if not recs:
        sys.exit("no beads carry media.")

    if args.list or not (args.interactive or args.id):
        for r in recs:
            describe(r)
        print(f"\n{len(recs)} bead(s) with media. "
              "Re-run with --interactive to add alt text.")
        return

    if args.id:
        rec = next((r for r in recs if r["id"] == args.id), None)
        if not rec:
            sys.exit(f"no bead with media and id {args.id}")
        describe(rec)
        enrich(rec, args.alt, dry=args.dry_run)
        return

    for rec in recs:
        describe(rec)
        alts = []
        for i, m in enumerate(rec["body"]["media"]):
            if m.get("alt"):
                print(f"  [{i}] already has alt — press enter to keep it")
            got = input(f"  alt for [{i}] (blank = skip): ").strip()
            alts.append(got or m.get("alt") or "")
        enrich(rec, alts, dry=args.dry_run)

    print("\nDone. Re-publish the affected strands to push the alt text out.")


if __name__ == "__main__":
    main()
