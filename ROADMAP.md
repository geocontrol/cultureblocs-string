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

## 4 · CreativeID (design track)

Settled positions: the core work claim stays permanently tiny (title,
reference URL, freeform date; only createdAt immutable) — enough for
"this is mine / we did this." Industry, scenes, and forms not yet
invented add layers as records in their own namespaces that
*reference* the claim, never as fields on it. Role vocabularies are
industry layers. Money routing consumes the graph; it does not live
in it. Trust is computed from closed loops (A claims ↔ B attests) —
the mutual-mint primitive at professional scale — with strongRef
CID-pinning so silent edits visibly sever attestations.

- [ ] **Now, tiny**: `creatorDid` on `workRef`.
- [ ] **Phase 0 drafting** — `creative.work` and
  `creative.connection` lexicons per the above. Namespace lean:
  `com.cultureblocs.creative.*`, migration path open.
- [ ] **Auracles** (successor to the Creative Passport) — three-tier
  ask: stable resolvable per-person ID → expose as `did:web` →
  bidirectional `alsoKnownAs` linkage for computed verification. A
  join layer honouring their users' investment, not a competitor.
- [ ] **Other ID systems** — `externalIds` as `{scheme, id}`: ISNI,
  IPI, ORCID, Wikidata alongside Auracles as peers.
- [ ] **First real loop** — self-claim a work; the org attests it.
  Demonstrate before asking anyone to believe.

## 5 · Venues & event data (deferred; re-entry triggers defined)

Deliberately parked. Wake when **(a)** the
[Lexicon Community](https://github.com/lexicon-community) calendar
work is stable enough to adopt (interoperate, don't fork), or
**(b)** a real venue asks. Until then the meetup *is* the venue
pilot. And per the framing: enhancement, not a calendar replacement.

- [ ] `exhibition` and `work.listing` lexicons (listings double as
  the AR recognition-pack channel).
- [ ] Venue onboarding tooling.
- [ ] Tier 1 engagement signals (consented, anonymised audience
  insight) once ATProto's permissioned-data layer matures.
- [ ] **The AppView** — a Jetstream listener on `com.cultureblocs.*`
  (~50 lines): "my strands" becomes "strands across the network."
  Meaningful the moment a second person publishes; may deserve
  promotion out of this section.

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
