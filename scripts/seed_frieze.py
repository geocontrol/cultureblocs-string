#!/usr/bin/env python3
"""Seed a fair's exhibitors from Artworld into the String as Tier 0 records.

These records are LOCAL ONLY and must never be promoted. Publishing them
would assert that named galleries are exhibiting at a named fair — a public
claim about third parties who have not made it. The data is true; it is not
attested, and in this project those are different things.

Stdlib only: the String's dependency list is fastapi + uvicorn and stays that
way, so Artworld is read by shelling out to `psql` rather than installing a
database driver.
"""
from __future__ import annotations

import datetime as _dt

SOURCE_APP = "seed-frieze"


def day_list(start: str, end: str) -> list[str]:
    """Every date the fair runs, inclusive of both ends."""
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    if d1 < d0:
        raise ValueError(f"end {end} is before start {start}")
    return [(d0 + _dt.timedelta(days=i)).isoformat()
            for i in range((d1 - d0).days + 1)]


def fair_event(fair: dict, start: str, end: str, now: str) -> tuple[str, dict]:
    """One event for the whole fair.

    Not one per day: a stand is present for the entire run, so per-day events
    would need 177 lineups each. Which day the collector means to visit a
    stand is part of their plan, which is app-local state, not a record.
    """
    slug = fair["slug"]
    year = fair.get("edition_year")
    name = f"{fair['name']} {year}" if year else fair["name"]
    body = {
        "$type": "community.lexicon.calendar.event",
        "name": name,
        "createdAt": now,
        "startsAt": f"{start}T00:00:00Z",
        "endsAt": f"{end}T23:59:59Z",
    }
    if fair.get("city"):
        body["description"] = f"{name}, {fair['city']}."
    # Tagged so Rounds can read the slug back off the seeded event.
    body["tags"] = ["seed:artworld", f"fair:{slug}"]
    return f"frieze:{slug}:fair", body


def stand_lineup(row: dict, event_uri: str, fair_slug: str,
                 artists: list[str], now: str) -> tuple[str, dict]:
    """One gallery's presence at the fair.

    `venue` is deliberately absent. It is a strongRef to a gallery's own
    repository, and these galleries have none — venue.profile is keyed
    `literal:self`, so a repo describes itself. Naming the gallery through
    `billing` (whose creditRef needs only a name) claims nothing on its
    behalf, and leaves `venue` free to become a real attestation if a gallery
    ever publishes a profile.
    """
    billing = [{"name": row["name"], "role": "gallery"}]
    billing += [{"name": a, "role": "artist"} for a in artists if a]

    tags = ["seed:artworld", f"fair:{fair_slug}"]
    if row.get("section"):
        tags.append(f"section:{row['section']}")

    body = {
        "$type": "com.cultureblocs.venue.lineup",
        "event": {"uri": event_uri},
        "billing": billing[:20],          # creditRef maxLength
        "tags": tags[:8],                 # lexicon maxLength
        "createdAt": now,
    }
    note = (row.get("description") or "").strip()
    if note:
        body["note"] = note

    return f"frieze:{fair_slug}:stand:{row['gallery_id']}", body
