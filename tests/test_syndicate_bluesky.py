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
from app.syndicate import bluesky, wall  # noqa: E402

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
    # text is the writable amount, not Bluesky's 300: the adapter spends the
    # rest on the link back (see the link tests at the end of this file).
    assert bluesky.LIMITS == {"text": 277, "images": 4, "wants_link": True}


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


def big_blob(n: int, size: int = 1_500_000, mime: str = "image/jpeg") -> dict:
    return {"$type": "blob", "ref": {"$link": f"bafkrei{n}"}, "mimeType": mime, "size": size}


def test_an_oversize_image_is_dropped_and_counted(calls):
    ref = {"image": big_blob(1)}
    out = bluesky.post(SESSION, STRAND, [item(ref)], "x")
    assert "embed" not in calls[0]["body"]["record"]
    assert out["dropped"] == 1


def test_a_non_image_mime_is_dropped_and_counted(calls):
    ref = {"image": big_blob(1, size=10, mime="application/octet-stream")}
    out = bluesky.post(SESSION, STRAND, [item(ref)], "x")
    assert "embed" not in calls[0]["body"]["record"]
    assert out["dropped"] == 1


def test_a_ref_at_exactly_the_max_size_is_kept(calls):
    ref = {"image": big_blob(1, size=1_000_000)}
    bluesky.post(SESSION, STRAND, [item(ref)], "x")
    imgs = calls[0]["body"]["record"]["embed"]["images"]
    assert [i["image"]["ref"]["$link"] for i in imgs] == ["bafkrei1"]


def test_filtered_refs_do_not_use_up_the_four_slots(calls):
    items = [item({"image": big_blob(1)}, {"image": blob(2)}, {"image": blob(3)}),
             item({"image": blob(4)}, {"image": blob(5)})]
    out = bluesky.post(SESSION, STRAND, items, "x")
    imgs = calls[0]["body"]["record"]["embed"]["images"]
    assert [i["image"]["ref"]["$link"] for i in imgs] == \
        [f"bafkrei{n}" for n in (2, 3, 4, 5)]
    assert out["dropped"] == 1


def test_text_at_the_limit_posts_and_one_over_is_refused_before_any_call(calls):
    limit = bluesky.LIMITS["text"]
    bluesky.post(SESSION, STRAND, [], "a" * limit)
    with pytest.raises(ValueError, match=str(limit)):
        bluesky.post(SESSION, STRAND, [], "a" * (limit + 1))
    assert len(calls) == 1


def test_text_is_counted_in_code_points_like_the_lexicon_validator(calls):
    limit = bluesky.LIMITS["text"]
    bluesky.post(SESSION, STRAND, [], "🎭" * limit)   # code points, not UTF-16 units
    with pytest.raises(ValueError):
        bluesky.post(SESSION, STRAND, [], "🎭" * (limit + 1))


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


# -- the link back to the wall (spec §5.2's "additive when the wall lands") --

WALL_LINK = "https://cultureblocs.com/wall/me.example/e328d978"


def test_the_writable_limit_leaves_room_for_the_link():
    """LIMITS["text"] is what a person may write, not Bluesky's 300: the
    adapter appends the link itself, and Loom sizes its counter from this."""
    assert bluesky.LIMITS["wants_link"] is True
    assert bluesky.LIMITS["text"] == bluesky.POST_MAX - len(bluesky.SUFFIX)
    assert bluesky.LIMITS["text"] == 277
    assert len(f"a post{bluesky.SUFFIX}") <= bluesky.POST_MAX


def test_the_link_is_appended_once_with_a_facet_over_the_visible_text(calls):
    bluesky.post(SESSION, STRAND, [], "A day out", link=WALL_LINK)
    rec = calls[0]["body"]["record"]

    assert rec["text"] == f"A day out{bluesky.SUFFIX}"
    assert rec["text"].count(bluesky.LINK_DISPLAY) == 1
    assert WALL_LINK not in rec["text"], "the long url rides in the facet, not the text"

    [facet] = rec["facets"]
    assert facet["features"] == [{"$type": "app.bsky.richtext.facet#link", "uri": WALL_LINK}]
    raw = rec["text"].encode("utf-8")
    start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
    assert raw[start:end].decode("utf-8") == bluesky.LINK_DISPLAY


def test_the_facet_range_is_bytes_not_characters(calls):
    """An emoji is one code point and four utf-8 bytes. A facet indexed in
    characters would point into the middle of the text here."""
    bluesky.post(SESSION, STRAND, [], "🎭 a day out", link=WALL_LINK)
    rec = calls[0]["body"]["record"]
    [facet] = rec["facets"]
    raw = rec["text"].encode("utf-8")
    assert raw[facet["index"]["byteStart"]:facet["index"]["byteEnd"]].decode("utf-8") \
        == bluesky.LINK_DISPLAY
    assert facet["index"]["byteStart"] != rec["text"].index(bluesky.LINK_DISPLAY), \
        "byte offset and character offset differ here, which is the point"


def test_text_at_the_writable_limit_plus_the_link_is_exactly_the_post_maximum(calls):
    text = "a" * bluesky.LIMITS["text"]
    bluesky.post(SESSION, STRAND, [], text, link=WALL_LINK)
    assert len(calls[0]["body"]["record"]["text"]) == bluesky.POST_MAX


def test_one_character_over_the_writable_limit_is_refused_before_any_call(calls):
    with pytest.raises(ValueError, match="277"):
        bluesky.post(SESSION, STRAND, [], "a" * 278, link=WALL_LINK)
    assert calls == []


def test_without_a_link_the_post_is_exactly_what_it_was_before(calls):
    bluesky.post(SESSION, STRAND, [], "A day out")
    rec = calls[0]["body"]["record"]
    assert rec["text"] == "A day out"
    assert "facets" not in rec


def test_what_the_post_shows_is_the_wall_it_actually_links_to():
    """A visible link naming one domain and pointing at another is the shape
    of a spoofed link. The display text is derived from the configured wall,
    so the two cannot drift."""
    assert bluesky.LINK_DISPLAY == wall.display()
    assert wall.display() == "cultureblocs.com/wall"
    assert bluesky.LINK_DISPLAY in wall.BASE


def test_a_wall_somewhere_else_is_shown_as_itself(monkeypatch):
    monkeypatch.setattr(wall, "BASE", "https://blocs.example.org/w/")
    assert wall.display() == "blocs.example.org/w"
    monkeypatch.setattr(wall, "BASE", "http://brick.local:8106/wall")
    assert wall.display() == "brick.local:8106/wall"
    monkeypatch.setattr(wall, "BASE", "")
    assert wall.display() == ""


def test_the_writable_limit_is_the_post_maximum_less_what_the_link_costs():
    assert bluesky.LIMITS["text"] + len(bluesky.SUFFIX) == bluesky.POST_MAX


def test_the_wall_link_is_built_from_the_handle_and_the_strand_rkey():
    assert wall.link_for("me.example", "e328d978") == WALL_LINK
    assert wall.enabled() is True


def test_an_unset_wall_base_turns_the_link_off(monkeypatch):
    monkeypatch.setattr(wall, "BASE", "")
    assert wall.enabled() is False
    assert wall.link_for("me.example", "e328d978") is None


def test_a_handle_or_rkey_that_needs_encoding_is_encoded():
    assert wall.link_for("did:plc:me", "a b") == \
        "https://cultureblocs.com/wall/did%3Aplc%3Ame/a%20b"
    assert wall.link_for("", "e328d978") is None
    assert wall.link_for("me.example", "") is None
