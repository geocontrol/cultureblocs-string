#!/usr/bin/env python3
"""Places: a profile, and events that audiences can point their beads at.

A venue, gallery, rehearsal room, studio, supplier or shop publishes a
`com.cultureblocs.place.profile` (which replaced venue.profile on
6 Nov 2026; a venue is a place whose spaceTypes include "venue"). Events
are published as `community.lexicon.calendar.event` — the shared event
record of the open social web — so a place's nights appear in every
calendar app on the network, not only in CultureBlocs. Cultural detail the
shared record does not carry (who is on, works shown) goes in a
`com.cultureblocs.place.lineup` record that references the event.

Deliberately small. The venue publishes what is happening; people who
came publish their own beads referencing the event. The venue counts
public references — it never collects anything about an attendee, which
is what makes this workable for a space with no data protection officer
and no budget.

    python scripts/venue.py profile --name "The Ivy House" \
        --type venue --access bookable \
        --street "40 Stuart Rd" --city London --postcode "SE15 3BE" \
        --capacity 150 --accessibility "step-free entry, accessible toilet" \
        --link "https://ivyhousenunhead.com|website"

    python scripts/venue.py event --title "Friday Session" \
        --start 2026-08-14T20:00:00Z --end 2026-08-14T23:00:00Z \
        --address "40 Stuart Rd|London|GB" \
        --link "https://dice.fm/...|tickets"
    # then, optionally, the cultural layer referencing that event:
    python scripts/venue.py lineup --event-uri at://…/community.lexicon.calendar.event/… \
        --event-cid bafy… --place-uri at://…/com.cultureblocs.place.profile/self \
        --billing "The Bug Club|live" --billing "DJ Nadia|dj" --tags gig,peckham

Then publish under the place's identity:
    python scripts/promote.py publish <record-id> --identity venue
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def links(items):
    out = []
    for i in items or []:
        uri, _, title = i.partition("|")
        out.append({"uri": uri.strip(), **({"title": title.strip()} if title.strip() else {})})
    return out


def billing(items):
    out = []
    for i in items or []:
        parts = [p.strip() for p in i.split("|")]
        if not parts or not parts[0]:
            continue
        b = {"name": parts[0]}
        if len(parts) > 1 and parts[1]:
            b["role"] = parts[1]
        if len(parts) > 2 and parts[2].startswith("did:"):
            b["did"] = parts[2]
        out.append(b)
    return out


def ext_ids(pairs):
    out = []
    for p in pairs or []:
        scheme, _, ident = p.partition(":")
        if scheme and ident:
            out.append({"scheme": scheme.strip().lower(), "id": ident.strip()})
    return out


def tags(s):
    return [t.strip() for t in (s or "").split(",") if t.strip()][:8]


SPACE_TYPES = ("venue", "gallery", "museum", "cinema", "theatre", "rehearsal_room",
               "recording_studio", "artist_studio", "makerspace", "workshop",
               "coworking", "supplier", "shop", "library", "community_space")
ACCESS = ("walk_in", "by_appointment", "bookable", "online_only")


def place_profile(args, t: str) -> dict:
    """A com.cultureblocs.place.profile from the command line.

    Location is the shared community.lexicon.location.address when there is
    a street, city or postcode, otherwise a geo point when --lat/--lng are
    given. Places are public, so an address is expected; an online-only
    supplier gives neither.
    """
    body = {"$type": "com.cultureblocs.place.profile", "name": args.name,
            "spaceTypes": [s for s in (args.space_types or ["venue"]) if s][:8],
            "createdAt": t}
    if args.access:
        body["publicAccess"] = args.access
    if args.description:
        body["description"] = args.description
    street = args.street or args.address
    if args.access != "online_only" and (street or args.city or args.postcode):
        loc = {"$type": "community.lexicon.location.address", "country": args.country}
        if street:
            loc["street"] = street
        if args.city:
            loc["locality"] = args.city
        if args.postcode:
            loc["postalCode"] = args.postcode.upper()
        body["location"] = loc
    elif args.access != "online_only" and args.lat is not None and args.lng is not None:
        body["location"] = {"$type": "community.lexicon.location.geo",
                            "latitude": str(args.lat), "longitude": str(args.lng),
                            "name": args.name}
    if args.capacity:
        body["capacity"] = args.capacity
    if args.accessibility:
        body["accessibility"] = args.accessibility
    if args.hours:
        body["hours"] = args.hours
    if links(args.link):
        body["links"] = links(args.link)
    if ext_ids(args.external_id):
        body["externalIds"] = ext_ids(args.external_id)
    if tags(args.tags):
        body["tags"] = tags(args.tags)
    return body


def place_lineup(args, t: str) -> dict:
    """A com.cultureblocs.place.lineup over a shared calendar event."""
    body = {"$type": "com.cultureblocs.place.lineup",
            "event": {"uri": args.event_uri,
                      **({"cid": args.event_cid} if args.event_cid else {})},
            "createdAt": t}
    if billing(args.billing):
        body["billing"] = billing(args.billing)
    if args.place_uri:
        body["place"] = {"uri": args.place_uri,
                         **({"cid": args.place_cid} if args.place_cid else {})}
    if args.note:
        body["note"] = args.note
    if tags(args.tags):
        body["tags"] = tags(args.tags)
    return body


def post(args, rtype, body, dedupe):
    record = {"dedupeKey": dedupe, "type": rtype, "sourceApp": "venue-cli",
              "createdAt": body["createdAt"], "body": body}
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    req = urllib.request.Request(
        args.string.rstrip("/") + "/records",
        data=json.dumps({"records": [record]}).encode(),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())["results"][0]
    if res["status"] == "invalid":
        sys.exit(f"rejected: {res['problems']}")
    print(f"{rtype} {res['status']}: {res['id']}")
    print("publish with: python scripts/promote.py publish "
          f"{res['id']} --identity <venue-identity>")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["profile", "event", "lineup"])
    p.add_argument("--name")
    p.add_argument("--description")
    p.add_argument("--address")
    p.add_argument("--lat", type=float)
    p.add_argument("--lng", type=float)
    p.add_argument("--capacity", type=int)
    p.add_argument("--accessibility")
    p.add_argument("--title")
    p.add_argument("--start", help="ISO datetime, e.g. 2026-08-14T20:00:00Z")
    p.add_argument("--end")
    p.add_argument("--place-uri", "--venue-uri", dest="place_uri",
                   help="at:// URI of the place profile record")
    p.add_argument("--place-cid", "--venue-cid", dest="place_cid")
    p.add_argument("--venue-name", help="if the venue has no CultureBlocs identity")
    p.add_argument("--type", action="append", dest="space_types",
                   help=f"kind of place, repeatable: {', '.join(SPACE_TYPES)} "
                        "(default venue)")
    p.add_argument("--access", choices=ACCESS,
                   help="how the public visits or books it")
    p.add_argument("--street", help="street address (--address is accepted too)")
    p.add_argument("--postcode")
    p.add_argument("--hours", help="opening or booking hours, freeform")
    p.add_argument("--event-uri", help="at:// URI of the event a lineup describes")
    p.add_argument("--event-cid", help="CID of that event, pinning what is described")
    p.add_argument("--city")
    p.add_argument("--country", default="GB")
    p.add_argument("--mode", choices=["inperson", "virtual", "hybrid"],
                   default="inperson")
    p.add_argument("--note")
    p.add_argument("--billing", action="append", help='"Name|role|did"; repeatable')
    p.add_argument("--status", choices=["scheduled", "cancelled", "postponed", "soldout"])
    p.add_argument("--link", action="append", help='"url|label"; repeatable')
    p.add_argument("--external-id", action="append", help='"scheme:id"; repeatable')
    p.add_argument("--tags", default="")
    p.add_argument("--string", "--spine",
                   default=os.environ.get("STRING_URL") or
                   os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or
                   os.environ.get("SPINE_TOKEN"))
    args = p.parse_args()
    t = now()

    if args.cmd == "profile":
        if not args.name:
            sys.exit("--name required")
        body = place_profile(args, t)
        # A new key: the String keeps the first record under a key, so an old
        # venue:profile:self must not swallow the new place record.
        post(args, body["$type"], body, "place:profile:self")

    elif args.cmd == "event":
        if not (args.title and args.start):
            sys.exit("--title and --start required")
        body = {"$type": "community.lexicon.calendar.event",
                "name": args.title, "createdAt": t,
                "startsAt": args.start,
                "mode": f"community.lexicon.calendar.event#{args.mode}",
                "status": "community.lexicon.calendar.event#" +
                          (args.status or "scheduled")}
        if args.end:
            body["endsAt"] = args.end
        if args.description:
            body["description"] = args.description
        locs = []
        if args.address or args.city:
            addr = {"$type": "community.lexicon.location.address",
                    "country": args.country}
            if args.address:
                addr["street"] = args.address
            if args.city:
                addr["locality"] = args.city
            if args.venue_name:
                addr["name"] = args.venue_name
            locs.append(addr)
        if args.lat is not None and args.lng is not None:
            locs.append({"$type": "community.lexicon.location.geo",
                         "latitude": str(args.lat), "longitude": str(args.lng),
                         **({"name": args.venue_name} if args.venue_name else {})})
        if locs:
            body["locations"] = locs
        uris = [{"uri": l["uri"], **({"name": l["title"]} if l.get("title") else {})}
                for l in links(args.link)]
        if uris:
            body["uris"] = uris
        post(args, body["$type"], body, f"event:{uuid.uuid4()}")

    else:  # lineup — the cultural layer over a shared event record
        if not args.event_uri:
            sys.exit("--event-uri required (the event this lineup describes)")
        body = place_lineup(args, t)
        post(args, body["$type"], body, f"lineup:{uuid.uuid4()}")


if __name__ == "__main__":
    main()
