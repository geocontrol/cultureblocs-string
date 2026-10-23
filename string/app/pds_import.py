"""The round trip: bring born-public records home from the network.

Some beads never pass through the String. The "I went" composer on
cultureblocs.com, Pocket and any other client that writes straight to a
person's own ATProto repository make records that are public from birth,
with no private original anywhere. This pulls them into the String so the
desk (Loom) can do what those surfaces deliberately cannot — annotate,
attach photos, gather into strands — and so republishing after an edit
updates the same public record instead of making a second one.

What happens to each record found in the repo:

  own        the String published it: its twin is already held. Nothing to
             bring home — unless it was changed out there (see refreshed).
  created    new to the String. Held under dedupeKey "atproto:<at-uri>" (the
             same key scripts/import_repo.py has always used, so the two never
             double-import), state `kept` — it was a person's deliberate act,
             not a machine's proposal — and marked published, with the
             publishedHash `drift_hash` gives it, so it does not read as
             "edited since published" the moment it lands.
  refreshed  held already, changed on the network since (the composer edits
             in place), and not edited in the String since it was last
             published or imported. The public fields are taken from the
             network; anything private the String holds (provenance, local
             media, geo) is kept.
  unchanged  held, and the network copy says nothing new — including a record
             edited in the String and not yet republished, when the network
             copy is still the one published.
  conflict   held, changed on the network AND edited in the String since. Left
             alone and reported: the person decides, and a republish would
             overwrite the network copy with the String's.
  invalid    does not validate against the lexicons this String holds.

Strands are not imported. A strand on the network lists its beads as at://
strongRefs, and turning those back into spine:// items needs every member
held first; it is reported as `strands` so the gap is visible, not silent.
Nothing here deletes: a record that has gone from the network stays.

Reading a repository needs no credential (listRecords is public), so this
never logs in, and the identity is used only to say whose repo to read.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import refs
from .strip import content_hash, drift_hash, strip_bead

COLLECTIONS = ("com.cultureblocs.bead", "com.cultureblocs.annotation")
STRAND = "com.cultureblocs.strand"
DEDUPE_PREFIX = "atproto:"
PUBLIC_API = "https://public.api.bsky.app/xrpc"
MAX_PAGES = 50          # 5,000 records a collection: a guard, not a limit anyone should meet


def _get(url: str) -> dict:
    """GET a JSON document. Module-level so tests can replace it."""
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def resolve(identity: dict) -> tuple[str, str]:
    """(did, pds) for a held identity.

    The handle is resolved by the identity's own PDS first, then the public
    AppView; the PDS that actually holds the repo comes from the DID document,
    because an identity's `pds` may be an entryway (bsky.social) rather than
    the server the repo lives on. If the DID document cannot be read, the
    identity's `pds` is used as given.
    """
    handle = identity["handle"]
    did = handle if handle.startswith("did:") else None
    q = urllib.parse.urlencode({"handle": handle})
    for base in (f"{identity['pds'].rstrip('/')}/xrpc", PUBLIC_API):
        if did:
            break
        try:
            did = _get(f"{base}/com.atproto.identity.resolveHandle?{q}")["did"]
        except Exception:
            continue
    if not did:
        raise ValueError(f"could not resolve {handle}")
    try:
        doc = (_get(f"https://plc.directory/{did}") if did.startswith("did:plc:")
               else _get(f"https://{did[8:].replace(':', '/')}/.well-known/did.json"))
        pds = next(s["serviceEndpoint"] for s in doc.get("service", [])
                   if str(s.get("id", "")).endswith("#atproto_pds"))
    except Exception:
        pds = identity["pds"]
    return did, pds.rstrip("/")


def list_records(pds: str, did: str, collection: str) -> list[dict]:
    out, cursor = [], None
    for _ in range(MAX_PAGES):
        q = {"repo": did, "collection": collection, "limit": 100}
        if cursor:
            q["cursor"] = cursor
        page = _get(f"{pds}/xrpc/com.atproto.repo.listRecords?{urllib.parse.urlencode(q)}")
        out.extend(page.get("records") or [])
        cursor = page.get("cursor")
        if not cursor or not page.get("records"):
            break
    return out


def _public(body: dict) -> dict:
    """What of a body is public, minus `images`, which a String-published bead
    holds as local `media` and its network twin as blob refs — the same photos
    in two shapes, so never a difference on their own."""
    out = strip_bead(body)
    out.pop("images", None)
    return out


def _merged(held: dict, network: dict) -> dict:
    """The held body with its public fields replaced by the network's.

    Keys the strip publishes come from the network (and go if the network
    dropped them); every other key — provenance, media, geo, private notes
    fields — is the String's own and stays.
    """
    out = dict(held)
    for key in (set(_public(held)) | set(_public(network))) - {"$type"}:
        if key in network:
            out[key] = network[key]
        else:
            out.pop(key, None)
    if not held.get("media"):          # born public: its photos live only as blobs
        if "images" in network:
            out["images"] = network["images"]
        else:
            out.pop("images", None)
    return out


def _source_app(body: dict) -> str:
    app = (body.get("provenance") or {}).get("app")
    return app[:100] if isinstance(app, str) and app else "import"


def run(store, registry, identity: dict, *, since: str | None = None,
        dry_run: bool = False, device: str | None = None,
        actor: str | None = None) -> dict:
    did, pds = resolve(identity)
    report = {"did": did, "pds": pds, "dryRun": dry_run,
              "counts": {k: 0 for k in ("created", "refreshed", "unchanged", "own",
                                        "conflict", "invalid", "strands", "older")},
              "created": [], "refreshed": [], "conflicts": [], "invalid": []}
    counts = report["counts"]

    try:
        counts["strands"] = len(list_records(pds, did, STRAND))
    except Exception:
        pass                            # only a count for the report

    for coll in COLLECTIONS:
        for item in list_records(pds, did, coll):
            uri, value = item.get("uri"), item.get("value")
            if not isinstance(uri, str) or not isinstance(value, dict):
                continue
            if since and str(value.get("createdAt") or "") < since:
                counts["older"] += 1
                continue
            body = refs.mirror_annotation_work(coll, value)
            held = store.by_published_uri(uri) or store.by_dedupe_key(DEDUPE_PREFIX + uri)

            if held is None:
                problems = registry.validate_record(coll, body) + refs.anchor_problems(coll, body)
                if problems:
                    counts["invalid"] += 1
                    report["invalid"].append({"uri": uri, "problems": problems})
                    continue
                counts["created"] += 1
                if dry_run:
                    report["created"].append({"uri": uri})
                    continue
                rid, _ = store.upsert(DEDUPE_PREFIX + uri, coll, _source_app(body),
                                      body.get("createdAt") or "", body, state="kept",
                                      device=device, actor=actor)
                store.set_published(rid, uri, drift_hash(body), device=device, actor=actor)
                report["created"].append({"uri": uri, "id": rid})
                continue

            # Held. Has the network copy moved away from what the String holds?
            network_moved = content_hash(_public(body)) != content_hash(_public(held["body"]))
            if not held["body"].get("media"):
                network_moved = network_moved or (body.get("images") != held["body"].get("images"))
            if not network_moved:
                counts["own" if not held["dedupeKey"].startswith(DEDUPE_PREFIX) else "unchanged"] += 1
                # Not yet linked, or linked by the old import_repo.py, which
                # stored the hash of the whole body rather than drift_hash:
                # unchanged on both sides, so move it onto drift_hash, or it
                # reads as "edited since published" forever.
                legacy = held.get("publishedHash") == content_hash(held["body"])
                if (not held.get("publishedUri") or legacy) and not dry_run:
                    store.set_published(held["id"], uri, drift_hash(held["body"]), device=device, actor=actor)
                continue
            # A legacy whole-body hash that still matches means "not edited" too.
            edited_here = (held.get("publishedHash") is not None
                           and drift_hash(held["body"]) != held["publishedHash"]
                           and content_hash(held["body"]) != held["publishedHash"])
            if edited_here:
                # Edited in the String since it was last published. Unless the
                # network copy moved too, that is only an edit waiting for a
                # republish. With no local photos, drift_hash is exactly the
                # hash of the stripped body, so the network copy can be checked
                # against what was published; with local photos it cannot, and
                # the String's edit is taken to be the only change.
                network_since = (not held["body"].get("media")
                                 and content_hash(strip_bead(body)) != held["publishedHash"])
                if not network_since:
                    counts["own" if not held["dedupeKey"].startswith(DEDUPE_PREFIX) else "unchanged"] += 1
                    continue
                counts["conflict"] += 1
                report["conflicts"].append({"uri": uri, "id": held["id"]})
                continue
            merged = _merged(held["body"], body)
            problems = registry.validate_record(coll, merged) + refs.anchor_problems(coll, merged)
            if problems:
                counts["invalid"] += 1
                report["invalid"].append({"uri": uri, "problems": problems})
                continue
            counts["refreshed"] += 1
            report["refreshed"].append({"uri": uri, "id": held["id"]})
            if dry_run:
                continue
            fields = {**merged, **{k: None for k in held["body"] if k not in merged}}
            store.patch(held["id"], fields, device=device, actor=actor)
            store.set_published(held["id"], uri, drift_hash(merged), device=device, actor=actor)
    return report
