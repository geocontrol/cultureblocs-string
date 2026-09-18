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

One strip, in `string/app/strip.py`, used by the publisher, this script
and the static exporter, and mirrored for browser clients in
`sdk/js/strip.js`. `tests/fixtures/strip-cases.json` is the specification
both are tested against — read it for the exact rules.

It is an allowlist at every depth: a field it does not name does not
publish. Geo coordinates, all provenance (devices, mintIds, apps) and
local media refs never leave; a work's local `image` never leaves. Place
names, notes, tags, links, kinds and times survive, as do refs — minus
resolver bookkeeping, and with three rules for people, because a bare name
may be a private individual (LOOM.md §9.8):

- a person ref — or a ref of any type other than work, event, venue or
  concept — publishes only with a DID or a **public-authority** id
  (wikidata, viaf, isni, orcid, musicbrainz, discogs, ipi); its ids from
  any other scheme (an email, a handle) never publish;
- a work's `creator` name publishes only when the work or its maker is
  identified (a `creatorDid`, the work's own DID, or an external id), so
  "a painting by J" keeps J local;
- a `did` or `creatorDid` that is not a well-formed DID counts as absent.
The note text publishes exactly as written: selecting a strand is the act
of consent.

## Syndication: posting a published strand elsewhere

The PDS is where a strand lives; other services get renderings of it
(POSSE). `POST /publish/<id>` takes two optional fields:

    { "identity": "personal", "destinations": ["bluesky"], "postText": "A day out" }

and runs in two phases. Phase 1 is the publish above, unchanged. Phase 2
posts to each destination and reports it under `syndications` in the
answer: `posted` (with `remoteUrl`), `already` (used before, so skipped), or
`failed` (with `reason`). A failed destination leaves the strand published
and records nothing, so it can be tried again. Bad requests — an unknown
destination, empty text, text over a destination's limit — are refused
with 422 **before** anything publishes.

`GET /destinations` lists what exists and each one's limits.

**One-shot.** Each (strand, destination) pair is posted once; the
`syndications` table enforces it, so republishing never double-posts.
Unpublishing a strand does not delete its posts.

**Bluesky** writes an `app.bsky.feed.post` into the same repo, under the
session the publish already opened, with up to four of the images phase 1
already uploaded — reused, not re-uploaded. The text is exactly what was
written, at most 300 characters (counted in code points, like the lexicon
validator). No link back yet: there is no per-strand web page to point at.

**Adding a destination** is one module in `string/app/syndicate/` exposing
`NAME`, `LIMITS` and `post(session, strand, items, text)`, plus one line in
`DESTINATIONS`. If it composes text from `narrative` or a bead's `note`, it
must route that text through the strip first.

## Known limitations (release one)

- **Media now publishes**: at publish time, each bead's local photos are
  uploaded as ATProto blobs into a `photos` field (images ≤2 MB; larger
  files are skipped). Unpublish deletes the records and the PDS
  garbage-collects the blobs.
- **Public visibility is real**: records go through the firehose and are
  fetchable by anyone immediately. Unpublish deletes them, but caches and
  indexes may retain copies — publish like you mean it.
- Viewing published records: any AT browser, e.g.
  https://pdsls.dev/at://<your-handle>
