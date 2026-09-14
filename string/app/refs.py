"""Refs helpers that need more than the lexicon can say.

The validator checks a ref's shape; it cannot check that an `index` lands
inside the record's own text, on character boundaries. That lives here,
with the transitional #workRef -> #ref mapping.

Ported to sdk/js/refs.js; both run tests/fixtures/refs-cases.json.
"""
from __future__ import annotations

ANNOTATION = "com.cultureblocs.annotation"

# The text a record's ref anchors index into.
TEXT_FIELD = {
    "com.cultureblocs.strand": "narrative",
    "com.cultureblocs.bead": "note",
    ANNOTATION: "note",
}


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _on_boundary(data: bytes, pos: int) -> bool:
    """True unless `pos` falls inside a multi-byte UTF-8 sequence."""
    return pos == len(data) or (data[pos] & 0xC0) != 0x80


def anchor_problems(nsid: str, body: dict) -> list[str]:
    """Problems with ref anchors that the lexicon cannot express.

    Args:
        nsid: The record type.
        body: The record body.

    Returns:
        Problem strings in the validator's format; empty when anchors are sound.
    """
    field = TEXT_FIELD.get(nsid)
    if field is None:
        return []
    problems: list[str] = []
    text = body.get(field)
    data = text.encode("utf-8") if isinstance(text, str) else b""
    refs = body.get("refs")
    for i, ref in enumerate(refs if isinstance(refs, list) else []):
        idx = ref.get("index") if isinstance(ref, dict) else None
        if not isinstance(idx, dict):
            continue
        start, end = idx.get("byteStart"), idx.get("byteEnd")
        if not (_is_int(start) and _is_int(end)):
            continue  # shape errors are the validator's to report
        path = f"$.refs[{i}].index"
        if not 0 <= start <= end <= len(data):
            problems.append(f"{path}: {start}..{end} is outside {field} ({len(data)} bytes)")
        elif not (_on_boundary(data, start) and _on_boundary(data, end)):
            problems.append(f"{path}: {start}..{end} splits a character in {field}")
    presentation = body.get("presentation")
    if isinstance(presentation, dict):
        for key in ("venueRef", "eventRef"):
            ref = presentation.get(key)
            if isinstance(ref, dict) and "index" in ref:
                problems.append(f"$.presentation.{key}.index: presentation refs cannot anchor")
    return problems


def ref_from_work_ref(work: dict) -> dict:
    """Map a deprecated #workRef onto a #ref with role subject."""
    descriptor = {"label": work.get("title") or work.get("wikidata") or "Untitled work"}
    for key in ("creator", "creatorDid", "date"):
        if isinstance(work.get(key), str) and work[key]:
            descriptor[key] = work[key]
    ids = []
    if isinstance(work.get("wikidata"), str) and work["wikidata"]:
        ids.append({"scheme": "wikidata", "id": work["wikidata"]})
    if isinstance(work.get("linkedArt"), str) and work["linkedArt"]:
        ids.append({"scheme": "linkedArt", "id": work["linkedArt"], "uri": work["linkedArt"]})
    acc = work.get("accession")
    if isinstance(acc, dict) and isinstance(acc.get("institution"), str) \
            and isinstance(acc.get("id"), str):
        ids.append({"scheme": "accession", "id": f"{acc['institution']}/{acc['id']}"})
    ref = {"type": "work", "role": "subject", "descriptor": descriptor}
    if ids:
        ref["externalIds"] = ids
    return ref


def mirror_annotation_work(nsid: str, body: dict) -> dict:
    """Give an annotation's required `work` a matching subject ref.

    Transitional, while the AR gallery still writes `work`: an annotation
    with no work-subject ref gets one derived from `work`. An existing
    work-subject ref is never replaced. Returns a new dict when it adds one.
    """
    if nsid != ANNOTATION or not isinstance(body.get("work"), dict):
        return body
    refs = body.get("refs") if isinstance(body.get("refs"), list) else []
    if any(isinstance(r, dict) and r.get("type") == "work" and r.get("role") == "subject"
           for r in refs):
        return body
    return {**body, "refs": [*refs, ref_from_work_ref(body["work"])]}
