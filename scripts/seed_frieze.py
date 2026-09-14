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
NOTE_MAX = 2000          # com.cultureblocs.venue.lineup.note maxGraphemes


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
        # venue.lineup.note is capped at maxGraphemes 2000, and ten of Frieze's
        # gallery descriptions exceed it. Without this, those galleries fail
        # validation and vanish from the fair entirely — a truncated description
        # is a far smaller loss than a missing exhibitor. The ellipsis keeps the
        # truncation visible rather than pretending the text simply ends there.
        if len(note) > NOTE_MAX:
            note = note[:NOTE_MAX - 1].rstrip() + "…"
        body["note"] = note

    return f"frieze:{fair_slug}:stand:{row['gallery_id']}", body


import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

PG_CONTAINER = "artworld-postgres-1"
PG_USER = "artworld"
PG_DB = "artworld"


def _psql(sql: str) -> list[dict]:
    """Run a query in Artworld's Postgres and return rows as dicts.

    Results come back as one JSON object per line via row_to_json, so
    descriptions containing quotes, pipes or newlines survive intact — a
    delimiter-separated format would not.
    """
    proc = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
         "-At", "-c", sql],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"psql failed: {proc.stderr.strip()}")
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def read_fair(slug: str) -> dict:
    rows = _psql(f"""
        select row_to_json(t) from (
          select slug, name, city, country, edition_year,
                 start_date::text, end_date::text
          from fair where slug = '{slug}'
        ) t;""")
    if not rows:
        sys.exit(f"no fair with slug {slug!r} in Artworld")
    return rows[0]


def read_stands(slug: str) -> list[dict]:
    return _psql(f"""
        select row_to_json(t) from (
          select g.id as gallery_id, g.canonical_name as name,
                 p.section, p.booth, coalesce(g.description, '') as description
          from fair_participation p
          join fair f on f.id = p.fair_id
          join gallery g on g.id = p.gallery_id
          where f.slug = '{slug}'
          order by g.canonical_name
        ) t;""")


def read_rosters(slug: str) -> dict[int, list[str]]:
    """Artist names per gallery, for the galleries at this fair."""
    rows = _psql(f"""
        select row_to_json(t) from (
          select ga.gallery_id, a.display_name as artist
          from gallery_artist ga
          join artist a on a.id = ga.artist_id
          join fair_participation p on p.gallery_id = ga.gallery_id
          join fair f on f.id = p.fair_id
          where f.slug = '{slug}'
          order by ga.gallery_id, a.display_name
        ) t;""")
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["gallery_id"], []).append(r["artist"])
    return out


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "brick")


def _assert_local(string_url: str) -> None:
    """Refuse to seed anything that is not demonstrably a local String.

    These records name real galleries as exhibiting at a real fair. They are
    true and unattested, which is why they stay on this machine. A mistyped
    --string must not be able to push them somewhere public.
    """
    from urllib.parse import urlparse
    host = (urlparse(string_url).hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".ts.net"):
        return
    sys.exit(
        f"refusing to seed {string_url!r}: seeded fair data is Tier 0 and must "
        f"stay local. Allowed hosts: {', '.join(LOCAL_HOSTS)}, or a tailnet "
        f"(*.ts.net).")


def _patch_record(string_url: str, token: str | None, rid: str, fields: dict) -> None:
    """PATCH shallow-merges `fields` into the record's body — see string/app/main.py."""
    data = json.dumps({"fields": fields}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{string_url.rstrip('/')}/records/{rid}", data=data,
        headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"PATCH /records/{rid} failed: {e.code}\n  {e.read().decode()[:500]}")


def _summarize(counts: dict) -> str:
    parts = [f"{counts[k]} {k}" for k in ("created", "updated", "invalid") if counts.get(k)]
    return ", ".join(parts) if parts else "no changes"


def post_records(string_url: str, token: str | None,
                 records: list[dict]) -> dict:
    """Ingest in batches (the endpoint accepts 500; 100 keeps errors readable).

    db.py's upsert() is insert-or-ignore on dedupeKey, so a record the String
    already has comes back `duplicate` and is otherwise untouched. That is
    correct for beads (mint facts) but wrong for a re-seed meant to correct
    fair dates or gallery data in place: without a follow-up write, re-running
    this script against 177 live stands would silently do nothing. So a
    `duplicate` gets a PATCH with the freshly computed body — the ingest
    response carries the existing record's `id` even when it reports
    `duplicate`, so no extra lookup is needed.
    """
    counts = {"created": 0, "updated": 0, "invalid": 0}
    for i in range(0, len(records), 100):
        chunk = records[i:i + 100]
        data = json.dumps({"records": chunk}).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{string_url.rstrip('/')}/records", data=data,
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            sys.exit(f"POST /records failed: {e.code}\n  {e.read().decode()[:500]}")
        for rec, res in zip(chunk, body.get("results", [])):
            status = res["status"]
            if status == "invalid":
                counts["invalid"] += 1
                print(f"  invalid {res['dedupeKey']}: {res.get('problems')}")
            elif status == "created":
                counts["created"] += 1
            elif status == "duplicate":
                _patch_record(string_url, token, res["id"], rec["body"])
                counts["updated"] += 1
    return counts


def main() -> None:
    import os
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fair", default="frieze-london-2026")
    p.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    p.add_argument("--end", required=True, help="last day, YYYY-MM-DD")
    p.add_argument("--string", default=os.environ.get("STRING_URL",
                                                      "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.fair):
        sys.exit(f"invalid --fair slug {args.fair!r}: expected lowercase letters, "
                 f"digits and hyphens only")

    _assert_local(args.string)
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fair = read_fair(args.fair)
    if fair.get("start_date") and fair.get("end_date"):
        print(f"note: Artworld now has dates for {args.fair} "
              f"({fair['start_date']} to {fair['end_date']}); "
              f"using the --start/--end you gave instead.")

    ev_key, ev_body = fair_event(fair, args.start, args.end, now)
    days = day_list(args.start, args.end)
    print(f"{fair['name']}: {len(days)} day(s), {args.start} to {args.end}")

    # The event must exist before the stands can reference it, so it is
    # ingested first and its id read back to build the reference.
    ev_rec = {"dedupeKey": ev_key, "type": ev_body["$type"],
              "sourceApp": SOURCE_APP, "createdAt": now, "body": ev_body}

    stands = read_stands(args.fair)
    rosters = read_rosters(args.fair)
    print(f"  {len(stands)} exhibitor(s), "
          f"{sum(1 for s in stands if s.get('section'))} with a section, "
          f"{len(rosters)} with a roster")

    # billing[:20] in stand_lineup() keeps 1 gallery entry + 19 artists; any
    # roster longer than that is silently truncated, alphabetically (the
    # roster query orders by name), which biases which artists are
    # search-findable in Rounds. A lexicon change is out of scope for this
    # wave, so the loss is made visible here instead of staying silent.
    total_artists = sum(len(a) for a in rosters.values())
    dropped_artists = sum(max(0, len(a) - 19) for a in rosters.values())
    capped_stands = sum(1 for a in rosters.values() if len(a) > 19)
    print(f"  rosters: {total_artists} artist(s), {dropped_artists} dropped "
          f"to fit the 20-entry billing limit "
          f"({capped_stands} of {len(stands)} stands at the cap)")

    if args.dry_run:
        print(json.dumps(ev_rec, indent=2)[:600])
        k, b = stand_lineup(stands[0], "spine://records/<pending>",
                            args.fair, rosters.get(stands[0]["gallery_id"], []), now)
        print(json.dumps({"dedupeKey": k, "body": b}, indent=2)[:800])
        print(f"(dry run — would ingest 1 event and {len(stands)} stands)")
        return

    ev_counts = post_records(args.string, args.token, [ev_rec])
    print(f"  event: {_summarize(ev_counts)}")

    event_id = _find_record_id(args.string, args.token, ev_key)
    event_uri = f"spine://records/{event_id}"

    records = []
    for row in stands:
        key, body = stand_lineup(row, event_uri, args.fair,
                                 rosters.get(row["gallery_id"], []), now)
        records.append({"dedupeKey": key, "type": body["$type"],
                        "sourceApp": SOURCE_APP, "createdAt": now,
                        "body": body})
    stand_counts = post_records(args.string, args.token, records)
    print(f"  stands: {_summarize(stand_counts)}")


def _find_record_id(string_url: str, token: str | None, dedupe_key: str) -> str:
    """The ingest response carries the id, but a re-run reports `duplicate`
    with the existing id, so read it back rather than assuming."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(
        f"{string_url.rstrip('/')}/records?type=community.lexicon.calendar.event&limit=500",
        headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read())
    rows = rows if isinstance(rows, list) else rows.get("records", [])
    for row in rows:
        # Verified against the running String: the API returns camelCase.
        if row.get("dedupeKey") == dedupe_key:
            return row["id"]
    sys.exit(f"could not find the seeded event {dedupe_key!r} after ingest")


if __name__ == "__main__":
    main()
