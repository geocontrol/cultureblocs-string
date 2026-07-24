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

    lexicons/com/cultureblocs/  the schema commons: defs, bead, annotation, strand
    string/                     the String service (FastAPI + SQLite WAL)
    studio/                     CultureBloc Studio — pull the totem over Web
                                Serial, resolve times, tell, push to the String
    timeline/                   "the day's string" — annotate, photos, links,
                                group into strands, publish
    web/                        <cultureblocs-strands> embed component
                                (CANONICAL COPY — always copy outward from here)
    scripts/                    mint, promote, export, lexicon publication, seed
    workers/                    scrobbler (Last.fm -> listen beads)
    sdk/python/                 offline capture queue (Swift port pending for AR)
    bridge/                     scripted totem-dump -> bead path
    skill/                      agent skill: drive the String from Claude Code

## Quick start

    docker compose up -d --build
    python scripts/seed_demo.py          # optional example day

| Port  | Surface |
|-------|---------|
| :8100 | String API |
| :8101 | Timeline ("the day's string") |
| :8102 | CultureBloc Studio |
| :8103 | Pocket Totem (PWA — phone minting) |

Open the timeline, load a day, and you have the whole loop minus a totem.

## Minting — where beads begin

- **Totem** (M5Stack StickS3): mint by button press, mutual press for
  encounters; pull over USB in the **Studio** (:8102), which resolves the
  device's elapsed-time counters to real instants, manages the mask
  wardrobe, and pushes kept beads in.
- **By hand**: `python scripts/mint.py --note "..." --kind read`
  — for moments no device witnessed. See `--help` for kinds, tags,
  place, links, and backdating.
- **Scrobbler**: `workers/scrobbler.py` polls Last.fm, clusters plays
  into listening sessions, and proposes one `listen` bead per closed
  session. Machine-minted beads sit on a dotted rail in the timeline
  with a release button — proposals, not facts, until you keep them.
  Run hourly (cron / LaunchAgent); idempotent by construction.

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
    python scripts/promote.py status          # drift since publish

What publishes: place names, notes, tags, links, works, kinds, times.
What never leaves: geo coordinates, provenance, device ids, mintIds,
and (release one) media. Full details in [PROMOTER.md](PROMOTER.md).

Published strands render anywhere via the embed component — live from
a repo (`<cultureblocs-strands actor="handle">`) or from a baked export
(`scripts/export_public.py`, see below).

## Static export (photo-capable)

    python scripts/export_public.py export <strand-id> --out <site>/cultureblocs

Same privacy strip, plus media copied content-addressed — currently the
only path that publishes photos, until media blobs land in the promoter.

## API surface (selected)

| Endpoint | Purpose |
|---|---|
| `POST /records` | batch ingest, idempotent on `dedupeKey`, lexicon-validated |
| `GET /records?day=&type=&sourceApp=` · `GET /days` | query |
| `PATCH /records/{id}` | edit the envelope (note, tags, links…), re-validated |
| `GET /changes?since=` | append-only feed with cursor (workers hook here) |
| `POST /media` · `GET /media/{name}` | content-addressed photo store |
| `PUT/GET/DELETE /identities…` | held publishing identities (passwords never returned) |
| `POST /publish/{strand}` · `POST /unpublish/{strand}` | server-side Stage F |

Auth: set `STRING_TOKEN` to require a bearer token on every call.

## Configuration

`STRING_DB`, `STRING_LEXICONS`, `STRING_MEDIA`, `STRING_TOKEN` (the old
`SPINE_*` names still work). Scripts honour `STRING_URL`/`STRING_TOKEN`
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
