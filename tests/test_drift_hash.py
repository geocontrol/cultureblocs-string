"""publishedHash on a bead measures the local body that was published, not
the bytes the PDS received.

The published record carries `images` — blob refs that only exist after an
upload — so hashing it made `promote.py status` report every published bead
with a photo as "edited since publish", however often it was republished.
drift_hash() hashes what the author controls instead: the stripped bead plus
the identity, alt text and dimensions of each local photo."""
import contextlib
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher, strip  # noqa: E402

BEAD = "com.cultureblocs.bead"


def bead(**over) -> dict:
    body = {"$type": BEAD, "createdAt": "2026-09-12T10:00:00Z", "kind": "bloc",
            "note": "Finished reading 'Navigational entanglements'.",
            "media": [{"uri": "/media/aaa.jpg", "mime": "image/jpeg", "alt": "A cover",
                       "aspectRatio": {"width": 800, "height": 1200}}]}
    body.update(over)
    return body


# -- drift_hash ------------------------------------------------------------

def test_a_bead_without_photos_hashes_as_it_always_has() -> None:
    body = bead()
    del body["media"]
    assert strip.drift_hash(body) == strip.content_hash(strip.strip_bead(body))


def test_the_same_body_hashes_the_same() -> None:
    assert strip.drift_hash(bead()) == strip.drift_hash(bead())


def test_editing_the_note_is_drift() -> None:
    assert strip.drift_hash(bead(note="changed")) != strip.drift_hash(bead())


def test_adding_removing_or_replacing_a_photo_is_drift() -> None:
    base = strip.drift_hash(bead())
    two = bead(media=bead()["media"] + [{"uri": "/media/bbb.jpg"}])
    none = bead(media=[])
    other = bead(media=[{**bead()["media"][0], "uri": "/media/ccc.jpg"}])
    assert len({base, strip.drift_hash(two), strip.drift_hash(none), strip.drift_hash(other)}) == 4


def test_changing_alt_text_or_dimensions_is_drift() -> None:
    m = bead()["media"][0]
    alt = bead(media=[{**m, "alt": "A different description"}])
    size = bead(media=[{**m, "aspectRatio": {"width": 1200, "height": 800}}])
    assert strip.drift_hash(alt) != strip.drift_hash(bead())
    assert strip.drift_hash(size) != strip.drift_hash(bead())


def test_the_photo_host_does_not_matter_only_the_file() -> None:
    """A String reached at another address serves the same content-addressed file."""
    moved = bead(media=[{**bead()["media"][0], "uri": "http://brick:8100/media/aaa.jpg"}])
    assert strip.drift_hash(moved) == strip.drift_hash(bead())


def test_private_fields_are_not_drift() -> None:
    """Geo and provenance never publish, so changing them changes nothing public."""
    private = bead(geo={"lat": 51.5, "lng": -0.1, "precision": "exact"},
                   provenance={"app": "culturebloc", "device": "totem-01",
                               "mintedAt": "2026-09-12T10:00:00Z"})
    assert strip.drift_hash(private) == strip.drift_hash(bead())


# -- the publisher stores it -------------------------------------------------

class FakeStore:
    def __init__(self, records: dict):
        self.records = records
        self.published: dict = {}

    def get(self, rid):
        return self.records.get(rid)

    def set_published(self, rid, uri, phash):
        self.published[rid] = (uri, phash)
        return True


def test_publish_strand_stores_the_drift_hash_even_when_photos_upload(tmp_path: Path) -> None:
    (tmp_path / "aaa.jpg").write_bytes(b"jpeg-bytes")
    body = bead()
    store = FakeStore({
        "s1": {"id": "s1", "type": "com.cultureblocs.strand", "sourceApp": "timeline",
               "publishedUri": None,
               "body": {"$type": "com.cultureblocs.strand", "createdAt": "2026-09-12T20:00:00Z",
                        "title": "Saturday", "items": [{"uri": "spine://records/b1"}]}},
        "b1": {"id": "b1", "type": BEAD, "sourceApp": "timeline", "publishedUri": None, "body": body},
    })
    sent = {}

    def fake_xrpc(_pds, method, *, body=None, token=None):
        assert method == "com.atproto.repo.putRecord", method
        sent[body["rkey"]] = body["record"]
        return {"uri": f"at://did:plc:fake/{body['collection']}/{body['rkey']}", "cid": "bafycid"}

    publisher._login = lambda _i: ("did:plc:fake", "jwt", "https://pds.example")
    publisher._xrpc = fake_xrpc
    publisher._upload_blob = lambda _p, _j, data, mime: {"$type": "blob", "ref": {"$link": "bafkblob"},
                                                         "mimeType": mime, "size": len(data)}
    publisher.publish_strand(store, "s1", {"name": "t", "handle": "t.example"}, media_dir=tmp_path)

    assert sent["b1"]["images"], "the photo must actually publish for this test to mean anything"
    assert store.published["b1"][1] == strip.drift_hash(body)


# -- promote.py agrees -------------------------------------------------------

def load_promote():
    spec = importlib.util.spec_from_file_location("promote", ROOT / "scripts" / "promote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_reports_a_republished_bead_with_photos_as_in_sync() -> None:
    promote = load_promote()
    body = bead()
    records = {
        "/records/b1": {"id": "b1", "type": BEAD, "body": body,
                        "publishedUri": "at://did:plc:fake/com.cultureblocs.bead/b1",
                        "publishedHash": strip.drift_hash(body)},
    }
    strands = [{"id": "s1", "publishedUri": "at://did:plc:fake/com.cultureblocs.strand/s1",
                "body": {"title": "Saturday", "items": [{"uri": "spine://records/b1"}]}}]
    promote.get_strands = lambda _args: strands
    promote.spine = lambda _args, path, **_kw: records[path]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        promote.cmd_status(None)
    assert "in sync" in out.getvalue(), out.getvalue()

    records["/records/b1"]["body"] = bead(note="edited after publishing")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        promote.cmd_status(None)
    assert "1 beads edited since publish" in out.getvalue(), out.getvalue()


def test_promote_publish_stores_the_drift_hash() -> None:
    promote = load_promote()
    body = bead()
    written = {}
    promote.get_strands = lambda _args: [
        {"id": "s1", "body": {"$type": "com.cultureblocs.strand", "title": "Saturday",
                              "createdAt": "2026-09-12T20:00:00Z",
                              "items": [{"uri": "spine://records/b1"}]}}]
    promote.spine = lambda _args, path, **_kw: {"id": "b1", "type": BEAD, "body": body}
    promote.login = lambda _args: ("did:plc:fake", "jwt")
    promote.xrpc = lambda _args, method, **kw: {
        "uri": f"at://did:plc:fake/{kw['body']['collection']}/{kw['body']['rkey']}", "cid": "bafycid"}
    promote.spine_writeback = lambda _args, path, **kw: written.__setitem__(path, kw.get("body"))

    class Args:
        ids = ["s1"]
        dry_run = False

    with contextlib.redirect_stdout(io.StringIO()):
        promote.cmd_publish(Args())
    assert written["/records/b1/published"]["hash"] == strip.drift_hash(body)
