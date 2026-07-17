#!/usr/bin/env python3
"""CultureBloc bridge: device mint log -> hydrated bead records -> Spine.

Input format (adapt `parse_mint_events` to your C4 sync export): JSONL,
one mint event per line:

    {"mintId": "a1b2...", "seq": 12, "kind": "mutual",
     "ticks": 348122, "peerDeviceId": "bloc-7f", "tagId": null}

Time anchoring (no RTC on the StickS3): pass the device's tick counter
value *at sync time* and the wall-clock UTC *at sync time*; every event's
timestamp is back-computed as  utc_now - (ticks_now - event.ticks).

Usage:
    python culturebloc_bridge.py mints.jsonl \
        --ticks-now 401500 --utc-now 2026-07-08T18:30:00Z \
        --tick-ms 1000 --device bloc-3a \
        --spine http://localhost:8100 [--token X] \
        [--place "Tate Britain"] [--lat 51.4911 --lng -0.1278 --precision 100m]

Everything is idempotent: re-running the same export is a no-op.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))
from cultureblocs_capture import CaptureQueue  # noqa: E402

KIND_MAP = {"solo": "visit", "mutual": "encounter", "dwell": "dwell"}


def parse_mint_events(path: Path) -> list[dict]:
    """ADAPTATION POINT: swap this for your real C4 sync export reader
    (CBOR batches over BLE/WiFi). Contract out: list of dicts with at
    least mintId, ticks, kind."""
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def anchor(ticks: int, ticks_now: int, utc_now: datetime, tick_ms: int) -> str:
    dt = utc_now - timedelta(milliseconds=(ticks_now - ticks) * tick_ms)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def hydrate(ev: dict, args, ts: str) -> dict:
    kind = KIND_MAP.get(ev.get("kind", "solo"), "note")
    body: dict = {
        "$type": "com.cultureblocs.bead",
        "createdAt": ts,
        "kind": kind,
        "provenance": {
            "app": "culturebloc",
            "device": args.device,
            "mintedAt": ts,
            "mutualMint": ev.get("kind") == "mutual",
        },
    }
    if args.place or (args.lat is not None and args.lng is not None):
        place: dict = {}
        if args.place:
            place["name"] = args.place
        if args.lat is not None and args.lng is not None:
            place["geo"] = {"lat": args.lat, "lng": args.lng,
                            "precision": args.precision}
        body["subject"] = place
    if ev.get("kind") == "mutual" and ev.get("peerDeviceId"):
        # Peer stays in a note pending encounter confirmation (Tier 0 only).
        body["note"] = f"mutual mint with device {ev['peerDeviceId']}"
    return body


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mints", type=Path)
    p.add_argument("--ticks-now", type=int, required=True)
    p.add_argument("--utc-now", required=True)
    p.add_argument("--tick-ms", type=int, default=1000,
                   help="milliseconds per device tick")
    p.add_argument("--device", required=True)
    p.add_argument("--spine", default="http://localhost:8100")
    p.add_argument("--token")
    p.add_argument("--place")
    p.add_argument("--lat", type=float)
    p.add_argument("--lng", type=float)
    p.add_argument("--precision", default="100m",
                   choices=["exact", "100m", "1km", "city"])
    p.add_argument("--queue", default="~/.cultureblocs/bridge-queue.jsonl")
    args = p.parse_args()

    utc_now = datetime.fromisoformat(args.utc_now.replace("Z", "+00:00"))
    q = CaptureQueue(args.queue, app="culturebloc-bridge")

    events = parse_mint_events(args.mints)
    for ev in events:
        ts = anchor(ev["ticks"], args.ticks_now, utc_now, args.tick_ms)
        body = hydrate(ev, args, ts)
        q.capture("com.cultureblocs.bead", dedupe_key=ev["mintId"],
                  created_at=ts, body=body)
    print(f"queued {len(events)} events")

    try:
        result = q.flush(args.spine, token=args.token)
        print(f"flushed: {result}")
    except Exception as exc:  # offline is fine — queue persists
        print(f"spine unreachable ({exc}); records kept in queue, "
              f"re-run flush later")


if __name__ == "__main__":
    main()
