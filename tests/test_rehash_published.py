"""scripts/rehash_published.py moves already-published beads onto drift_hash,
but only where the live published record proves nothing was edited."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import strip  # noqa: E402

spec = importlib.util.spec_from_file_location("rehash_published", ROOT / "scripts/rehash_published.py")
rehash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehash)

BEAD = "com.cultureblocs.bead"
URI = "at://did:plc:fake/com.cultureblocs.bead/b1"
IMAGE = {"image": {"$type": "blob", "ref": {"$link": "bafkblob"}}, "alt": "A cover"}


def bead(**over) -> dict:
    body = {"$type": BEAD, "createdAt": "2026-09-12T10:00:00Z", "kind": "bloc", "note": "Read it.",
            "media": [{"uri": "/media/aaa.jpg", "alt": "A cover"}]}
    body.update(over)
    return body


def record(body: dict, stored: str) -> dict:
    return {"id": "b1", "type": BEAD, "body": body, "publishedUri": URI, "publishedHash": stored}


def published(body: dict, images: list) -> dict:
    return {**strip.strip_bead(body), "images": images}


def test_old_style_hash_with_matching_record_is_rehashed() -> None:
    body = bead()
    pub = published(body, [IMAGE])
    rec = record(body, strip.content_hash(pub))
    assert rehash.decide(rec, pub) == ("rehash", strip.drift_hash(body))


def test_already_on_drift_hash_is_left_alone() -> None:
    body = bead()
    rec = record(body, strip.drift_hash(body))
    assert rehash.decide(rec, published(body, [IMAGE])) == ("in sync", None)


def test_text_edited_since_publish_is_reported_not_rehashed() -> None:
    body = bead()
    pub = published(body, [IMAGE])
    rec = record(bead(note="edited later"), strip.content_hash(pub))
    assert rehash.decide(rec, pub)[0] == "edited"


def test_photo_added_since_publish_is_reported_not_rehashed() -> None:
    body = bead()
    pub = published(body, [IMAGE])
    later = bead(media=body["media"] + [{"uri": "/media/bbb.jpg"}])
    assert rehash.decide(record(later, strip.content_hash(pub)), pub)[0] == "edited"


def test_missing_published_record_is_reported() -> None:
    body = bead()
    assert rehash.decide(record(body, "x"), None)[0] == "not on PDS"


def test_run_applies_only_rehashes_and_only_with_apply() -> None:
    body = bead()
    pub = published(body, [IMAGE])
    good = record(body, strip.content_hash(pub))
    edited = {**record(bead(note="edited"), strip.content_hash(pub)), "id": "b2",
              "publishedUri": URI.replace("b1", "b2")}
    writes = []
    records = [good, edited]

    def fetch_published(uri):
        return pub

    def write_hash(rid, uri, new_hash):
        writes.append((rid, uri, new_hash))

    counts = rehash.run(records, fetch_published, write_hash, apply=False, out=lambda *_: None)
    assert counts == {"rehash": 1, "edited": 1} and writes == []

    rehash.run(records, fetch_published, write_hash, apply=True, out=lambda *_: None)
    assert writes == [("b1", URI, strip.drift_hash(body))]
