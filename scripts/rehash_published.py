#!/usr/bin/env python3
"""One-shot: move published beads and annotations onto drift_hash.

publishedHash used to be the hash of the record as sent to the PDS. For a
bead with photos that record holds upload-time blob refs the String can never
recompute, so `promote.py status` reported it as edited forever. Publishing
now stores drift_hash(body) instead (string/app/strip.py); this backfills
records published before that.

A stored hash is replaced only when the live published record proves nothing
was edited: its text matches the local strip exactly, and it carries the same
number of photos as the local bead. Anything else is reported and left alone,
so real drift still shows up in `status`.

    python scripts/rehash_published.py            # report only
    python scripts/rehash_published.py --apply    # write the new hashes

Options: --string URL (default http://localhost:8100)  --token STRING_TOKEN
Reads published records from each author's PDS; writes only to the String.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "string"))
from app.strip import drift_hash, strip_bead  # noqa: E402

BEAD_TYPES = ("com.cultureblocs.bead", "com.cultureblocs.annotation")


def decide(rec: dict, published: dict | None) -> tuple[str, str | None]:
    """What to do with one published bead.

    Returns ("in sync", None), ("rehash", new_hash), ("edited", None) or
    ("not on PDS", None).
    """
    body = rec["body"]
    if rec.get("publishedHash") == drift_hash(body):
        return "in sync", None
    if published is None:
        return "not on PDS", None
    text = {k: v for k, v in published.items() if k != "images"}
    local_photos = body.get("media") if isinstance(body.get("media"), list) else []
    if local_photos:
        photos_match = len(published.get("images") or []) == len(local_photos)
    else:                      # born-public bead: its images are in the body already
        photos_match = (published.get("images") or []) == (body.get("images") or [])
    if text == strip_bead(body) and photos_match:
        return "rehash", drift_hash(body)
    return "edited", None


def run(records: list[dict], fetch_published: Callable[[str], dict | None],
        write_hash: Callable[[str, str, str], None], *, apply: bool,
        out: Callable[..., None] = print) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in records:
        action, new_hash = decide(rec, fetch_published(rec["publishedUri"]))
        counts[action] = counts.get(action, 0) + 1
        if action != "in sync":
            out(f"  {action:10}  {rec['id']}  {(rec['body'].get('note') or '')[:50]!r}")
        if action == "rehash" and apply:
            write_hash(rec["id"], rec["publishedUri"], new_hash)
    return counts


# ---------------- network ----------------
def _get(url: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.loads(r.read())


_pds_for: dict[str, str] = {}


def _pds(did: str) -> str:
    if did not in _pds_for:
        doc = _get(f"https://plc.directory/{did}") if did.startswith("did:plc:") else \
            _get(f"https://{did[8:].replace(':', '/')}/.well-known/did.json")
        _pds_for[did] = next(s["serviceEndpoint"] for s in doc["service"]
                             if s["id"].endswith("#atproto_pds"))
    return _pds_for[did]


def fetch_published(uri: str) -> dict | None:
    did, collection, rkey = uri.removeprefix("at://").split("/")
    q = urllib.parse.urlencode({"repo": did, "collection": collection, "rkey": rkey})
    try:
        return _get(f"{_pds(did)}/xrpc/com.atproto.repo.getRecord?{q}")["value"]
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):      # deleted on the PDS
            return None
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="write the new hashes")
    p.add_argument("--string", default=os.environ.get("STRING_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN"))
    args = p.parse_args()
    base = args.string.rstrip("/")

    records = [r for t in BEAD_TYPES
               for r in _get(f"{base}/records?type={t}&limit=2000", args.token)["records"]
               if r.get("publishedUri")]

    def write_hash(rid: str, uri: str, new_hash: str) -> None:
        headers = {"Content-Type": "application/json"}
        if args.token:
            headers["Authorization"] = f"Bearer {args.token}"
        req = urllib.request.Request(f"{base}/records/{rid}/published", method="POST",
                                     data=json.dumps({"uri": uri, "hash": new_hash}).encode(),
                                     headers=headers)
        urllib.request.urlopen(req, timeout=15).close()

    counts = run(records, fetch_published, write_hash, apply=args.apply)
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing published"
    print(f"{len(records)} published beads/annotations: {summary}")
    if counts.get("rehash") and not args.apply:
        print("dry run: re-run with --apply to write the new hashes")


if __name__ == "__main__":
    main()
