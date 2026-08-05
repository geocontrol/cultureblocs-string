#!/usr/bin/env python3
"""Refresh the vendored Lexicon Community schemas from their repository.

These are other people's schemas (MIT licensed). We hold copies only so
the String can validate records that use them; the authority is the
@lexicons.lexicon.community repository, which is what this reads.
"""
import json
import pathlib
import urllib.request

DID = "did:plc:mtr7qrqtcyseedx3jyr5o7db"
WANT = ["community.lexicon.calendar.event", "community.lexicon.calendar.rsvp",
        "community.lexicon.location.address", "community.lexicon.location.geo",
        "community.lexicon.location.fsq", "community.lexicon.location.hthree"]
ROOT = pathlib.Path(__file__).resolve().parents[1] / "lexicons"


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def main() -> None:
    doc = get(f"https://plc.directory/{DID}")
    pds = [s["serviceEndpoint"] for s in doc["service"]
           if s["id"] == "#atproto_pds"][0]
    for nsid in WANT:
        rec = get(f"{pds}/xrpc/com.atproto.repo.getRecord?repo={DID}"
                  f"&collection=com.atproto.lexicon.schema&rkey={nsid}")
        value = rec["value"]
        value.pop("$type", None)
        path = ROOT / (nsid.replace(".", "/") + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")
        print(f"vendored {nsid}")


if __name__ == "__main__":
    main()
