"""Bluesky: a published strand as an app.bsky.feed.post, in the same repo.

Nearly free, which is why it is first. The post lands in the PDS repo the
strand was just written to, under the session phase 1 already opened, and
its images are the blobs phase 1 already uploaded: com.cultureblocs.defs
#imageRef mirrors app.bsky.embed.images#image field for field, so a ref
carries straight across. Nothing is uploaded twice.

What it says is the text a person wrote, sent exactly as written. It reads
nothing else: not the narrative, not a bead's note. An adapter that wants
more words than that must route them through the strip first (spec §6).

No link facet — there is no per-strand permalink to point at yet (spec §3).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import publisher

NAME = "bluesky"
LIMITS = {"text": 300, "images": 4, "wants_link": False}
POST = "app.bsky.feed.post"
# Mirrors app.bsky.embed.images#image.image's maxSize (1000000 bytes).
MAX_IMAGE_BYTES = 1_000_000


def check_text(text) -> None:
    """Refuse text Bluesky would refuse, before anything is sent.

    Counted in code points, as the String's lexicon validator counts
    maxGraphemes (lexicon.py). A code point count is never less than the
    grapheme count, so this can refuse an emoji-heavy post Bluesky would
    take, and can never pass one it rejects.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("post text is empty")
    if len(text) > LIMITS["text"]:
        raise ValueError(f"post text is {len(text)} characters; "
                         f"Bluesky takes at most {LIMITS['text']}")


def _embed_image(ref: dict) -> dict:
    # alt is optional on an imageRef and required on a Bluesky image; an
    # empty string is what Bluesky itself sends for "no description".
    out = {"image": ref["image"], "alt": ref.get("alt", "")}
    if ref.get("aspectRatio"):
        out["aspectRatio"] = ref["aspectRatio"]
    return out


def post(session: dict, strand: dict, items: list[dict], text: str) -> dict:
    """Post `text` with up to four of the strand's already-uploaded images.

    Returns {"id": rkey, "url": a bsky.app link, "dropped": images left out}.
    """
    check_text(text)
    refs = [ref for body in items for ref in (body.get("images") or [])]
    usable = [ref for ref in refs
              if str(ref.get("image", {}).get("mimeType", "")).startswith("image/")
              and isinstance(ref.get("image", {}).get("size"), int)
              and ref["image"]["size"] <= MAX_IMAGE_BYTES]
    kept = usable[:LIMITS["images"]]
    record = {"$type": POST, "text": text,
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    if kept:
        record["embed"] = {"$type": "app.bsky.embed.images",
                           "images": [_embed_image(r) for r in kept]}
    res = publisher._xrpc(session["pds"], "com.atproto.repo.createRecord",
                          token=session["jwt"],
                          body={"repo": session["did"], "collection": POST, "record": record})
    rkey = res["uri"].rsplit("/", 1)[-1]
    return {"id": rkey, "url": f"https://bsky.app/profile/{session['handle']}/post/{rkey}",
            "dropped": len(refs) - len(kept)}
