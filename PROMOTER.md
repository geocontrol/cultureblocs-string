# The promoter: strands as signed ATProto records

`scripts/promote.py` publishes told strands from your String into a real
ATProto repository. The String stays the source of truth; the published copy
is the signed press release. Release one targets the Bluesky-hosted PDS —
sovereignty is preserved by protocol-level account portability, and by the
fact that the String never leaves your machine.

## One-time setup: a personal account

Personal strands should be published under a PERSONAL identity, not the
org's. (Use the cultureblocs.com account only for org strands — meetups,
announcements.)

1. Create a Bluesky account for yourself (or use an existing one).
2. Optional but recommended — claim a domain handle, e.g. `mark.geekyoto.com`:
   Settings → Handle → "I have my own domain", then add at your DNS:

       TXT  _atproto.mark.geekyoto.com   "did=did:plc:YOURDID"

3. Make an app password (Settings → Privacy & Security → App Passwords).

## Commands

    python scripts/promote.py list                # strands + published state
    BSKY_HANDLE=mark.geekyoto.com \
    BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx \
      python scripts/promote.py publish <strand-id>
    python scripts/promote.py status              # detect local edits (drift)
    python scripts/promote.py unpublish <strand-id>

Publish writes beads first (collection = their type, rkey = String id), then
the strand with strongRefs to them; the returned at:// URIs land back in the
String, and the timeline shows a "published" chip on everything published.
Re-publishing after edits overwrites in place (`status` tells you when
that's needed). Unpublish deletes the public records and clears the chips;
local records are untouched.

## What gets stripped

Same discipline as the static exporter, applied for the open network:
geo coordinates, all provenance (devices, mintIds, apps), and — release one
only — media. Place names, notes, tags, links, works, kinds and times
survive. The note text publishes exactly as written: selecting a strand is
the act of consent.

## Known limitations (release one)

- **No media blobs yet.** Correctly referencing blobs needs a small lexicon
  evolution (media as blob fields) — until then photos live on your static
  site exports only.
- **Public visibility is real**: records go through the firehose and are
  fetchable by anyone immediately. Unpublish deletes them, but caches and
  indexes may retain copies — publish like you mean it.
- Viewing published records: any AT browser, e.g.
  https://pdsls.dev/at://<your-handle>
