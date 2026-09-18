"""The Bluesky adapter: a strand as an app.bsky.feed.post in the same repo.

The claim the whole design rests on (spec §5): the post reuses the blobs
phase 1 already uploaded — it never uploads again."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher, strip  # noqa: E402
from app.syndicate import bluesky  # noqa: E402

SESSION = {"did": "did:plc:me", "jwt": "jwt", "pds": "https://pds.example", "handle": "me.example"}
STRAND = {"$type": "com.cultureblocs.strand", "createdAt": "2026-09-18T10:00:00Z",
          "title": "A day out", "narrative": "NARRATIVE-MUST-NOT-LEAVE", "items": []}


def blob(n: int) -> dict:
    return {"$type": "blob", "ref": {"$link": f"bafkrei{n}"}, "mimeType": "image/jpeg", "size": 10}


def item(*images, note="NOTE-MUST-NOT-LEAVE") -> dict:
    out = {"$type": "com.cultureblocs.bead", "kind": "bloc", "note": note,
           "createdAt": "2026-09-18T10:00:00Z"}
    if images:
        out["images"] = list(images)
    return out


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_xrpc(pds, method, *, body=None, token=None):
        seen.append({"pds": pds, "method": method, "body": body, "token": token})
        return {"uri": "at://did:plc:me/app.bsky.feed.post/3post", "cid": "bafycid"}

    def no_upload(*_a, **_k):
        raise AssertionError("the adapter re-uploaded a blob; phase 1 already did")

    monkeypatch.setattr(publisher, "_xrpc", fake_xrpc)
    monkeypatch.setattr(publisher, "_upload_blob", no_upload)
    return seen


def test_it_declares_its_name_and_limits():
    assert bluesky.NAME == "bluesky"
    assert bluesky.LIMITS == {"text": 300, "images": 4, "wants_link": False}


def test_a_post_is_created_in_the_same_repo_with_the_text_as_written(calls):
    out = bluesky.post(SESSION, STRAND, [item()], "  A day out, Saturday  ")
    [c] = calls
    assert c["method"] == "com.atproto.repo.createRecord"
    assert c["pds"] == "https://pds.example" and c["token"] == "jwt"
    assert c["body"]["repo"] == "did:plc:me"
    assert c["body"]["collection"] == "app.bsky.feed.post"
    assert "rkey" not in c["body"], "the PDS mints the TID"
    rec = c["body"]["record"]
    assert rec["$type"] == "app.bsky.feed.post"
    assert rec["text"] == "  A day out, Saturday  ", "text is never rewritten"
    assert rec["createdAt"].endswith("Z")
    assert "embed" not in rec, "no images, no embed"
    assert out == {"id": "3post", "url": "https://bsky.app/profile/me.example/post/3post",
                   "dropped": 0}


def test_blob_refs_are_reused_with_alt_and_aspect_ratio_carried_across(calls):
    ref = {"image": blob(1), "alt": "Gasholder at dusk.",
           "aspectRatio": {"width": 1600, "height": 1067}}
    bluesky.post(SESSION, STRAND, [item(ref)], "x")
    embed = calls[0]["body"]["record"]["embed"]
    assert embed["$type"] == "app.bsky.embed.images"
    assert embed["images"] == [{"image": blob(1), "alt": "Gasholder at dusk.",
                                "aspectRatio": {"width": 1600, "height": 1067}}]


def test_a_missing_alt_becomes_empty_because_bluesky_requires_the_field(calls):
    bluesky.post(SESSION, STRAND, [item({"image": blob(1)})], "x")
    [img] = calls[0]["body"]["record"]["embed"]["images"]
    assert img == {"image": blob(1), "alt": ""}


def test_more_than_four_images_posts_the_first_four_and_says_how_many_dropped(calls):
    items = [item({"image": blob(1)}, {"image": blob(2)}), item(),
             item({"image": blob(3)}, {"image": blob(4)}, {"image": blob(5)})]
    out = bluesky.post(SESSION, STRAND, items, "x")
    imgs = calls[0]["body"]["record"]["embed"]["images"]
    assert [i["image"]["ref"]["$link"] for i in imgs] == [f"bafkrei{n}" for n in (1, 2, 3, 4)]
    assert out["dropped"] == 1


def test_text_at_the_limit_posts_and_one_over_is_refused_before_any_call(calls):
    bluesky.post(SESSION, STRAND, [], "a" * 300)
    with pytest.raises(ValueError, match="300"):
        bluesky.post(SESSION, STRAND, [], "a" * 301)
    assert len(calls) == 1


def test_text_is_counted_in_code_points_like_the_lexicon_validator(calls):
    bluesky.post(SESSION, STRAND, [], "🎭" * 300)       # 300 code points, 600 UTF-16 units
    with pytest.raises(ValueError):
        bluesky.post(SESSION, STRAND, [], "🎭" * 301)


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_text_is_refused(calls, text):
    with pytest.raises(ValueError, match="empty"):
        bluesky.post(SESSION, STRAND, [], text)
    assert calls == []


def test_nothing_but_the_given_text_and_the_images_leaves(calls):
    """The adapter composes nothing from note or narrative (spec §6)."""
    bluesky.post(SESSION, STRAND, [item({"image": blob(1)})], "A day out")
    sent = json.dumps(calls[0]["body"])
    assert "NOTE-MUST-NOT-LEAVE" not in sent
    assert "NARRATIVE-MUST-NOT-LEAVE" not in sent


def test_the_strip_does_not_change():
    """Syndication must not quietly widen what leaves. Change these on purpose,
    with a fixture in tests/fixtures/strip-cases.json, or not at all."""
    assert strip.BEAD_FIELDS == ("createdAt", "kind", "note")
    assert strip.STRAND_FIELDS == ("createdAt", "title", "narrative", "day")
