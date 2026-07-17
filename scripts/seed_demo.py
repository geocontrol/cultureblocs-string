#!/usr/bin/env python3
"""Seed the Spine with the canonical example day:
Tate visit -> Hockney exhibition -> met Jenny -> dwell at a painting
(AR bookmark) -> evening screening at the Curzon Soho.

Usage: python scripts/seed_demo.py [--spine http://localhost:8100] [--token X]
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))
from cultureblocs_capture import CaptureQueue

DAY = "2026-07-04"


def bead(kind, t, place=None, note=None, geo=None, mutual=False):
    body = {
        "$type": "com.cultureblocs.bead",
        "createdAt": f"{DAY}T{t}:00Z",
        "kind": kind,
        "provenance": {"app": "culturebloc", "device": "bloc-3a",
                       "mintedAt": f"{DAY}T{t}:00Z", "mutualMint": mutual},
    }
    if place:
        subj = {"name": place}
        if geo:
            subj["geo"] = geo
        body["subject"] = subj
    if note:
        body["note"] = note
    return body


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spine", default="http://localhost:8100")
    p.add_argument("--token")
    args = p.parse_args()

    q = CaptureQueue("/tmp/cultureblocs-seed-queue.jsonl", app="seed")
    tate = {"lat": 51.4911, "lng": -0.1278, "precision": "100m"}
    soho = {"lat": 51.5133, "lng": -0.1312, "precision": "100m"}

    records = [
        ("com.cultureblocs.bead", bead("visit", "11:02", "Tate Britain", geo=tate)),
        ("com.cultureblocs.bead", bead(
            "visit", "11:20", "Tate Britain",
            note="David Hockney — 'Time & More' rooms 1-6", geo=tate)),
        ("com.cultureblocs.bead", bead(
            "encounter", "12:05", "Tate Britain",
            note="mutual mint with Jenny (bloc-7f)", geo=tate, mutual=True)),
        ("com.cultureblocs.bead", bead(
            "dwell", "12:40", "Tate Britain",
            note="stopped a long while here", geo=tate)),
        ("com.cultureblocs.annotation", {
            "$type": "com.cultureblocs.annotation",
            "createdAt": f"{DAY}T12:41:00Z",
            "work": {"wikidata": "Q1892745",
                     "title": "A Bigger Splash",
                     "creator": "David Hockney", "date": "1967"},
            "note": "the stillness right after the dive — came back to it twice",
            "matchConfidence": "embedding",
            "geo": tate,
            "provenance": {"app": "ar-gallery",
                           "mintedAt": f"{DAY}T12:41:00Z"},
        }),
        ("com.cultureblocs.bead", bead(
            "screening", "19:30", "Curzon Soho",
            note="'The Backrooms' — sold-out screen 1", geo=soho)),
    ]
    for rtype, body in records:
        q.capture(rtype, dedupe_key=str(uuid.uuid4()),
                  created_at=body["createdAt"], body=body)
    print(q.flush(args.spine, token=args.token))


if __name__ == "__main__":
    main()
