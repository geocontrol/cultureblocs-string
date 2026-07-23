#!/usr/bin/env python3
"""Scrobble worker: turn Last.fm listening history into listen beads.

Polls Last.fm's user.getRecentTracks, clusters plays into listening
sessions (a gap of more than --gap minutes starts a new session), and
mints ONE com.cultureblocs.bead per *closed* session into the Spine:

    kind: listen
    note: "Boards of Canada — Geogaddi (11 tracks)" + timed track list
    tags: the session's artists (up to 4)
    provenance.app: "scrobbler"   <- the timeline renders these on the
                                     dotted machine rail with a release
                                     button; they are proposals, not
                                     mint facts, and flow through your
                                     normal curation.

Design properties:
  - Only CLOSED sessions are minted (last play older than --gap), so a
    session that is still growing is never half-captured.
  - dedupeKey = scrobble:{user}:{first track's unix time} -> re-running
    is always a no-op; the Spine ignores duplicates.
  - Sessions that may be truncated by the lookback window are skipped
    (they'll be complete on the next run with a longer window).
  - No Last.fm secret needed: reading your own public recent tracks
    only requires the API key. (If your Last.fm privacy settings hide
    recent listening, un-hide it or this returns nothing.)

Usage (one-shot; run from cron/launchd, e.g. hourly):
    LASTFM_USER=you LASTFM_API_KEY=xxx python workers/scrobbler.py
Options:
    --spine http://localhost:8100   --token <SPINE_TOKEN>
    --gap 30            session gap, minutes
    --lookback 48       how far back to fetch, hours
    --daemon --interval 900         loop mode instead of one-shot
    --from-json FILE    read a saved getRecentTracks JSON instead of
                        calling the API (testing / bulk history import)
    --dry-run           print sessions, mint nothing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://ws.audioscrobbler.com/2.0/"


def iso(uts: int) -> str:
    return datetime.fromtimestamp(uts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_recent(user: str, key: str, from_uts: int) -> list[dict]:
    """All tracks since from_uts, oldest first. Handles pagination."""
    tracks, page, pages = [], 1, 1
    while page <= pages:
        q = urllib.parse.urlencode({
            "method": "user.getrecenttracks", "user": user, "api_key": key,
            "format": "json", "limit": 200, "from": from_uts, "page": page})
        with urllib.request.urlopen(f"{API}?{q}", timeout=30) as r:
            data = json.loads(r.read())
        rt = data.get("recenttracks", {})
        attrs = rt.get("@attr", {})
        pages = int(attrs.get("totalPages", 1) or 1)
        got = rt.get("track", [])
        if isinstance(got, dict):        # API quirk: single track = object
            got = [got]
        tracks.extend(got)
        page += 1
    return normalise(tracks)


def normalise(raw: list[dict]) -> list[dict]:
    out = []
    for t in raw:
        if t.get("@attr", {}).get("nowplaying") == "true":
            continue                     # skip in-progress track
        if "date" not in t:
            continue
        out.append({
            "uts": int(t["date"]["uts"]),
            "artist": t.get("artist", {}).get("#text", "Unknown artist"),
            "title": t.get("name", "Unknown title"),
            "album": t.get("album", {}).get("#text", ""),
        })
    out.sort(key=lambda x: x["uts"])
    return out


def cluster(tracks: list[dict], gap_s: int) -> list[list[dict]]:
    sessions: list[list[dict]] = []
    for t in tracks:
        if sessions and t["uts"] - sessions[-1][-1]["uts"] <= gap_s:
            sessions[-1].append(t)
        else:
            sessions.append([t])
    return sessions


def summarise(session: list[dict]) -> tuple[str, list[str]]:
    artists = []
    for t in session:
        if t["artist"] not in artists:
            artists.append(t["artist"])
    albums = [t["album"] for t in session if t["album"]]
    dominant = max(set(albums), key=albums.count) if albums else ""
    n = len(session)
    if dominant and albums.count(dominant) >= max(2, n // 2) and len(artists) == 1:
        head = f"{artists[0]} — {dominant} ({n} track{'s' if n != 1 else ''})"
    elif len(artists) == 1:
        head = f"{artists[0]} ({n} track{'s' if n != 1 else ''})"
    else:
        head = f"{n} tracks: {', '.join(artists[:3])}{'…' if len(artists) > 3 else ''}"
    lines = [f"{iso(t['uts'])[11:16]}  {t['artist']} — {t['title']}" for t in session]
    body = head + "\n\n" + "\n".join(lines)
    if len(body) > 2800:                 # respect note maxGraphemes with margin
        body = body[:2760] + f"\n… (+{n} tracks total)"
    return body, artists[:4]


def to_record(session: list[dict], user: str) -> dict:
    first = session[0]["uts"]
    created = iso(first)
    note, artists = summarise(session)
    return {
        "dedupeKey": f"scrobble:{user}:{first}",
        "type": "com.cultureblocs.bead",
        "sourceApp": "scrobbler",
        "createdAt": created,
        "body": {
            "$type": "com.cultureblocs.bead",
            "createdAt": created,
            "kind": "listen",
            "note": note,
            "tags": artists,
            "provenance": {"app": "scrobbler", "mintedAt": created,
                           "timeAnchored": True},
        },
    }


def post(spine: str, token: str | None, records: list[dict]) -> list[dict]:
    req = urllib.request.Request(
        spine.rstrip("/") + "/records",
        data=json.dumps({"records": records}).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["results"]


def run_once(args) -> None:
    now = int(time.time())
    gap_s = args.gap * 60
    from_uts = now - args.lookback * 3600
    if args.from_json:
        raw = json.loads(open(args.from_json).read())
        tracks = normalise(raw.get("recenttracks", raw).get("track", raw)
                           if isinstance(raw, dict) else raw)
    else:
        tracks = fetch_recent(args.user, args.key, from_uts)
    sessions = cluster(tracks, gap_s)
    minted, skipped = [], 0
    for s in sessions:
        if now - s[-1]["uts"] <= gap_s:
            skipped += 1                  # still open — mint next run
            continue
        if not args.from_json and s[0]["uts"] - from_uts <= gap_s:
            skipped += 1                  # possibly truncated by window
            continue
        minted.append(to_record(s, args.user or "local"))
    if args.dry_run:
        for r in minted:
            print(f"-- {r['createdAt']}  {r['body']['note'].splitlines()[0]}")
        print(f"({len(minted)} closed sessions, {skipped} skipped)")
        return
    if not minted:
        print(f"nothing to mint ({len(sessions)} sessions seen, {skipped} open/truncated)")
        return
    results = post(args.spine, args.token, minted)
    n = lambda s: sum(1 for r in results if r["status"] == s)
    print(f"{len(minted)} sessions -> {n('created')} new beads, "
          f"{n('duplicate')} already minted, {n('invalid')} invalid")
    for r in results:
        if r["status"] == "invalid":
            print("  invalid:", r["problems"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--user", default=os.environ.get("LASTFM_USER"))
    p.add_argument("--key", default=os.environ.get("LASTFM_API_KEY"))
    p.add_argument("--string", "--spine", dest="spine", default=os.environ.get("STRING_URL") or os.environ.get("SPINE_URL", "http://localhost:8100"))
    p.add_argument("--token", default=os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN"))
    p.add_argument("--gap", type=int, default=30, help="session gap, minutes")
    p.add_argument("--lookback", type=int, default=48, help="hours of history to fetch")
    p.add_argument("--daemon", action="store_true")
    p.add_argument("--interval", type=int, default=900, help="daemon poll seconds")
    p.add_argument("--from-json")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not args.from_json and not (args.user and args.key):
        sys.exit("need LASTFM_USER and LASTFM_API_KEY (env or --user/--key)")
    if args.daemon:
        while True:
            try:
                run_once(args)
            except Exception as exc:     # keep the daemon alive
                print(f"error: {exc}", file=sys.stderr)
            time.sleep(args.interval)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
