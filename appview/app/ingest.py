"""Two ways in: the live firehose, and backfill from a repo.

Jetstream is a filtered view of the ATProto firehose — asking it for only
com.cultureblocs.* collections means the server drops the millions of
unrelated events before they reach us, so this runs at near-zero cost.

Backfill exists because records published before the AppView started
would otherwise be invisible: a venue that put up listings last month
should not have to republish them.
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

COLLECTIONS = [
    "com.cultureblocs.bead",
    "com.cultureblocs.annotation",
    "com.cultureblocs.strand",
    "com.cultureblocs.creative.profile",
    "com.cultureblocs.creative.work",
    "com.cultureblocs.creative.connection",
    "com.cultureblocs.venue.profile",
    "com.cultureblocs.venue.lineup",
    "com.cultureblocs.venue.listing",      # deprecated; indexed for old records
    # Shared schemas of the open social web. Events are published by many
    # apps (atmo.rsvp, VenueCMS venues, us) and referenced by all of them:
    # an RSVP says "I'm going", a bead says "I was here". Same event record.
    "community.lexicon.calendar.event",
    "community.lexicon.calendar.rsvp",
]

EVENT = "community.lexicon.calendar.event"
RSVP = "community.lexicon.calendar.rsvp"
LEGACY_LISTING = "com.cultureblocs.venue.listing"

JETSTREAM_HOSTS = [
    "wss://jetstream1.us-east.bsky.network/subscribe",
    "wss://jetstream2.us-east.bsky.network/subscribe",
    "wss://jetstream1.us-west.bsky.network/subscribe",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def resolve_pds(did: str) -> str:
    if did.startswith("did:plc:"):
        doc = _json(f"https://plc.directory/{did}")
    elif did.startswith("did:web:"):
        host = did[len("did:web:"):].replace(":", "/")
        doc = _json(f"https://{host}/.well-known/did.json")
    else:
        raise ValueError(f"unsupported DID method: {did}")
    for s in doc.get("service", []):
        if s.get("id") in ("#atproto_pds", f"{did}#atproto_pds"):
            return s["serviceEndpoint"]
    raise ValueError(f"no PDS endpoint for {did}")


def resolve_handle(handle: str) -> str:
    """handle -> DID, with fallbacks.

    The public API only answers for handles it can verify bidirectionally.
    Plenty of real accounts have a domain handle set on the DID side while
    the domain serves something unhelpful at /.well-known/atproto-did — the
    account still exists and its records are still public, so fall back to
    the DNS TXT record and to the well-known file before giving up.
    """
    if handle.startswith("did:"):
        return handle
    handle = handle.lstrip("@").strip()
    try:
        q = urllib.parse.urlencode({"handle": handle})
        return _json("https://public.api.bsky.app/xrpc/"
                     f"com.atproto.identity.resolveHandle?{q}")["did"]
    except Exception:
        pass
    try:                                    # DNS TXT _atproto.<handle>
        q = urllib.parse.urlencode({"name": f"_atproto.{handle}", "type": "TXT"})
        dns = _json(f"https://dns.google/resolve?{q}")
        for a in dns.get("Answer", []):
            data = a.get("data", "").strip('"')
            if data.startswith("did="):
                return data[4:]
    except Exception:
        pass
    try:                                    # /.well-known/atproto-did
        with urllib.request.urlopen(
                f"https://{handle}/.well-known/atproto-did", timeout=15) as r:
            text = r.read(2048).decode(errors="replace").strip()
        if text.startswith("did:") and "\n" not in text:
            return text
    except Exception:
        pass
    raise ValueError(
        f"could not resolve '{handle}' to a DID — try the did:plc:… directly")


def backfill(index, actor: str) -> dict:
    """Index every cultureblocs record already in someone's repo."""
    did = resolve_handle(actor)
    pds = resolve_pds(did)
    counts: dict[str, int] = {}
    for coll in COLLECTIONS:
        cursor = None
        while True:
            params = {"repo": did, "collection": coll, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            try:
                page = _json(f"{pds}/xrpc/com.atproto.repo.listRecords?"
                             + urllib.parse.urlencode(params))
            except Exception:
                break                      # collection absent in this repo
            for rec in page.get("records", []):
                index.put(rec["uri"], rec.get("cid"), rec["value"], now())
                counts[coll] = counts.get(coll, 0) + 1
            cursor = page.get("cursor")
            if not cursor or not page.get("records"):
                break
    return {"did": did, "pds": pds, "indexed": counts,
            "total": sum(counts.values())}


async def consume(index, host_idx: int = 0) -> None:
    """Follow the firehose forever, reconnecting on failure."""
    import websockets

    backoff = 1
    while True:
        host = JETSTREAM_HOSTS[host_idx % len(JETSTREAM_HOSTS)]
        params = [("wantedCollections", c) for c in COLLECTIONS]
        cur = index.cursor()
        if cur:
            params.append(("cursor", cur))
        url = f"{host}?{urllib.parse.urlencode(params)}"
        try:
            async with websockets.connect(url, ping_interval=20,
                                          max_size=2 ** 22) as ws:
                print(f"[jetstream] connected: {host}", flush=True)
                backoff = 1
                async for raw in ws:
                    try:
                        handle_event(index, json.loads(raw))
                    except Exception as exc:          # never die on one event
                        print(f"[jetstream] bad event: {exc}", flush=True)
        except Exception as exc:
            host_idx += 1
            print(f"[jetstream] disconnected ({exc}); retrying in {backoff}s",
                  flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def handle_event(index, evt: dict) -> None:
    if evt.get("kind") != "commit":
        return
    c = evt.get("commit") or {}
    did, coll, rkey = evt.get("did"), c.get("collection"), c.get("rkey")
    if not (did and coll and rkey):
        return
    uri = f"at://{did}/{coll}/{rkey}"
    op = c.get("operation")
    if op in ("create", "update") and isinstance(c.get("record"), dict):
        index.put(uri, c.get("cid"), c["record"], now())
        print(f"[jetstream] {op} {uri}", flush=True)
    elif op == "delete":
        index.delete(uri)
        print(f"[jetstream] delete {uri}", flush=True)
    if evt.get("time_us"):
        index.set_cursor(evt["time_us"])
