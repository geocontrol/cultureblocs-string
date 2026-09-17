# cultureblocs string

*Beads on a thread — in the lineage of the quipu, the Andean knot-records.
Formerly "the Spine": the service was renamed, but the API, the data, and
the `spine://` record URIs inside existing strands are unchanged, and old
`SPINE_*` environment variables still work.*

The String is a small, self-hosted record store for your cultural life.
Moments are minted as **beads** (a gallery visit, a film, a book, a
listening session, an encounter), told into **strands** (the story of a
day or an evening), and kept locally — validated against the open
[`com.cultureblocs.*` lexicons](https://www.cultureblocs.com/lexicons.html),
which resolve through cultureblocs.com as a formal ATProto schema
authority.

Three principles, enforced by architecture rather than policy:

- **Local-first** — everything works offline; the String runs on your
  machine and is the source of truth.
- **Own your data** — one SQLite file, open schemas, every export yours.
- **Privacy by default** — records start private. Publishing is a
  deliberate act per strand, with locations, device identifiers and
  provenance stripped on the way out. The wire format is already the
  federation format, so publication is a copy, not a migration.

## Layout

    lexicons/com/cultureblocs/  the schema commons:
                                defs, bead, annotation, strand;
                                creative/{profile,work,connection};
                                venue/{profile,lineup}
    lexicons/community/         vendored Lexicon Community schemas
                                (calendar events + RSVPs, locations)
    string/                     the String service (FastAPI + SQLite WAL)
    timeline/                   "the day's string" — annotate, photos, links,
                                group into strands, publish
    web/                        <cultureblocs-strands> embed component
                                (CANONICAL COPY — always copy outward from here)
    scripts/                    mint, creative, venue, promote, export,
                                lexicon publication, seed
    workers/                    scrobbler (Last.fm -> listen beads)
    appview/                    network index: Jetstream consumer + query API
    sdk/python/                 offline capture queue (Swift port pending for AR)
    sdk/js/                     lexicon validator + publish strip for
                                browser clients (CANONICAL COPY — the
                                Python and JS halves are held together by
                                tests/fixtures/*.json)
    bridge/                     scripted totem-dump -> bead path
    skill/                      agent skill: drive the String from Claude Code

## Quick start

    docker compose up -d --build
    python scripts/seed_demo.py          # optional example day

| Port  | Surface |
|-------|---------|
| :8100 | String API |
| :8101 | Timeline ("the day's string") |
| :8103 | Pocket Totem (PWA — phone minting; live at cultureblocs.com/pocket/) |
| :8104 | AppView (network index — public references) |

Open the timeline, load a day, and you have the whole loop minus a totem.

## Minting — where beads begin

- **Totem** (M5Stack StickS3): mint by button press, mutual press for
  encounters; pull over USB from **Loom's Feeds surface**
  ([cultureblocs-loom](https://github.com/geocontrol/cultureblocs-loom), :8108),
  which resolves the device's elapsed-time counters to real instants, manages
  the mask wardrobe, and lands kept beads as proposals you keep or release
  before they reach the String.
- **CreativeID & venues**: `scripts/creative.py` (profile / work /
  connect) and `scripts/venue.py` (profile / listing) — self-asserted
  claims and venue listings that beads can point at. See
  [CREATIVE-AND-VENUE.md](CREATIVE-AND-VENUE.md).
- **Pocket Totem** (`pocket/`, also deployed at
  [cultureblocs.com/pocket](https://www.cultureblocs.com/pocket/)): mask
  and mint on a phone. Beads queue locally. Two destinations: your String
  (set a URL), or — signed in with **ATProto OAuth** — your own
  repository, no server of your own required. Either way publishing is a
  deliberate press, never a side effect. Scanning a venue's QR attaches
  that event to what you mint.
- **By hand**: `python scripts/mint.py --note "..." --kind read`
  — for moments no device witnessed. See `--help` for kinds, tags,
  place, links, and backdating.
- **Scrobbler**: `workers/scrobbler.py` polls Last.fm, clusters plays
  into listening sessions, and proposes one `listen` bead per closed
  session. Machine-minted beads arrive with `state: proposal` and sit on
  a dotted rail in the timeline with **keep** and **release** buttons —
  proposals, not facts, until you keep them. Run hourly (cron /
  LaunchAgent); idempotent by construction, and a session still in
  proposal may be *revised* by a later run (a set that turned out to have
  more tracks in it). The moment you keep it, no worker can touch it
  again.

## Telling — the timeline

Annotate notes (⌘/Ctrl-Enter to save), attach photos, set kind/tags/
place/links, select beads and **group into strands** — the publishable
story unit, with its own title, place and event link.

## Publishing — strands to the Atmosphere

The String holds **identities** (ATProto accounts) and publishes
server-side; the timeline gets publish / republish / unpublish buttons
per strand, with a confirm showing which identity will speak:

    curl -X PUT http://localhost:8100/identities/personal \
      -H 'content-type: application/json' \
      -d '{"handle":"you.bsky.social","appPassword":"xxxx-xxxx-xxxx-xxxx"}'

Use **app passwords**, never account passwords. Multiple identities are
the point: personal strands publish as you, organisational strands as
the org — same desk, different letterhead. CLI equivalent:

    python scripts/promote.py publish <strand-id> --identity personal
    python scripts/promote.py publish <record-id> --identity venue   # listings, claims
    python scripts/promote.py status          # drift since publish

What publishes: place names, notes, tags, links, kinds, times, and refs —
what an entry is about. What never leaves: geo coordinates, provenance,
device ids, mintIds, local media, and any person named only by name.
Full details in [PROMOTER.md](PROMOTER.md).

Published strands render anywhere via the embed component — live from
a repo (`<cultureblocs-strands actor="handle">`) or from a baked export
(`scripts/export_public.py`, see below).

## The round trip: records that were born public

A bead minted on a phone and published to your own repository has no
private original — it is born public. Bring it home to edit it:

    python scripts/import_repo.py --actor you.bsky.social --dry-run
    python scripts/import_repo.py --actor you.bsky.social

Imported records keep their public identity (`dedupeKey` is the at:// URI,
so re-running imports nothing twice) and remember their published twin.
Annotate them, attach photos, group them into strands, then re-publish:
because the String reuses the original record key, the public record is
**updated in place** rather than gaining an orphaned twin.

Two things follow from being born public. There is no richer private
version to fall back on — what you minted is what the world saw. And
every later edit is a public amendment, visible in your repository's
commit history. That is honest, and worth knowing before you edit a note
someone already read.

## Static export (photo-capable)

    python scripts/export_public.py export <strand-id> --out <site>/cultureblocs

Same privacy strip, plus media copied content-addressed — currently the
only path that publishes photos, until media blobs land in the promoter.

## API surface (selected)

| Endpoint | Purpose |
|---|---|
| `POST /records` | batch ingest, idempotent on `dedupeKey`, lexicon-validated |
| `GET /records?day=&type=&sourceApp=` · `GET /days` | query |
| `PATCH /records/{id}` | edit the envelope (note, tags, links…), re-validated. Send `If-Match: <hlc>` to be refused with 412 rather than silently overwrite a version you never saw; a field sent as `null` is removed |
| `DELETE /records/{id}` | delete a record; `If-Match: <hlc>` refuses with 412 as PATCH does |
| `POST /records/{id}/state` | proposal → kept, and the other states |
| `GET /changes?since=` | append-only feed with cursor (workers hook here); rows carry `hlc`, `deviceId` and `actor` |
| `POST /media` · `GET /media/{name}` | content-addressed photo store |
| `PUT/GET/DELETE /identities…` | held publishing identities (passwords never returned) |
| `POST /publish/{strand}` · `POST /unpublish/{strand}` | server-side Stage F |

Auth: set `STRING_TOKEN` to require a bearer token on every call.
Writes may carry `X-Device-Id: <name>`, which is recorded in the change
feed — not a security control, but a second device replaying the log has
to be able to tell its own writes apart from everyone else's.

## Records have a state

`proposal | kept | draft | published | edited`, stored on the record
rather than guessed by each client from the producing app's name. A
proposal is a machine's suggestion and may be revised until a person
keeps it; everything else is a mint fact and is insert-once. Records
written before this column existed were backfilled once, on first start:
unpublished scrobbler beads became proposals and stay on the dotted rail,
while scrobbler beads that were already published became kept, so they
move from the dotted rail to the solid one.

## Tests

    python -m pytest tests/
    node --test "sdk/js/test/*.test.mjs"     # and easel/, web/, catalogue/

`tests/fixtures/lexicon-cases.json`, `strip-cases.json` and
`refs-cases.json` are run by both languages. They are the contract
between `string/app/lexicon.py` and `sdk/js/lexicon.js`, between
`string/app/strip.py` and `sdk/js/strip.js`, and between
`string/app/refs.py` and `sdk/js/refs.js` — change a rule and you change the fixture, and both
implementations tell you whether they still agree. The strip fixtures
decide what leaves your machine; treat them as the tests to be most
suspicious of.

## Configuration

`STRING_DB`, `STRING_LEXICONS`, `STRING_MEDIA`, `STRING_TOKEN` (the old
`SPINE_*` names still work). `STRING_DEVICE_ID` names this machine in
HLC stamps and change rows — set it on a host that matters (the brick),
where it should stay the same across restarts; it defaults to the
hostname. Scripts honour `STRING_URL`/`STRING_TOKEN`
and accept `--string`/`--spine` interchangeably.

## Data, backups, privacy

Everything lives in `data/` (gitignored): the SQLite database — which
now also holds identity **app passwords** — plus the media store. Back
up with `sqlite3 data/string.db ".backup backup.db"` and a copy of
`data/media/`. Treat `data/` as credential-bearing.

## Further docs

- [PUBLISHING.md](PUBLISHING.md) — lexicon publication: making
  cultureblocs.com a resolvable schema authority (done; kept as the
  update mechanism).
- [PROMOTER.md](PROMOTER.md) — publishing strands as signed records.
- [APPVIEW.md](APPVIEW.md) — the network index: how public references
  become counts, and what it deliberately does not do.
- [CREATIVE-AND-VENUE.md](CREATIVE-AND-VENUE.md) — the CreativeID and
  venue lexicons, the self-attest model, and how to run a venue pilot.
- [HOST-SPEC.md](HOST-SPEC.md) — the always-on host: a Raspberry Pi
  as a DataBrick for the household's cultural memory.
- [MEETUP-RUNBOOK.md](MEETUP-RUNBOOK.md) — an event, end to end:
  announce, mint on the night, tell, publish.
- [skill/cultureblocs-string/SKILL.md](skill/cultureblocs-string/SKILL.md)
  — install into Claude Code to mint/edit/publish conversationally.

## Related

- **cultureblocs.com** — the schema commons, apps, and London meetup
  ([site repo](https://github.com/Geocontrol) · the meetup page renders
  strands live from `@cultureblocs.com`).
- The embed component's canonical copy is `web/cultureblocs-strands.js`
  in THIS repo; site repos carry copies — copy outward only.
