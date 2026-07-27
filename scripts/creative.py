#!/usr/bin/env python3
"""CreativeID: self-asserted profile, work claims, and attestations.

The model is self-attestation. A work claim proves one narrow, honest
thing: that you made this claim, on this date, from this repository.
That is enough to tag a piece of work as yours and to be pointed at by
everything further up the stack — industry registrations, scene layers,
licensing — none of which live here.

    python scripts/creative.py profile --name "Mark Simpkins" \
        --disciplines "writing,software" --link https://geekyoto.com \
        --external-id wikidata:Q123 --external-id auracle:abc-123

    python scripts/creative.py work --title "Untitled (Peckham)" \
        --url https://example.com/work --date 2026 \
        --credit "Jo Bloggs|photography" --tags peckham,print

    python scripts/creative.py connect --did did:plc:xxxx \
        --relationship collaborated_on --role "mix engineer"
    python scripts/creative.py connect --uri at://did:plc:.../rkey \
        --cid bafy... --relationship attests_to \
        --note "shown at our summer show"

Records land in your String. Publish them with:
    python scripts/promote.py publish <record-id> --identity <name>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def post(args, rtype: str, body: dict, dedupe: str) -> None:
    record = {"dedupeKey": dedupe, "type": rtype, "sourceApp": "creative-cli",
              "createdAt": body["createdAt"], "body": body}
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    req = urllib.request.Request(
        args.string.rstrip("/") + "/records",
        data=json.dumps({"records": [record]}).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())["results"][0]
    if res["status"] == "invalid":
        sys.exit(f"rejected: {res['problems']}")
    print(f"{rtype} {res['status']}: {res['id']}")
    print("publish with: python scripts/promote.py publish "
          f"{res['id']} --identity <name>")


def ext_ids(pairs: list[str]) -> list[dict]:
    out = []
    for p in pairs or []:
        scheme, _, ident = p.partition(":")
        if scheme and ident:
            out.append({"scheme": scheme.strip().lower(), "id": ident.strip()})
    return out


def links(items: list[str]) -> list[dict]:
    out = []
    for i in items or []:
        uri, _, title = i.partition("|")
        out.append({"uri": uri.strip(), **({"title": title.strip()} if title.strip() else {})})
    return out


def credits(items: list[str]) -> list[dict]:
    out = []
    for i in items or []:
        parts = [p.strip() for p in i.split("|")]
        if not parts or not parts[0]:
            continue
        c = {"name": parts[0]}
        if len(parts) > 1 and parts[1]:
            c["role"] = parts[1]
        if len(parts) > 2 and parts[2].startswith("did:"):
            c["did"] = parts[2]
        out.append(c)
    return out


def tags(s: str) -> list[str]:
    return [t.strip() for t in (s or "").split(",") if t.strip()][:8]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["profile", "work", "connect"])
    p.add_argument("--name")
    p.add_argument("--bio")
    p.add_argument("--disciplines", default="")
    p.add_argument("--based", help="place name")
    p.add_argument("--title")
    p.add_argument("--url", help="referenceUrl for a work")
    p.add_argument("--date", help="freeform completion date, e.g. 2024")
    p.add_argument("--description")
    p.add_argument("--credit", action="append",
                   help='"Name|role|did" (role and did optional); repeatable')
    p.add_argument("--link", action="append", help='"url|label"; repeatable')
    p.add_argument("--external-id", action="append",
                   help='"scheme:id", e.g. isni:0000000121174403; repeatable')
    p.add_argument("--tags", default="")
    p.add_argument("--did", help="subject DID for connect")
    p.add_argument("--uri", help="subject record at:// URI for connect")
    p.add_argument("--cid", help="CID to pin the attested record content")
    p.add_argument("--relationship", default="attests_to")
    p.add_argument("--role")
    p.add_argument("--note")
    p.add_argument("--string", "--spine",
                   default=os.environ.get("STRING_URL") or
                   os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or
                   os.environ.get("SPINE_TOKEN"))
    args = p.parse_args()
    t = now()

    if args.cmd == "profile":
        if not args.name:
            sys.exit("--name required")
        body = {"$type": "com.cultureblocs.creative.profile",
                "name": args.name, "createdAt": t}
        if args.bio:
            body["bio"] = args.bio
        if tags(args.disciplines):
            body["disciplines"] = tags(args.disciplines)
        if args.based:
            body["based"] = {"name": args.based}
        if links(args.link):
            body["links"] = links(args.link)
        if ext_ids(args.external_id):
            body["externalIds"] = ext_ids(args.external_id)
        post(args, body["$type"], body, "creative:profile:self")

    elif args.cmd == "work":
        if not args.title:
            sys.exit("--title required")
        body = {"$type": "com.cultureblocs.creative.work",
                "title": args.title, "createdAt": t}
        for k, v in (("referenceUrl", args.url), ("completionDate", args.date),
                     ("description", args.description)):
            if v:
                body[k] = v
        if credits(args.credit):
            body["credits"] = credits(args.credit)
        if links(args.link):
            body["links"] = links(args.link)
        if ext_ids(args.external_id):
            body["externalIds"] = ext_ids(args.external_id)
        if tags(args.tags):
            body["tags"] = tags(args.tags)
        post(args, body["$type"], body, f"creative:work:{uuid.uuid4()}")

    else:  # connect
        if args.did:
            subject = {"$type": "com.cultureblocs.defs#didRef", "did": args.did}
            if args.name:
                subject["name"] = args.name
        elif args.uri:
            subject = {"$type": "com.cultureblocs.defs#strongRef", "uri": args.uri}
            if args.cid:
                subject["cid"] = args.cid
        else:
            sys.exit("connect needs --did or --uri (with --cid to pin content)")
        body = {"$type": "com.cultureblocs.creative.connection",
                "subject": subject, "relationship": args.relationship,
                "createdAt": t}
        if args.role:
            body["role"] = args.role
        if args.note:
            body["note"] = args.note
        post(args, body["$type"], body, f"creative:connection:{uuid.uuid4()}")


if __name__ == "__main__":
    main()
