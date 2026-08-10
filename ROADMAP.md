# Roadmap

The shape of where CultureBlocs is going, by workstream. Status honest,
dependencies named. Building in public: if something here interests you,
say so — the meetup is the place, or open an issue.

*Last updated: July 2026. Done so far, for context: the String (record
store, timeline, Studio), the totem pipeline, the scrobbler, the
`com.cultureblocs.*` lexicons published as a resolvable ATProto schema
authority, strand publishing under held identities, and two sites
rendering strands live from the Atmosphere.*

## Framing: the Art Life

CultureBlocs is for living what David Lynch called the Art Life — with
"art" and "culture" read broadly. A gallery afternoon, an album on the
stereo, a book finished at breakfast, a film, a meetup, an encounter:
the beads are whatever a life's culture is made of. Some of these tools
could capture activity well beyond the cultural; we are not building
for that, and may never — the schemas are open precisely so someone
else can, if that's a direction worth going.

Three scope separations, deliberately held:

- **Diary tools ≠ publishing tools.** Keeping your art-string diary
  (totem, timeline, telling) is one thing; publishing data *about*
  your art (CreativeID) or a venue publishing its exhibitions is
  another. Connected by shared schemas and refs — never conflated
  into one app.
- **Proposals ≠ facts.** Machines (scrobbler, witness workers) may
  propose beads; only a person keeps them. The mint fact is sacred;
  the machine rail is dotted for a reason.
- **We are not replacing calendars.** Event data, when it comes,
  enhances in interesting places — beads tie to listings, strands
  remember evenings. Your calendar keeps its job.

---

## 1 · The String (core, near-term)

- [x] **Media blobs in the promoter** — beads' local photos upload as
  ATProto blobs (`photos` field) at publish time; the embed component
  renders them live via `getBlob`. Context links to Instagram/FB/
  Flickr etc. ride the existing `links[]` field — the timeline editor
  now takes many links, one per line.
- [ ] **Enrichment worker** — consume `GET /changes`, cluster each
  day's beads by time/place gaps into *draft* strands to accept or
  discard. Hand-made strands are the calibration set. *Independent.*
- [ ] **One-click publish for a lone bead** — auto-titled single-bead
  strand from the timeline. *Small.*
- [x] **Identities UI** — held accounts managed from the timeline
  (identities button in the header).
- [ ] **Encounter confirmation** — matching mintIds across two
  people's Strings become confirmed edges, mapped to real DIDs at
  confirmation time. The social layer. *Gated on totem mintId (§2).*
- [ ] **Housekeeping** — backup cron, timestamped worker logs, embed
  component served from one canonical URL, Last.fm archive back-fill
  (2003–2011 history via `scrobbler.py --from-json`).
- [ ] **Timeline growth** — tag/source filters, multi-day and month
  views. Driven by daily-use friction.
- [ ] **Always-on host** — spec written: [HOST-SPEC.md](HOST-SPEC.md)
  (Raspberry Pi as a DataBrick — a physical object in place holding
  the household's cultural memory). Build when parts arrive; retires
  the sleeping-laptop failure class and unlocks §2 posting from
  anywhere.

## 2 · Capture surfaces (the totem is one of a family)

Different hands, one gesture: choose a mask, mint a moment. Every
surface writes the same records through the same offline-queue
pattern; none of them is a feed.

### The Totem (hardware, firmware conversation's queue)
- [ ] **mintId** — 128-bit, SHA-256 of the sorted nonce pair.
  Keystone: dedupe, the encounter join key, pairing seed. String
  support already live.
- [ ] **bootEpoch** — honest power-loss handling.
- [ ] **deviceId** rename + widen; NVS counter optional on top.
- [ ] **Meetup readiness** — units charged/cleared, a "meetup" mask.
  *Deadline: 19 Aug.*

### The pocket totem (phone app) — *highest of the new surfaces*
- [x] **PWA built** (`pocket/`, served on :8103): one screen — mask
  strip, the mint button as a live LED dot-matrix (mask initial in
  dots, bloom on press), optional one-line note, offline queue in
  localStorage flushing to the String. Installable; serve over HTTPS
  (e.g. `tailscale serve`) for full PWA install + offline shell.
- [ ] **Design language**: the glyph/dot-matrix direction (à la
  Nothing) — peripheral, glanceable, low-attention signalling, which
  is the totem's soul on glass. Monochrome matrix bloom on mint,
  masks as glyph patterns, particle cloud, no chrome.
- [ ] **A button, not a feed** — deliberately no timeline on the
  phone; the telling stays a desk ritual.
- [x] **ATProto OAuth** — sign in with your own handle; beads publish to
  your own repository with no String to run. PKCE + pushed authorisation
  + DPoP, with the private key non-extractable in IndexedDB. Deployed at
  cultureblocs.com/pocket/ because the client id must be a stable URL.
- [x] **The round trip** — `scripts/import_repo.py` brings
  born-public beads home to be told, and re-publishing updates the same
  public record instead of orphaning it.
- [ ] **Local-only notes** for someone with no account at all: keep it on
  this phone, claim it later. The missing rung between "scan" and
  "create a decentralised identity" — see the QR journey diagram.
- [ ] Native (iOS App Intents / Android) later, when voice (§below)
  or widgets demand it.

### Voice — the Resident lineage (inanimate.tech)
- [ ] **Today-hack**: an iOS Shortcut — "Hey Siri, mint a cinema
  bead" → dictated note → POST /records over Tailscale. Zero new
  code; do before any architecture.
- [ ] **Skill** (done for the desk): the Claude Code skill already
  mints/edits/publishes conversationally — the same idea, terminal-side.
- [ ] Deeper: assistant-mediated minting per the voice → model →
  real-world pattern Resident was designed for. Design when native
  app exists.

### Witness workers (machines that propose)
- [x] **Scrobbler** — Sonos → Last.fm → listen-session beads on the
  dotted rail. The pattern's first instance.
- [ ] **Booking mail** — cinema/theatre confirmations become booking
  beads: a forwarding alias or IMAP poll; many confirmations embed
  schema.org JSON-LD (`EventReservation`), so parsing can be robust.
  Design note: a booking bead is *future tense* — the ticket stub
  before the show, later the anchor the visit-bead ties to; likely a
  new `booking` kind. Proposals on the dotted rail, as ever.

### Browser extension
- [ ] Current page + selection → bead (link + note) in two clicks.
  The del.icio.us muscle memory; also where the old trackback thread
  re-enters — noting the web into the string.

## 3 · The Meetup (the deadline that exercises everything)

- [x] Announcement strand published by `@cultureblocs.com`; meetup
  page renders it live.
- [ ] **19 Aug execution** — totems on the night; next-day telling;
  two strands (org + personal); a live publish as the demo; consent
  said out loud (published encounters naming people need the
  person's actual yes).
- [ ] **CreativeID question to the room** — "would you use a minimal
  work claim? what's missing from title-URL-date?"
- [ ] **Repeatability** — the runbook becomes the standing pattern;
  every meetup feeds the site automatically.

## 4 · CreativeID (lexicons landed; integrations next)

**The model is self-attestation.** The primary act is tagging a piece of
work as yours; the record lives in your own repository and proves one
narrow, honest thing — that this claim was made on this date by the
holder of that repository. Unattested is the normal state, not a
deficient one. Where two parties independently point at each other, a
reader computes a verified relationship from the closed loop: the
mutual-mint primitive at professional scale, with CID pinning so silent
edits visibly break the loop.

**Layers reference; they never grow the core.** Industry metadata,
scene vocabularies and licensing terms live in other namespaces
pointing at a work's URI. Role vocabularies are externalised. Money
routing consumes the graph and does not live in it. And **registration
with ISNI/ISWC/ISRC and friends is somebody else's business** — a
bridge service could lodge self-asserted works with those bodies (the
shape exists already), and `externalIds` is the hook it writes back
into. CultureBlocs is enough of a tag to facilitate that workflow, and
stops there.

- [x] **Lexicons drafted and live**: `creative.profile`,
  `creative.work`, `creative.connection`, plus `creatorDid` on
  `workRef` and a shared `externalId` type. CLI: `scripts/creative.py`.
  Design notes: [CREATIVE-AND-VENUE.md](CREATIVE-AND-VENUE.md).
- [ ] **Auracles** (successor to the Creative Passport) — conversation
  under way. The join is `externalIds` scheme `auracle`, plus a
  reciprocal link if they expose a DID, so verification computes from a
  closed loop rather than being granted by either side. They already
  hold other identifiers per profile, so a DID field sits inside their
  existing model.
- [ ] **Other schemes** as peers: ISNI, IPI, ORCID, MusicBrainz,
  Wikidata, and the newer consent registries (RSL Media, Spawning) —
  point at a person's consent declaration rather than inventing a
  permissions vocabulary here.
- [ ] **Read CAWG's identity assertion spec** before extending
  `creative.connection`: same problems (binding claims to exact
  content, aggregating identity claims), more scrutiny.
- [ ] **First real loop** — self-claim a work; the org attests it.
  Demonstrate before asking anyone to believe.

### Possible joins (parking notes, not commitments)

- **LOT** (https://lot-systems.com/ — subscription distribution of
  digital + physical goods: wardrobes, self-care, home essentials).
  Has an API for retrieving data: https://lot-systems.com/api (page is
  client-rendered — read it properly when this gets picked up). Filed
  as a possible join: physical goods with data attached sits near the
  provenance/attestation thread and the brands-engaging-artists layer
  from the Art Life framing. Nothing designed yet.

## 5 · Venues & audience evidence (pilot active)

The distinguishing bet, and the part no other system has: **the venue
does not gather the data — the audience publishes it.** A venue puts out
an event; attendees' beads reference it if they choose; the venue counts
*public* references. It never collects, stores or processes anything
about a person — the difference between impossible and trivial for a
grassroots space with no data protection officer. What such venues need
evidence for is unglamorous: funding applications, licensing and
landlord arguments, a record that a night happened.

Stated boundary: **public references are countable; identities are not
the venue's to collect.**

**We do not own the event record.** Nights publish as
`community.lexicon.calendar.event` (Lexicon Community's shared type), so
a venue's programme reaches every calendar app that speaks it. An RSVP
is intent — *I'm going*; a bead is evidence — *I was here*. Two tenses
pointing at one record, published by different apps. That composition is
the whole opportunity, and it means our work starts where theirs stops.

- [x] **Adopted the community calendar**: events + RSVPs vendored and
  validated by the String; `venue.listing` deprecated (kept published so
  old records resolve); `com.cultureblocs.venue.lineup` added as the
  layer carrying who is on and works shown.
- [x] **`venue.profile`** keeps what an event does not carry — capacity
  and access notes, which funders and licensing ask for — and now points
  at `community.lexicon.location.*`.
- [x] **AppView indexes the shared types**, so it works for venues that
  have never heard of CultureBlocs. Verified against Edition Festival's
  2026 programme (14 events, published via VenueCMS).
- [x] **Doors** publishes both records from one form, and its QR codes
  point at the event.
- [ ] **Peckham pilot** — two grassroots venues; app hosted by us,
  identity and records theirs. Runbook in
  [CREATIVE-AND-VENUE.md](CREATIVE-AND-VENUE.md).
- [ ] **Talk to VenueCMS** (Scott Cazan) and Edition Festival (John
  Chantler): they own venue data entry and already publish to the
  network; we add the audience-memory layer that consumes it.
  Complementary, not competing.
- [ ] **Join the Lexicon Community conversation** — Discourse and the
  monthly call. If billing/lineup proves generally useful, propose it
  upstream rather than keeping our own layer forever.
- [ ] Tier 1 engagement signals (consented, anonymised) only if and when
  ATProto's permissioned-data layer makes them honest.

## 6 · AR (bottom of the list, by design)

Parked pending a rethink — the cultural backlash is against
always-on wearable cameras, and rightly. The reframe when this
returns: **phone-first, lens-as-gesture** — pointing a phone at a
painting is a deliberate, visible, momentary act, philosophically a
totem press. And *matching without scanning*: venue-published
listing packs let recognition run on-device against known works, no
images leaving the phone — a privacy showcase rather than a
surveillance-adjacent feature. The `annotation` lexicon and the
Swift capture-queue port wait ready for that version.

---

**The suggested thread through it all:** media blobs → meetup
execution → pocket-totem PWA (people to hand it to now exist) →
mintId & encounters as firmware lands → CreativeID Phase 0 with the
meetup's answers in hand → the AppView when publisher #2 appears.
