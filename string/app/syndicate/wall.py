"""Where a syndicated post links back to.

The wall (cultureblocs-site `/wall/`) is the only human-facing address a
published strand has: `<base>/<handle>/<rkey>` shows that strand whole. Until
it existed, a post could say nothing about where it came from — which is why
the Bluesky adapter shipped without a link facet (spec §3, §5.2).

The base is configurable because the wall is a page on a site, not part of
this service: another String points at its own. Setting `WALL_BASE_URL` empty
turns the link off, and every adapter then posts exactly as it did before.
"""
from __future__ import annotations

import os
from urllib.parse import quote

BASE = (os.environ.get("WALL_BASE_URL", "https://cultureblocs.com/wall") or "").rstrip("/")


def enabled() -> bool:
    return bool(BASE)


def link_for(actor: str, rkey: str) -> str | None:
    """The wall's address for one strand, or None when there is nothing to
    point at — no wall configured, or no actor/rkey to name.

    The actor is the handle the strand was published as, because that is what
    the wall shows as its own title. A DID works too (the wall resolves
    either), which is what a handle change would need.
    """
    if not enabled() or not actor or not rkey:
        return None
    return f"{BASE}/{quote(str(actor), safe='')}/{quote(str(rkey), safe='')}"


def rkey_of(uri: str | None) -> str | None:
    """The record key at the end of an at:// URI."""
    if not uri or "/" not in str(uri):
        return None
    return str(uri).rsplit("/", 1)[-1] or None
