"""imageRef: the published image shape carries alt text and dimensions,
and the legacy bare-blob shape no longer validates."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.lexicon import LexiconRegistry  # noqa: E402

RECORD_TYPES = [
    "com.cultureblocs.bead",
    "com.cultureblocs.annotation",
    "com.cultureblocs.creative.work",
]

BLOB = {"$type": "blob", "ref": {"$link": "bafkreitestcid"},
        "mimeType": "image/jpeg", "size": 12345}


def build_registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


def base_record(nsid: str) -> dict:
    """Minimal valid record per type, before images are added."""
    rec = {"$type": nsid, "createdAt": "2026-08-15T10:00:00Z"}
    if nsid == "com.cultureblocs.bead":
        rec["kind"] = "note"
    elif nsid == "com.cultureblocs.annotation":
        rec["work"] = {"title": "A work"}
    elif nsid == "com.cultureblocs.creative.work":
        rec["title"] = "Untitled #1"
    return rec


def test_full_image_ref_validates_on_every_record():
    reg = build_registry()
    for nsid in RECORD_TYPES:
        rec = base_record(nsid)
        rec["images"] = [{
            "image": BLOB,
            "alt": "A charcoal study of a gasholder at dusk.",
            "aspectRatio": {"width": 1600, "height": 1067},
        }]
        problems = reg.validate_record(nsid, rec)
        assert not problems, f"{nsid}: expected valid, got {problems}"


def test_image_alone_is_enough():
    """alt and aspectRatio are optional; the blob is not."""
    reg = build_registry()
    for nsid in RECORD_TYPES:
        rec = base_record(nsid)
        rec["images"] = [{"image": BLOB}]
        problems = reg.validate_record(nsid, rec)
        assert not problems, f"{nsid}: expected valid, got {problems}"


def test_legacy_bare_blob_no_longer_validates():
    """The whole point of the migration: a bare blob is missing `image`."""
    reg = build_registry()
    for nsid in RECORD_TYPES:
        rec = base_record(nsid)
        rec["images"] = [BLOB]
        problems = reg.validate_record(nsid, rec)
        assert problems, f"{nsid}: expected the legacy shape to fail, but it validated"
        assert any("image" in p for p in problems), \
            f"{nsid}: expected a missing-`image` problem, got {problems}"


def test_aspect_ratio_requires_integers():
    reg = build_registry()
    rec = base_record("com.cultureblocs.creative.work")
    rec["images"] = [{"image": BLOB, "aspectRatio": {"width": "1600", "height": 1067}}]
    problems = reg.validate_record("com.cultureblocs.creative.work", rec)
    assert problems, "expected a string width to be rejected"


def test_aspect_ratio_requires_both_dimensions():
    reg = build_registry()
    rec = base_record("com.cultureblocs.creative.work")
    rec["images"] = [{"image": BLOB, "aspectRatio": {"width": 1600}}]
    problems = reg.validate_record("com.cultureblocs.creative.work", rec)
    assert problems, "expected a half-specified aspectRatio to be rejected"


def test_media_ref_accepts_aspect_ratio():
    """Tier 0 media carries dimensions so the promoter never derives them."""
    reg = build_registry()
    rec = base_record("com.cultureblocs.bead")
    rec["media"] = [{
        "uri": "http://brick:8100/media/abc123.jpg",
        "mime": "image/jpeg",
        "alt": "Gasholder at dusk.",
        "aspectRatio": {"width": 1600, "height": 1067},
    }]
    problems = reg.validate_record("com.cultureblocs.bead", rec)
    assert not problems, f"expected valid, got {problems}"


def test_photos_field_is_gone_from_the_schema():
    """`photos` was renamed, not aliased. Readers tolerate it; the schema does not."""
    reg = build_registry()
    for nsid in ("com.cultureblocs.bead", "com.cultureblocs.annotation"):
        props = reg.docs[nsid]["defs"]["main"]["record"]["properties"]
        assert "photos" not in props, f"{nsid}: `photos` should have been renamed to `images`"
        assert "images" in props, f"{nsid}: expected an `images` property"


if __name__ == "__main__":
    test_full_image_ref_validates_on_every_record()
    test_image_alone_is_enough()
    test_legacy_bare_blob_no_longer_validates()
    test_aspect_ratio_requires_integers()
    test_aspect_ratio_requires_both_dimensions()
    test_media_ref_accepts_aspect_ratio()
    test_photos_field_is_gone_from_the_schema()
    print("OK: imageRef schema tests passed")
