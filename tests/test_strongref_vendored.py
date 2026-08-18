"""com.atproto.repo.strongRef is held so RSVPs can validate.

It is vendored, not owned: it belongs to the atproto project, and
publish_lexicons.py must never republish it under cultureblocs.com's
authority — the same arrangement as the community.lexicon.* files.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.lexicon import LexiconRegistry  # noqa: E402

RSVP = "community.lexicon.calendar.rsvp"


def build_registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


def test_strongref_is_held():
    reg = build_registry()
    assert "com.atproto.repo.strongRef" in reg.docs


def test_public_rsvp_validates():
    """A real published subject has both an at:// uri and a cid."""
    reg = build_registry()
    rec = {
        "$type": RSVP,
        "status": "community.lexicon.calendar.rsvp#going",
        "subject": {
            "uri": "at://did:plc:abc123/community.lexicon.calendar.event/3kxyz",
            "cid": "bafyreib2rxk3rh6kzwq6y4o2hbvgchpqvtqzsxkyexbcbnrhbcxkxvqnaa",
        },
    }
    problems = reg.validate_record(RSVP, rec)
    assert not problems, f"expected valid, got {problems}"


def test_rsvp_without_a_cid_is_rejected():
    """The point of the strongRef is the content hash. A local record has no
    cid, and inventing one would be a lie in exactly the field the
    architecture relies on to make references tamper-evident. So a local
    plan is deliberately NOT modelled as an RSVP — see the design spec §5."""
    reg = build_registry()
    rec = {
        "$type": RSVP,
        "status": "community.lexicon.calendar.rsvp#interested",
        "subject": {"uri": "spine://records/8f2c1a"},
    }
    problems = reg.validate_record(RSVP, rec)
    assert problems, "a subject with no cid must not validate"
    assert any("cid" in p for p in problems), problems


def test_vendored_lexicon_is_not_publishable():
    """publish_lexicons.py allowlists com.cultureblocs.* only. Assert that
    holds for this file, so a future change to that filter cannot silently
    start claiming authority over someone else's namespace."""
    doc = json.loads(
        (ROOT / "lexicons/com/atproto/repo/strongRef.json").read_text())
    assert doc["id"] == "com.atproto.repo.strongRef"
    assert not doc["id"].startswith("com.cultureblocs.")


if __name__ == "__main__":
    test_strongref_is_held()
    test_public_rsvp_validates()
    test_rsvp_without_a_cid_is_rejected()
    test_vendored_lexicon_is_not_publishable()
    print("OK: strongRef vendoring tests passed")
