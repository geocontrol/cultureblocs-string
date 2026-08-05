#!/usr/bin/env python3
"""Publish the com.cultureblocs.* lexicons as ATProto schema records.

Writes each lexicon document in lexicons/com/cultureblocs/ into the
cultureblocs account's repo as a com.atproto.lexicon.schema record whose
rkey is the lexicon's NSID. Combined with the _lexicon DNS record (see
PUBLISHING.md), this makes the schemas formally resolvable by any ATProto
tooling: NSID -> DNS -> DID -> record.

Usage:
    BSKY_HANDLE=cultureblocs.com BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx \
        python scripts/publish_lexicons.py [--pds https://bsky.social]
    python scripts/publish_lexicons.py --dry-run      # print, publish nothing
    python scripts/publish_lexicons.py --verify       # check DNS + fetch back

Use an APP PASSWORD (Settings -> Privacy & Security -> App Passwords),
never the account password. Publishing is idempotent: putRecord with a
fixed rkey overwrites, so re-running after editing a lexicon is the
update mechanism.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LEX_DIR = Path(__file__).resolve().parents[1] / "lexicons" / "com" / "cultureblocs"
COLLECTION = "com.atproto.lexicon.schema"
AUTHORITY = "cultureblocs.com"


def xrpc(pds: str, method: str, *, params: dict | None = None,
         body: dict | None = None, token: str | None = None) -> dict:
    url = f"{pds.rstrip('/')}/xrpc/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def load_lexicons() -> list[dict]:
    docs = []
    for f in sorted(LEX_DIR.rglob("*.json")):
        doc = json.loads(f.read_text())
        # Only publish schemas this domain is the authority for. Vendored
        # community lexicons live under lexicons/community/ and belong to
        # lexicon.community — publishing them here would be a false claim.
        if doc.get("lexicon") == 1 and str(doc.get("id", "")).startswith(
                "com.cultureblocs."):
            docs.append(doc)
    if not docs:
        sys.exit(f"no lexicon documents found in {LEX_DIR}")
    return docs


def publish(args) -> None:
    docs = load_lexicons()
    if args.dry_run:
        for d in docs:
            print(f"would put {COLLECTION} rkey={d['id']} "
                  f"({len(d['defs'])} defs)")
        return
    handle = os.environ.get("BSKY_HANDLE")
    password = os.environ.get("BSKY_APP_PASSWORD")
    if not (handle and password):
        sys.exit("set BSKY_HANDLE and BSKY_APP_PASSWORD (an app password)")
    session = xrpc(args.pds, "com.atproto.server.createSession",
                   body={"identifier": handle, "password": password})
    did, token = session["did"], session["accessJwt"]
    print(f"authenticated as {session.get('handle', handle)} ({did})")
    for d in docs:
        record = {"$type": COLLECTION, **d}
        res = xrpc(args.pds, "com.atproto.repo.putRecord", token=token, body={
            "repo": did, "collection": COLLECTION, "rkey": d["id"],
            "record": record})
        print(f"  put {d['id']}  ->  {res['uri']}")
    print("\ndone. If the _lexicon DNS record is in place (see PUBLISHING.md),")
    print("the NSIDs are now formally resolvable.")


def verify(args) -> None:
    # 1. DNS: _lexicon.<authority> TXT should carry did=<did>
    q = urllib.parse.urlencode({"name": f"_lexicon.{AUTHORITY}", "type": "TXT"})
    with urllib.request.urlopen(f"https://dns.google/resolve?{q}", timeout=15) as r:
        dns = json.loads(r.read())
    answers = [a["data"].strip('"') for a in dns.get("Answer", [])]
    did = next((a.split("did=", 1)[1] for a in answers if "did=" in a), None)
    if did:
        print(f"DNS ok: _lexicon.{AUTHORITY} -> {did}")
    else:
        print(f"DNS MISSING: no did= TXT at _lexicon.{AUTHORITY} "
              f"(answers: {answers or 'none'})")
    # 2. fetch each schema record back from the PDS, unauthenticated
    if not did:
        return
    for d in load_lexicons():
        try:
            res = xrpc(args.pds, "com.atproto.repo.getRecord", params={
                "repo": did, "collection": COLLECTION, "rkey": d["id"]})
            ok = res["value"].get("id") == d["id"]
            print(f"  {'ok ' if ok else 'MISMATCH'} {d['id']}")
        except Exception as exc:
            print(f"  MISSING {d['id']}: {exc}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pds", default=os.environ.get("PDS_URL", "https://bsky.social"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    verify(args) if args.verify else publish(args)


if __name__ == "__main__":
    main()
