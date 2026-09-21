"""Bluesky: a published strand as an app.bsky.feed.post, in the same repo.

Nearly free, which is why it is first. The post lands in the PDS repo the
strand was just written to, under the session phase 1 already opened, and
its images are the blobs phase 1 already uploaded: com.cultureblocs.defs
#imageRef mirrors app.bsky.embed.images#image field for field, so a ref
carries straight across. Nothing is uploaded twice.

What it says is the text a person wrote, sent exactly as written. It reads
nothing else: not the narrative, not a bead's note. An adapter that wants
more words than that must route them through the strip first (spec §6).

A link back is appended when one is offered: the wall's address for this
strand (wall.py), shown as short text with the real url carried in a
richtext facet. That keeps the post's 300 characters for writing rather than
spending ninety of them on a uuid — and it is why LIMITS["text"] is the
amount a person may write, not Bluesky's maximum.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import publisher
from . import wall

NAME = "bluesky"
POST = "app.bsky.feed.post"
POST_MAX = 300                      # Bluesky's own limit on a post's text
LINK_DISPLAY = "cultureblocs.com/wall"
SUFFIX = f"\n\n{LINK_DISPLAY}"      # what an appended link costs
LINK = "app.bsky.richtext.facet#link"
# What a person may write: the adapter spends the rest on the link itself, so
# Loom's counter (which reads this) is right without knowing anything about
# facets. With no wall configured nothing is appended and the whole post is
# theirs.
LIMITS = {"text": POST_MAX - (len(SUFFIX) if wall.enabled() else 0),
          "images": 4, "wants_link": True}
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
                         f"Bluesky takes at most {LIMITS['text']} here")


def _embed_image(ref: dict) -> dict:
    # alt is optional on an imageRef and required on a Bluesky image; an
    # empty string is what Bluesky itself sends for "no description".
    out = {"image": ref["image"], "alt": ref.get("alt", "")}
    if ref.get("aspectRatio"):
        out["aspectRatio"] = ref["aspectRatio"]
    return out


def _link_facet(text: str, link: str) -> dict:
    """A facet over the display text at the end of `text`.

    Bluesky indexes facets in **utf-8 bytes**, not characters, so this is
    measured on the encoded string: an emoji earlier in the post would
    otherwise shift the link and the range would point into the middle of
    something.
    """
    raw = text.encode("utf-8")
    shown = LINK_DISPLAY.encode("utf-8")
    return {"index": {"byteStart": len(raw) - len(shown), "byteEnd": len(raw)},
            "features": [{"$type": LINK, "uri": link}]}


def post(session: dict, strand: dict, items: list[dict], text: str,
         link: str | None = None) -> dict:
    """Post `text` with up to four of the strand's already-uploaded images.

    `link` is where this strand can be read — the wall's address for it. It
    is appended as short visible text with the url in a facet; the person's
    own words are never rewritten, only followed.

    Returns {"id": rkey, "url": a bsky.app link, "dropped": images left out}.
    """
    check_text(text)
    refs = [ref for body in items for ref in (body.get("images") or [])]
    usable = [ref for ref in refs
              if str(ref.get("image", {}).get("mimeType", "")).startswith("image/")
              and isinstance(ref.get("image", {}).get("size"), int)
              and ref["image"]["size"] <= MAX_IMAGE_BYTES]
    kept = usable[:LIMITS["images"]]
    said = f"{text}{SUFFIX}" if link else text
    record = {"$type": POST, "text": said,
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    if link:
        record["facets"] = [_link_facet(said, link)]
    if kept:
        record["embed"] = {"$type": "app.bsky.embed.images",
                           "images": [_embed_image(r) for r in kept]}
    res = publisher._xrpc(session["pds"], "com.atproto.repo.createRecord",
                          token=session["jwt"],
                          body={"repo": session["did"], "collection": POST, "record": record})
    rkey = res["uri"].rsplit("/", 1)[-1]
    return {"id": rkey, "url": f"https://bsky.app/profile/{session['handle']}/post/{rkey}",
            "dropped": len(refs) - len(kept)}
