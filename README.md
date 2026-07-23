# cultureblocs string

*Beads on a thread — in the lineage of the quipu, the Andean
knot-records. Formerly "the Spine"; the service renamed but the
API, data, and `spine://` record URIs are unchanged, and old
`SPINE_*` env vars still work.*

Tier 0 record bucket for the cultureblocs cultural graph. Every app
(CultureBloc bridge, AR gallery, manual entry) is an independent producer
writing lexicon-valid records into one place. Apps never talk to each
other — they share only the schemas in `lexicons/`.

The wire format is already the federation format: bodies are valid
`com.cultureblocs.*` records from day one, so later promotion to an
ATProto PDS is a copy, not a migration.

## Layout

    lexicons/org/cultureblocs/   defs, bead, annotation, strand (schema commons)
    spine/                      FastAPI + SQLite(WAL) record service
    sdk/python/                 offline capture queue (port to Swift for the AR app)
    bridge/                     CultureBloc mint-log -> bead hydrator (script path)
    studio/                     CultureBloc Studio — pull totem over Web Serial,
                                annotate, push beads to the String (primary device path)
    timeline/                   single-file day view ("the day's string")
    scripts/seed_demo.py        example day (Tate / Hockney / Curzon)

## Run

    docker compose up -d --build
    python scripts/seed_demo.py            # seed the example day
    open http://localhost:8101             # timeline (String at :8100)
    open http://localhost:8102             # CultureBloc Studio

Or without Docker:

    pip install -r string/requirements.txt
    STRING_DB=./data/string.db STRING_LEXICONS=./lexicons \
      uvicorn app.main:app --app-dir string --port 8100

Auth: set `STRING_TOKEN` in the compose file to require
`Authorization: Bearer <token>` on every call. At-venue access without
exposing anything publicly: put the host on Tailscale. Backup: copy
`data/string.db` plus any `*.jsonl` capture queues.

## CultureBloc Studio (the totem's desk)

The primary path from the StickS3 totem into the String. Pull beads over
Web Serial (Chrome/Edge; `http://localhost:8102` is a secure context —
a LAN IP is not, so use Tailscale HTTPS or open the file directly from
another machine), name the occasion, retag masks, annotate, keep/release,
then **Push to String** — kept beads become `com.cultureblocs.bead` records.

Timestamp handling, best truth first: current-epoch elapsed beads resolve
to exact UTC instants via the `---NOW <n> EPOCH <k>---` anchor (correct
across midnight); old-epoch beads (minted before a power loss) keep their
order but are flagged `timeAnchored: false`; legacy `t`-beads and
no-time beads use the date picker, also flagged. Dedupe: `cb:{mintId}`
when the firmware provides one (128-bit, shared across both parties on a
mutual mint — the encounter join key, carried in `provenance.mintId`),
falling back to a composite key for older firmware. Mixed firmware
generations in one dump all work.

## Interfaces

| Surface | Contract |
|---|---|
| `POST /records` | batch ingest; **idempotent on `dedupeKey`** (mintId / app UUID); each body validated against its `$type` lexicon; per-item result `created`/`duplicate`/`invalid` |
| `GET /records?day=&type=&sourceApp=` | day/type queries for UIs |
| `PATCH /records/{id}` | shallow-merge annotation edits (LWW), revision bump, re-validated |
| `GET /changes?since=N` | append-only change feed with cursor — the hook for the enrichment worker, CRDT upgrade, and the PDS promoter |
| `GET /days`, `/lexicons`, `/health` | navigation & introspection |

## CultureBloc bridge (scripted alternative)

A headless path for the same job — useful for batch imports or automation
when the browser isn't in the loop:

    python bridge/culturebloc_bridge.py mints.jsonl \
      --ticks-now 401500 --utc-now 2026-07-08T18:30:00Z \
      --device bloc-3a --place "Tate Britain" \
      --lat 51.4911 --lng -0.1278 --precision 100m

Time anchoring back-computes UTC from the device's monotonic ticks (no
RTC needed). `parse_mint_events()` is the marked adaptation point for the
real C4 sync export. Offline-safe: unreachable String leaves records in
the local queue; re-run to flush.

## AR gallery app

Port `sdk/python/cultureblocs_capture.py` to Swift (~200 lines: append
JSONL, flush batch, keep failures). On bookmark, capture an
`com.cultureblocs.annotation` with a `workRef` (Wikidata QID / accession
if resolved, descriptive fallback otherwise) and `matchConfidence`
(`embedding` | `geometric` | `manual`). The app stays fully standalone.

## Deliberately not here yet

Strand enrichment worker, encounter confirmation, the PDS + promoter
(Stage F: snapshot -> privacy-strip -> putRecord -> strongRef back), and
the CRDT upgrade. All of them consume `GET /changes` — the seam is in
place.

## Publishing strands to a static site (geekyoto-style)

Tier-2 promotion with a static site as the target. The strand is the unit
of publication — anything not in an exported strand stays private, and
selection is the consent act.

**Workflow:**

1. **Group in the timeline** (:8101): select beads → "Group into strand" →
   name it; use the strand's EDIT to set place and event link.
2. **Find the strand id:**

       python scripts/export_public.py list
       # bc424e19-…  2026-07-17  IoT London Meetup 156  [5 items]

3. **Export into the site repo** (several ids allowed; newest renders first):

       python scripts/export_public.py export <strand-id> [...] \
         --out ~/TPM/geekyoto/public/cultureblocs \
         --media-src ./data/media

   Target whatever folder your generator serves at the site root:
   `public/` (Astro/Next/plain Vercel), `static/` (Hugo), a passthrough
   dir (Eleventy). If the String runs elsewhere (e.g. Docker on a home
   server), run the export from any machine with `--spine http://<host>:8100`
   over Tailscale — but note `--media-src` must be a local path to the
   String's media directory, so either run the script on the host and copy
   the output folder over, or mount/sync `data/media`.
4. **Add the component** (once):

       cp web/cultureblocs-strands.js ~/TPM/geekyoto/public/cultureblocs/

   then in any template:

       <script type="module" src="/cultureblocs/cultureblocs-strands.js"></script>
       <cultureblocs-strands src="/cultureblocs/strands.json" limit="1"></cultureblocs-strands>

   `limit="1"` = newest strand only (homepage); omit for a full /beads
   page. Theme from site CSS via custom properties:

       cultureblocs-strands{ --cb-accent:#2B4BC7; --cb-font:Charter,serif; }

   (also: --cb-ink, --cb-faint, --cb-thread, --cb-card, --cb-edge)
5. **Preview** with the site's dev server and read `strands.json` yourself —
   it is small and human-readable, and what is in that file is exactly what
   the world gets.
6. **Ship:** commit `public/cultureblocs` and push; Vercel deploys.
   Worth wrapping step 3 in a `make beads STRAND=<id>` target.

**Privacy strip** (public web = strictest tier): geo coordinates and all
provenance (device ids, mintIds, apps) are removed; place names, notes,
tags, links, works and media survive. Media files are copied
content-addressed, so re-exports are idempotent and cache-friendly.

**Option 2 path:** the JSON keeps records in com.cultureblocs.* lexicon
shape, and the component neither knows nor cares that it is reading a
static file — when a PDS exists, a loader fetching the same shapes from
public XRPC feeds identical markup. Baked vs live becomes a per-page
choice, not a rewrite.

## Scrobble worker (Sonos -> Last.fm -> listen beads)

`workers/scrobbler.py` polls Last.fm recent tracks, clusters plays into
listening sessions (>30-min gap = new session), and mints one `listen`
bead per **closed** session with `provenance.app: "scrobbler"` — so the
timeline shows them on the dotted machine rail with a release button,
and they flow through normal curation. Idempotent: dedupe on the first
track's timestamp; re-runs are no-ops; open or window-truncated
sessions wait for the next run.

    LASTFM_USER=you LASTFM_API_KEY=xxx python workers/scrobbler.py
    # options: --spine --token --gap 30 --lookback 48 --dry-run
    # loop mode: --daemon --interval 900

Only the API key is needed (public read of your own history — un-hide
"recent listening" in Last.fm privacy if empty). Run hourly via cron,
or on macOS a LaunchAgent with StartInterval 3600, alongside
sonos-lastfm which feeds the account. `--from-json export.json` imports
a saved getRecentTracks payload (testing or bulk history import).
