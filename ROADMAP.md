# Roadmap

The shape of where CultureBlocs is going, by workstream. Status honest,
dependencies named. Building in public: if something here interests you,
say so — the meetup is the place, or open an issue.

*Last updated: July 2026. Done so far, for context: the String (record
store, timeline, Studio), the totem pipeline, the scrobbler, the
`com.cultureblocs.*` lexicons published as a resolvable ATProto schema
authority, strand publishing under held identities, and two sites
rendering strands live from the Atmosphere.*

---

## 1 · The String (core, near-term)

- [ ] **Media blobs in the promoter** — evolve the bead lexicon so
  `media` can carry ATProto blob refs; upload photos at publish time.
  Until then the static export is the photo-capable path. *The known
  gap; high visible payoff.*
- [ ] **Enrichment worker** — consume `GET /changes`, cluster each
  day's beads by time/place gaps into *draft* strands to accept or
  discard. Hand-made strands are the calibration set. *Independent.*
- [ ] **One-click publish for a lone bead** — auto-titled single-bead
  strand from the timeline; lowers ceremony without eroding
  selection-as-consent. *Small.*
- [ ] **Identities UI** — manage held accounts from the timeline
  instead of curl. *Small.*
- [ ] **Encounter confirmation** — matching mintIds across two
  people's Strings become confirmed edges, mapped to real DIDs at
  confirmation time. The social layer. *Gated on totem mintId (§2).*
- [ ] **Housekeeping** — backup cron (`sqlite3 .backup` + media),
  timestamped worker logs, embed component served from one canonical
  URL (copies currently vendored per site), Last.fm archive back-fill
  (2003–2011 history via `scrobbler.py --from-json`).
- [ ] **Timeline growth** — tag/source filters, multi-day and month
  views. Driven by daily-use friction.
- [ ] **Always-on host** — String + workers + sonos-lastfm to a home
  server; retires the sleeping-laptop failure class.

## 2 · The Totem (firmware)

- [ ] **mintId** — 128-bit, derived as SHA-256 of the sorted pair of
  exchange nonces (order-independent, unforgeable). The keystone:
  collision-free dedupe, the encounter join key, future pairing seed.
  String support already live and waiting.
- [ ] **bootEpoch** — per-bead power-session stamp + `EPOCH` in the
  dump anchor; wrong-time beads become honestly-flagged beads.
- [ ] **deviceId** rename (not "DID") and widen to 128-bit.
- [ ] NVS-robust counter (optional, on top of epoch).
- [ ] **Meetup readiness** — units charged/cleared, a "meetup" mask,
  per the runbook. *Deadline: 19 Aug.*

## 3 · The Meetup (the deadline that exercises everything)

- [x] Announcement strand published by `@cultureblocs.com`; meetup
  page renders it live.
- [ ] **19 Aug execution** — totems on the night; next-day telling;
  two strands (org + personal); a live publish as the demo; consent
  said out loud (published encounters naming people need the person's
  actual yes).
- [ ] **CreativeID question to the room** — "would you use a minimal
  work claim? what's missing from title-URL-date?" Bring the
  question, not the answer.
- [ ] **Repeatability** — the runbook becomes the standing pattern;
  every meetup feeds the site automatically.

## 4 · CreativeID (design track)

Settled positions from the thinking so far: the core work claim stays
permanently tiny (title, reference URL, freeform date; only createdAt
immutable) — enough for "this is mine, I did this / we did this."
Industry, scenes, and forms not yet invented add their own layers as
records in their own namespaces that *reference* the claim — never as
fields on it. Role vocabularies are industry layers, not core schema.
Money routing consumes the graph; it does not live in it. Trust is
computed from closed loops (A claims ↔ B attests), the mutual-mint
primitive at professional scale, with strongRef CID-pinning so silent
edits visibly sever attestations.

- [ ] **Now, tiny**: `creatorDid` on `workRef` — the one field that
  lets beads and AR annotations reach a creative identity.
- [ ] **Phase 0 drafting** — `creative.work` and `creative.connection`
  lexicons per the positions above. Namespace lean:
  `com.cultureblocs.creative.*`, migration path kept open.
- [ ] **Auracles** (successor to the Creative Passport) — the
  three-tier ask: stable resolvable per-person ID → expose as
  `did:web` → bidirectional `alsoKnownAs` linkage for computed
  verification. Framed as a join layer that honours their users'
  investment, not a competitor.
- [ ] **Other ID systems** — `externalIds` as `{scheme, id}` pairs:
  ISNI, IPI, ORCID, Wikidata alongside Auracles as peers.
- [ ] **First real loop** — self-claim a work; the org attests it.
  Demonstrate before asking anyone to believe.

## 5 · Venues & event data (deferred; re-entry triggers defined)

Deliberately parked. Wake when **(a)** the
[Lexicon Community](https://github.com/lexicon-community) calendar
work is stable enough to adopt (interoperate, don't fork), or
**(b)** a real venue asks. Until then the meetup *is* the venue
pilot: an organisation publishing event-shaped strands that
attendees tie beads to.

- [ ] `exhibition` and `work.listing` lexicons (listings double as
  the AR recognition-pack distribution channel).
- [ ] Venue onboarding tooling.
- [ ] Tier 1 engagement signals (consented, anonymised audience
  insight) once ATProto's permissioned-data layer matures.
- [ ] **The AppView** — a Jetstream listener on `com.cultureblocs.*`
  (~50 lines): "my strands" becomes "strands across the network."
  Meaningful the moment a second person publishes; may deserve
  promotion out of this section.

## 6 · AR (bottom of the list, by design)

Parked pending a rethink — the cultural backlash is against always-on
wearable cameras, and rightly. The reframe when this returns:
**phone-first, lens-as-gesture** — pointing your phone at a painting
is a deliberate, visible, momentary act, philosophically a totem
press. And *matching without scanning*: venue-published listing packs
let recognition run on-device against known works, no images leaving
the phone — a privacy showcase rather than a surveillance-adjacent
feature. The `annotation` lexicon and the Swift capture-queue port
wait ready for that version.

---

**The suggested thread through it all:** media blobs → meetup
execution → mintId & encounters as firmware lands → CreativeID
Phase 0 with the meetup's answers in hand → the AppView when
publisher #2 appears.