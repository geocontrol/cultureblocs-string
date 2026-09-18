"""Syndication: renderings of a published strand on other services.

POSSE — publish on your own site, syndicate elsewhere. The PDS is where the
record lives; everything here is a rendering of it, made once, after the
strand is safely published (spec: docs/superpowers/specs/
2026-09-18-publish-destinations-design.md in cultureblocs-loom).

One module per destination, each exposing exactly NAME, LIMITS and
post(session, strand, items, text) -> {"id", "url", "dropped"}. Adding a
destination is a new module and one line in DESTINATIONS.

A rule for whoever writes the next one: any adapter that composes text from
`narrative`, a bead's `note` or any other record field must route it through
the strip first. The Bluesky adapter reads only the text a person wrote.
"""
from __future__ import annotations

from . import bluesky

DESTINATIONS = {bluesky.NAME: bluesky}


def available() -> list[dict]:
    """Every destination and its declared limits; Loom sizes its text box from these."""
    return [{"name": name, "limits": dict(mod.LIMITS)} for name, mod in DESTINATIONS.items()]


def check(destinations: list[str], text: str | None) -> list[str]:
    """Why this syndication request must not go ahead, in words; [] if it may.

    Run before phase 1: publishing and *then* failing on the post text is
    the worst order available.
    """
    if not destinations:
        return []
    unknown = [d for d in dict.fromkeys(destinations) if d not in DESTINATIONS]
    if unknown:
        return [f"unknown destination: {', '.join(unknown)} "
                f"(known: {', '.join(DESTINATIONS)})"]
    if not isinstance(text, str) or not text.strip():
        return ["post text is empty"]
    limit = min(DESTINATIONS[d].LIMITS["text"] for d in destinations)
    if len(text) > limit:
        return [f"post text is {len(text)} characters; the most every chosen "
                f"destination takes is {limit}"]
    return []


def post(destination: str, *, session: dict, strand: dict, items: list[dict],
         text: str) -> dict:
    """-> {"id": str, "url": str | None, "dropped": int}. Raises on failure."""
    return DESTINATIONS[destination].post(session, strand, items, text)


def run(store, record_id: str, destinations: list[str], text: str,
        held: dict) -> list[dict]:
    """Phase 2: post to each destination not already used, and record it.

    Never raises for a destination's sake. A failure is reported and records
    nothing, so the destination stays available to try again; the strand
    phase 1 published is untouched either way.
    """
    results = []
    for dest in dict.fromkeys(destinations):
        done = store.syndication(record_id, dest)
        if done:
            results.append({"destination": dest, "status": "already",
                            "remoteUrl": done["remoteUrl"], "postedAt": done["postedAt"]})
            continue
        try:
            out = post(dest, session=held["session"], strand=held["strand"],
                       items=held["items"], text=text)
        except Exception as exc:  # noqa: BLE001 — any adapter failure is reported, not raised
            results.append({"destination": dest, "status": "failed", "reason": str(exc)})
            continue
        row = store.add_syndication(record_id, dest, out["id"], out.get("url")) or {}
        results.append({"destination": dest, "status": "posted",
                        "remoteUrl": row.get("remoteUrl", out.get("url")),
                        "postedAt": row.get("postedAt"),
                        "droppedImages": out.get("dropped", 0)})
    return results
