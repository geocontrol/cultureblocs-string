"""The AppView reads place.profile, old venue.profile records as places, and
open offers. Loaded by path: appview/app and string/app are both packages
called `app`, so a plain import would collide with the String's."""
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


db = _load("appview_db", ROOT / "appview" / "app" / "db.py")
places = _load("appview_places", ROOT / "appview" / "app" / "places.py")

DID = "did:plc:placeholder00000000000000"
OTHER = "did:plc:someoneelse0000000000000"
NOW = datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc)
T = "2026-11-01T10:00:00Z"


@pytest.fixture
def index(tmp_path):
    return db.Index(str(tmp_path / "appview.db"))


def put(index, did, coll, rkey, body):
    uri = f"at://{did}/{coll}/{rkey}"
    index.put(uri, None, {"$type": coll, "createdAt": T, **body}, T)
    return uri


def test_old_venue_is_read_as_a_place(index):
    put(index, DID, places.LEGACY_VENUE, "self",
        {"name": "The Ivy House", "capacity": 200, "address": "40 Stuart Rd"})
    [p] = places.places_for(index, DID)
    assert p["value"]["spaceTypes"] == ["venue"]
    assert p["value"]["name"] == "The Ivy House"
    assert p["value"]["capacity"] == 200
    assert "address" not in p["value"], "never guessed into a location"
    assert p["originalValue"]["address"] == "40 Stuart Rd"
    assert p["legacyCollection"] == places.LEGACY_VENUE


def test_place_profiles_win_over_an_old_venue(index):
    put(index, DID, places.LEGACY_VENUE, "self", {"name": "Old name"})
    put(index, DID, places.PLACE, "self",
        {"name": "Arch 7", "spaceTypes": ["gallery", "artist_studio"]})
    put(index, DID, places.PLACE, "deptford",
        {"name": "Arch 7 Deptford", "spaceTypes": ["rehearsal_room"]})
    got = places.places_for(index, DID)
    assert sorted(p["value"]["name"] for p in got) == ["Arch 7", "Arch 7 Deptford"]
    assert not any("legacyCollection" in p for p in got)


@pytest.mark.parametrize("value,expected", [
    ({"status": "open"}, True),
    ({"status": "paused"}, False),
    ({"status": "closed"}, False),
    ({"status": "something-new"}, False),
    ({}, False),
    ({"status": "open", "validUntil": "2026-11-01T00:00:00Z"}, False),
    ({"status": "open", "validUntil": "2027-01-01T00:00:00Z"}, True),
    ({"status": "open", "validFrom": "2026-12-01T00:00:00Z"}, False),
    ({"status": "open", "validFrom": "2026-10-01T00:00:00+01:00"}, True),
    ({"status": "open", "validUntil": "next month"}, True),
])
def test_offer_is_open(value, expected):
    assert places.offer_is_open(value, NOW) is expected


def test_offers_split_by_who_offers_them(index):
    place_uri = put(index, DID, places.PLACE, "self",
                    {"name": "Arch 7", "spaceTypes": ["artist_studio"]})
    put(index, DID, places.OFFER, "a",
        {"kind": "offer", "title": "Mixing", "status": "open"})
    put(index, DID, places.OFFER, "b",
        {"kind": "offer", "title": "Desk to let", "status": "open",
         "offeredBy": {"uri": place_uri}})
    put(index, DID, places.OFFER, "c",
        {"kind": "offer", "title": "Paused", "status": "paused"})
    put(index, DID, places.OFFER, "d",
        {"kind": "offer", "title": "Someone else's place", "status": "open",
         "offeredBy": {"uri": f"at://{OTHER}/{places.PLACE}/self"}})
    got = places.offers_for(index, DID, [place_uri], now=NOW)
    assert [o["value"]["title"] for o in got["own"]] == ["Mixing"]
    assert [o["value"]["title"] for o in got["byPlace"][place_uri]] == ["Desk to let"]
    every = places.offers_for(index, DID, [place_uri], now=NOW, include_closed=True)
    assert {o["value"]["title"] for o in every["own"]} == {"Mixing", "Paused"}


def test_endpoints(index, monkeypatch, tmp_path):
    """/place, the /venue alias and /creative, through FastAPI."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    monkeypatch.setenv("APPVIEW_DB", str(tmp_path / "endpoints.db"))
    monkeypatch.setenv("APPVIEW_LIVE", "0")
    import types
    pkg = types.ModuleType("appview_pkg")
    pkg.__path__ = [str(ROOT / "appview" / "app")]
    sys.modules["appview_pkg"] = pkg
    main = _load("appview_pkg.main", ROOT / "appview" / "app" / "main.py")
    monkeypatch.setattr(main, "resolve_handle", lambda actor: actor)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)        # no `with`: startup (firehose) not run

    put(main.index, DID, places.LEGACY_VENUE, "self",
        {"name": "The Ivy House", "address": "40 Stuart Rd"})
    put(main.index, OTHER, places.PLACE, "self",
        {"name": "Arch 7", "spaceTypes": ["gallery"]})
    put(main.index, OTHER, places.OFFER, "x",
        {"kind": "offer", "title": "Studio desk", "status": "open",
         "offeredBy": {"uri": f"at://{OTHER}/{places.PLACE}/self"}})
    put(main.index, OTHER, places.OFFER, "y",
        {"kind": "offer", "title": "Mixing", "status": "open"})

    p = client.get(f"/place/{OTHER}").json()
    assert [x["value"]["name"] for x in p["places"]] == ["Arch 7"]
    assert [o["value"]["title"] for o in p["places"][0]["offers"]] == ["Studio desk"]
    assert p["totals"]["events"] == 0

    v = client.get(f"/venue/{DID}").json()
    assert v["places"][0]["value"]["spaceTypes"] == ["venue"]
    assert v["profile"]["value"]["address"] == "40 Stuart Rd", "old shape for old clients"

    c = client.get(f"/creative/{OTHER}").json()
    assert [o["value"]["title"] for o in c["offers"]] == ["Mixing"]

    assert "/place/" in client.get("/").text
