"""Places and offers: reading place.profile, and old venue.profile records as places.

com.cultureblocs.place.profile supersedes venue.profile, and place.lineup
supersedes venue.lineup. Records written with the old shapes stay on the
network and stay valid, so the AppView reads both and presents old venues
as places with spaceTypes ['venue'], as the deprecation note in
venue.profile describes. Nothing is rewritten: the original record is
returned alongside the mapped value.

No FastAPI here, so this can be tested without the web stack.
"""
from __future__ import annotations

from datetime import datetime, timezone

PLACE = "com.cultureblocs.place.profile"
LEGACY_VENUE = "com.cultureblocs.venue.profile"
PLACE_LINEUP = "com.cultureblocs.place.lineup"
LEGACY_LINEUP = "com.cultureblocs.venue.lineup"
LINEUPS = (PLACE_LINEUP, LEGACY_LINEUP)
OFFER = "com.cultureblocs.offer"

# Fields that carry straight across from a venue.profile to a place.profile.
_CARRIED = ("name", "description", "location", "capacity", "accessibility",
            "links", "externalIds", "tags", "createdAt")


def venue_as_place(rec: dict) -> dict:
    """An indexed venue.profile record, presented as a place.profile.

    The legacy `place` (placeRef) and `address` (string) fields have no
    exact place.profile equivalent, so they are not guessed into a
    location; the untouched record body rides along as `originalValue`
    for readers that want them, and for the /venue alias.
    """
    v = rec.get("value") or {}
    mapped = {"$type": PLACE, "spaceTypes": ["venue"]}
    for k in _CARRIED:
        if k in v:
            mapped[k] = v[k]
    return {**rec, "value": mapped, "legacyCollection": LEGACY_VENUE,
            "originalValue": v}


def places_for(index, did: str) -> list[dict]:
    """Every place an account publishes. place.profile records win: an old
    venue.profile is only shown for an account that has not yet published
    any place, so a venue that migrates does not appear twice."""
    places = index.records(PLACE, did, 50)
    if places:
        return places
    return [venue_as_place(r) for r in index.records(LEGACY_VENUE, did, 1)]


def _when(s) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def offer_is_open(value: dict, now: datetime | None = None) -> bool:
    """Open means status 'open' and inside any validity window. Any other
    status, including ones this code does not know, is not open; past
    validUntil an offer is closed whatever its status says."""
    if not isinstance(value, dict) or value.get("status") != "open":
        return False
    now = now or datetime.now(timezone.utc)
    start, end = _when(value.get("validFrom")), _when(value.get("validUntil"))
    if start and now < start:
        return False
    if end and now >= end:
        return False
    return True


def offers_for(index, did: str, place_uris: list[str] | None = None,
               now: datetime | None = None, include_closed: bool = False) -> dict:
    """An account's offers, split into the person's own (no offeredBy) and
    each place's (offeredBy points at one of its place records). Only open
    offers unless include_closed. Offers pointing at a place record this
    account does not publish are ignored: an offer speaks for its own repo."""
    own: list[dict] = []
    by_place: dict[str, list[dict]] = {u: [] for u in (place_uris or [])}
    for r in index.records(OFFER, did, 200):
        v = r.get("value") or {}
        if not include_closed and not offer_is_open(v, now):
            continue
        ref = v.get("offeredBy")
        uri = ref.get("uri") if isinstance(ref, dict) else None
        if uri is None:
            own.append(r)
        elif uri in by_place:
            by_place[uri].append(r)
    return {"own": own, "byPlace": by_place}
