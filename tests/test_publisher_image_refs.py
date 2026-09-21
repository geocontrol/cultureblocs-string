"""The promoter maps mediaRef -> imageRef, carrying alt text and dimensions.
Uploads are stubbed: this is a field-mapping test, not a network test.

The stub goes on through `monkeypatch`, so the real upload is back in place
for whatever runs next (tests/test_test_isolation.py checks that it is).
"""
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402


def fake_blob(_pds, _jwt, data, mime):
    return {"$type": "blob", "ref": {"$link": f"bafkrei{len(data)}"},
            "mimeType": mime, "size": len(data)}


@pytest.fixture(autouse=True)
def stub_upload(monkeypatch):
    """Every test in this file uploads nothing."""
    monkeypatch.setattr(publisher, "_upload_blob", fake_blob)


def with_media_dir(files: dict):
    """Create a temp media dir containing `files` (name -> bytes)."""
    d = tempfile.mkdtemp()
    for name, data in files.items():
        (Path(d) / name).write_bytes(data)
    return d


def test_alt_and_aspect_ratio_survive_publication():
    media_dir = with_media_dir({"abc.jpg": b"x" * 10})
    body = {"media": [{
        "uri": "http://brick:8100/media/abc.jpg",
        "mime": "image/jpeg",
        "alt": "Gasholder at dusk.",
        "aspectRatio": {"width": 1600, "height": 1067},
    }]}
    refs = publisher._image_refs(body, media_dir, "https://pds.example", "jwt")
    assert len(refs) == 1, refs
    assert refs[0]["image"]["mimeType"] == "image/jpeg"
    assert refs[0]["alt"] == "Gasholder at dusk."
    assert refs[0]["aspectRatio"] == {"width": 1600, "height": 1067}


def test_absent_alt_is_omitted_not_emptied():
    """An empty alt string is a claim that the image is decorative. Absence is not."""
    media_dir = with_media_dir({"abc.jpg": b"x" * 10})
    body = {"media": [{"uri": "http://brick:8100/media/abc.jpg", "mime": "image/jpeg"}]}
    refs = publisher._image_refs(body, media_dir, "https://pds.example", "jwt")
    assert "alt" not in refs[0], refs[0]
    assert "aspectRatio" not in refs[0], refs[0]


def test_blank_alt_is_omitted():
    media_dir = with_media_dir({"abc.jpg": b"x" * 10})
    body = {"media": [{"uri": "http://brick:8100/media/abc.jpg", "alt": "   "}]}
    refs = publisher._image_refs(body, media_dir, "https://pds.example", "jwt")
    assert "alt" not in refs[0], refs[0]


def test_malformed_aspect_ratio_is_dropped_not_published():
    media_dir = with_media_dir({"abc.jpg": b"x" * 10})
    for bad in ({"width": 0, "height": 10}, {"width": "1600", "height": 1067},
                {"width": 1600}, {"width": True, "height": True}, "1600x1067", None):
        body = {"media": [{"uri": "http://brick:8100/media/abc.jpg", "aspectRatio": bad}]}
        refs = publisher._image_refs(body, media_dir, "https://pds.example", "jwt")
        assert "aspectRatio" not in refs[0], f"{bad!r} should not publish: {refs[0]}"


def test_missing_and_oversized_files_are_still_skipped():
    media_dir = with_media_dir({"big.jpg": b"x" * 2_000_001, "ok.jpg": b"x" * 10})
    body = {"media": [
        {"uri": "http://brick:8100/media/gone.jpg"},
        {"uri": "http://brick:8100/media/big.jpg"},
        {"uri": "http://brick:8100/media/ok.jpg"},
    ]}
    refs = publisher._image_refs(body, media_dir, "https://pds.example", "jwt")
    assert len(refs) == 1, refs


def test_strip_bead_emits_images_not_photos():
    body = {"$type": "com.cultureblocs.bead", "kind": "note",
            "createdAt": "2026-08-15T10:00:00Z", "note": "hello",
            "geo": {"lat": 51.5, "lon": -0.1},
            "provenance": {"device": "totem-01"}}
    images = [{"image": {"$type": "blob"}, "alt": "a"}]
    out = publisher.strip_bead(body, images=images)
    assert out["images"] == images
    assert "photos" not in out
    assert "geo" not in out, "geo must never publish"
    assert "provenance" not in out, "provenance must never publish"


def test_strip_bead_without_images_omits_the_field():
    body = {"$type": "com.cultureblocs.bead", "kind": "note",
            "createdAt": "2026-08-15T10:00:00Z"}
    out = publisher.strip_bead(body)
    assert "images" not in out


if __name__ == "__main__":
    print("run with pytest: the upload stub is an autouse fixture")
