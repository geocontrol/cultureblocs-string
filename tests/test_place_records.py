"""The writers moved from venue.* to place.* (CHG-004, 6 Nov 2026).

scripts/venue.py builds place.profile and place.lineup records; the String's
publisher accepts place.profile, place.lineup and offer, publishing a place
at rkey "self"; the repo importer pulls the new collections. Old venue
records stay publishable so anything already held can be republished.
"""
import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
sys.path.insert(0, str(ROOT / "scripts"))
import venue  # noqa: E402
import import_repo  # noqa: E402
from app import publisher  # noqa: E402
from app.lexicon import LexiconRegistry  # noqa: E402

T = "2026-11-06T20:00:00Z"


def registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


def args(**kw) -> argparse.Namespace:
    base = dict(name=None, description=None, address=None, street=None, city=None,
                postcode=None, country="GB", lat=None, lng=None, capacity=None,
                accessibility=None, hours=None, space_types=None, access=None,
                link=None, external_id=None, tags="", event_uri=None, event_cid=None,
                place_uri=None, place_cid=None, note=None, billing=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_profile_is_a_place_with_an_address_location():
    body = venue.place_profile(args(name="The Ivy House", space_types=["venue"],
                                    access="bookable", street="40 Stuart Rd", city="London",
                                    postcode="se15 3be", capacity=150, hours="Thu-Sun",
                                    link=["https://ivyhousenunhead.com|website"]), T)
    assert body["$type"] == "com.cultureblocs.place.profile"
    assert body["spaceTypes"] == ["venue"]
    assert body["location"] == {"$type": "community.lexicon.location.address", "country": "GB",
                                "street": "40 Stuart Rd", "locality": "London",
                                "postalCode": "SE15 3BE"}
    assert "address" not in body and "place" not in body, "no deprecated venue fields"
    assert registry().validate_record(body["$type"], body) == []


def test_profile_defaults_to_venue_and_accepts_the_old_address_flag():
    body = venue.place_profile(args(name="Old Style", address="1 High St"), T)
    assert body["spaceTypes"] == ["venue"]
    assert body["location"]["street"] == "1 High St"
    assert registry().validate_record(body["$type"], body) == []


def test_profile_with_only_coordinates_uses_a_geo_location():
    body = venue.place_profile(args(name="Field", lat=51.47, lng=-0.06,
                                    space_types=["community_space"]), T)
    assert body["location"]["$type"] == "community.lexicon.location.geo"
    assert body["location"]["latitude"] == "51.47"
    assert registry().validate_record(body["$type"], body) == []


def test_online_only_supplier_has_no_location():
    body = venue.place_profile(args(name="Selvedge", space_types=["supplier"],
                                    access="online_only", street="ignored"), T)
    assert "location" not in body
    assert registry().validate_record(body["$type"], body) == []


def test_lineup_is_a_place_lineup_pointing_at_the_place():
    body = venue.place_lineup(args(event_uri="at://did:plc:x/community.lexicon.calendar.event/3k",
                                   event_cid="bafyevent",
                                   place_uri="at://did:plc:x/com.cultureblocs.place.profile/self",
                                   billing=["The Bug Club|live"], tags="gig,peckham"), T)
    assert body["$type"] == "com.cultureblocs.place.lineup"
    assert body["place"] == {"uri": "at://did:plc:x/com.cultureblocs.place.profile/self"}
    assert "venue" not in body
    assert registry().validate_record(body["$type"], body) == []


def test_old_venue_uri_flag_still_works():
    p = argparse.ArgumentParser()
    p.add_argument("--place-uri", "--venue-uri", dest="place_uri")
    assert p.parse_args(["--venue-uri", "at://x"]).place_uri == "at://x"


# ---------- publisher ----------

class FakeStore:
    def __init__(self, records):
        self.records = records

    def get(self, rid):
        return self.records.get(rid)

    def set_published(self, rid, uri, phash):
        self.records[rid]["publishedUri"] = uri
        return True


@pytest.fixture
def captured(monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, "_login", lambda _i: ("did:plc:fake", "jwt", "https://pds.example"))

    def xrpc(_pds, method, *, body=None, token=None):
        calls.append(body)
        return {"uri": f"at://did:plc:fake/{body['collection']}/{body['rkey']}", "cid": "bafy"}
    monkeypatch.setattr(publisher, "_xrpc", xrpc)
    return calls


IDENTITY = {"name": "place", "handle": "place.example", "app_password": "x", "pds": "https://pds.example"}


def held(rid, rtype, body, source="venue-cli"):
    return {"id": rid, "type": rtype, "sourceApp": source, "publishedUri": None,
            "dedupeKey": f"k:{rid}", "body": {"$type": rtype, "createdAt": T, **body}}


def test_publisher_publishes_a_place_profile_at_self(captured):
    store = FakeStore({"p": held("p", "com.cultureblocs.place.profile",
                                 {"name": "Arch Nine", "spaceTypes": ["rehearsal_room"]})})
    res = publisher.publish_record(store, "p", IDENTITY)
    assert captured[0]["collection"] == "com.cultureblocs.place.profile"
    assert captured[0]["rkey"] == "self"
    assert res["uri"].endswith("/com.cultureblocs.place.profile/self")


@pytest.mark.parametrize("rtype,body", [
    ("com.cultureblocs.place.lineup", {"event": {"uri": "at://did:plc:x/community.lexicon.calendar.event/3k"}}),
    ("com.cultureblocs.offer", {"kind": "offer", "title": "Mixing", "status": "open"}),
])
def test_publisher_publishes_lineups_and_offers_at_their_own_key(captured, rtype, body):
    store = FakeStore({"r": held("r", rtype, body)})
    publisher.publish_record(store, "r", IDENTITY)
    assert captured[0]["collection"] == rtype
    assert captured[0]["rkey"] != "self"


def test_seeded_place_lineups_are_still_refused(captured):
    store = FakeStore({"s": held("s", "com.cultureblocs.place.lineup",
                                 {"event": {"uri": "spine://records/fair"}, "tags": ["seed:artworld"]},
                                 source="seed-frieze")})
    with pytest.raises(ValueError, match="seeded"):
        publisher.publish_record(store, "s", IDENTITY)
    assert captured == [], "refused before any network call"


def test_deprecated_venue_records_stay_publishable():
    assert "com.cultureblocs.venue.profile" in publisher.PUBLIC_TYPES
    assert "com.cultureblocs.venue.lineup" in publisher.PUBLIC_TYPES


def test_importer_pulls_the_new_collections():
    for c in ("com.cultureblocs.place.profile", "com.cultureblocs.place.lineup", "com.cultureblocs.offer"):
        assert c in import_repo.COLLECTIONS
