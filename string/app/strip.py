"""The publish strip: the one canonical copy.

What may leave the String when a record is published. Allowlists all the
way down — a field not named here does not publish, at any depth, so a new
lexicon field stays private until someone decides otherwise and adds a
fixture saying so. Geo, provenance, local media and resolver bookkeeping
never leave.

Used by publisher.py, scripts/promote.py and scripts/export_public.py.
Ported to sdk/js/strip.js; both run tests/fixtures/strip-cases.json.
"""
from __future__ import annotations

ANNOTATION = "com.cultureblocs.annotation"
ROLES = ("subject", "mention")
BEAD_FIELDS = ("createdAt", "kind", "note")
STRAND_FIELDS = ("createdAt", "title", "narrative", "day")


def _str(v) -> bool:
    return isinstance(v, str) and v != ""


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _pick(d: dict, keys: tuple[str, ...]) -> dict:
    return {k: d[k] for k in keys if _str(d.get(k))}


def _head(body: dict) -> dict:
    return {"$type": body["$type"]}   # KeyError, like sdk/js/strip.js, rather than an untyped record


def strip_links(links) -> list[dict]:
    """linkRefs: uri and title only."""
    return [_pick(link, ("uri", "title")) for link in (links if isinstance(links, list) else [])
            if isinstance(link, dict) and _str(link.get("uri"))]


def strip_tags(tags) -> list[str]:
    return [t for t in (tags if isinstance(tags, list) else []) if _str(t)]


def strip_external_ids(ids) -> list[dict]:
    """externalIds: scheme, id and uri; entries without scheme and id are dropped."""
    return [_pick(e, ("scheme", "id", "uri")) for e in (ids if isinstance(ids, list) else [])
            if isinstance(e, dict) and _str(e.get("scheme")) and _str(e.get("id"))]


def strip_ref(ref, anchored: bool = True) -> dict | None:
    """The public form of one #ref, or None if it must not publish.

    Args:
        ref: A ref as stored locally.
        anchored: False for refs that have no text to anchor into
            (presentation.venueRef / eventRef); their index is dropped.

    Returns:
        The stripped ref, or None when it lacks a type or label, or is a
        person ref with neither a DID nor an external id.
    """
    if not isinstance(ref, dict) or not _str(ref.get("type")):
        return None
    descriptor = ref.get("descriptor")
    if not isinstance(descriptor, dict) or not _str(descriptor.get("label")):
        return None
    out = {
        "type": ref["type"],
        "role": ref["role"] if ref.get("role") in ROLES else "mention",
        "descriptor": _pick(descriptor, ("label", "creator", "creatorDid", "date")),
    }
    if _str(ref.get("did")):
        out["did"] = ref["did"]
    ids = strip_external_ids(ref.get("externalIds"))
    if ids:
        out["externalIds"] = ids
    if ref["type"] == "person" and "did" not in out and not ids:
        return None  # a bare name may be a private individual
    index = ref.get("index")
    if anchored and isinstance(index, dict) \
            and _int(index.get("byteStart")) and _int(index.get("byteEnd")):
        out["index"] = {"byteStart": index["byteStart"], "byteEnd": index["byteEnd"]}
    return out


def strip_refs(refs) -> list[dict]:
    kept = (strip_ref(r) for r in (refs if isinstance(refs, list) else []))
    return [r for r in kept if r is not None]


def strip_presentation(presentation) -> dict | None:
    if not isinstance(presentation, dict):
        return None
    out = _pick(presentation, ("format",))
    for key in ("venueRef", "eventRef"):
        ref = strip_ref(presentation.get(key), anchored=False)
        if ref is not None:
            out[key] = ref
    return out or None


def strip_work_ref(work) -> dict | None:
    """Deprecated #workRef on annotations: identifiers and descriptors, never `image`."""
    if not isinstance(work, dict):
        return None
    out = _pick(work, ("title", "creator", "date", "wikidata", "linkedArt", "creatorDid"))
    accession = work.get("accession")
    if isinstance(accession, dict) and _str(accession.get("institution")) \
            and _str(accession.get("id")):
        out["accession"] = _pick(accession, ("institution", "id"))
    return out


def _common(body: dict, out: dict) -> dict:
    tags = strip_tags(body.get("tags"))
    if tags:
        out["tags"] = tags
    links = strip_links(body.get("links"))
    if links:
        out["links"] = links
    refs = strip_refs(body.get("refs"))
    if refs:
        out["refs"] = refs
    return out


def strip_bead(body: dict, images: list | None = None) -> dict:
    """Public subset of a bead or annotation.

    Local `media` refs never publish; if the caller has uploaded them, they
    arrive as `images` — imageRefs carrying the blob plus alt text and
    dimensions — and are attached as given.
    """
    out = _head(body)
    for k in BEAD_FIELDS:
        if k in body:
            out[k] = body[k]
    subject = body.get("subject")
    if isinstance(subject, dict) and _str(subject.get("name")):
        out["subject"] = {"name": subject["name"]}
    if body.get("$type") == ANNOTATION:
        work = strip_work_ref(body.get("work"))
        if work is not None:
            out["work"] = work
    presentation = strip_presentation(body.get("presentation"))
    if presentation is not None:
        out["presentation"] = presentation
    _common(body, out)
    if images:
        out["images"] = images
    return out


def strip_strand(body: dict, items: list[dict] | None = None) -> dict:
    """Public subset of a strand. `items` are the published strongRefs,
    filled in at publish time; omitted for targets that bundle items inline."""
    out = _head(body)
    for k in STRAND_FIELDS:
        if k in body:
            out[k] = body[k]
    place = body.get("place")
    if isinstance(place, dict) and _str(place.get("name")):
        out["place"] = {"name": place["name"]}
    _common(body, out)
    if items is not None:
        out["items"] = items
    return out


def strip_public(body: dict) -> dict:
    """Records that are public by intent (creative claims, venue listings).

    These are written to be read by strangers, so the body publishes as
    authored — minus local-only machinery: provenance (device/app internals)
    and `media` refs that point at files on the author's own String. A venue's
    address and coordinates are the point of the record and stay.
    """
    return {k: v for k, v in body.items() if k not in ("provenance", "media")}
