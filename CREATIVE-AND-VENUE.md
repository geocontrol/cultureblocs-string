# CreativeID and venues: the design, and how to run a pilot

Two new families of lexicon, sharing the personal record's schemas and
its principles. Both are deliberately small; both are join layers rather
than registries.

    com.cultureblocs.creative.profile     who you are, self-asserted
    com.cultureblocs.creative.work        "I made this" / "we made this"
    com.cultureblocs.creative.connection  a directional claim about
                                          another party or record
    com.cultureblocs.venue.profile        a venue as a publishing party
    com.cultureblocs.venue.lineup         who is on, over a shared event

Events themselves are NOT ours. They are published as
`community.lexicon.calendar.event` — the shared event record stewarded by
[Lexicon Community](https://lexicon.community) — so a venue's programme
appears in every calendar app that speaks it (atmo.rsvp and others),
not only in CultureBlocs. `com.cultureblocs.venue.listing` is
**deprecated**; it remains published so existing records resolve.

## The positions these encode

**Self-attestation is the primary model.** The main reason to make a
work record is to tag a piece of work as yours. It lives in your own
repository, and that is the claim. What it proves is narrow and honest:
*this claim was made on this date by the holder of this repository* —
not authorship, not ownership. That narrowness is the feature; it is
exactly where NFT-style attestation over-claimed.

**Unattested is normal, not deficient.** There are no verification
badges or completeness scores. Where a second party independently points
back — a venue attesting a work it showed, a collaborator claiming the
same track — a reader computes a verified relationship from the closed
loop. Most records will never acquire one and are none the worse.
(ORCID's model, and structurally the same primitive as the totem's
mutual mint.)

**Layers reference; they never grow the core.** Industry metadata,
scene-specific vocabularies, licensing terms and commercial
registrations belong in other namespaces whose records point at a work's
URI. The work record stays permanently tiny so it can outlive every
layer built on it. Role vocabularies are externalised for the same
reason: film, music and theatre credit taxonomies are incompatible, and
baking any one of them in would repeat the mistake of modelling the
whole world on a single industry.

**Registration is somebody else's business.** ISNI, ISWC, ISRC and the
rest involve agencies, fees and legal entities. A bridge service could
take self-asserted works and lodge them with those bodies — that shape
already exists (ISNI registration agencies; Sound Credit assigns ISNIs
as a side-effect of profile creation). CultureBlocs does not build it.
`externalIds` is the hook such a bridge would write back into.

**Money is out of scope by design.** These records make the who-did-what
graph legible; payment routing consumes that graph from outside.

## Why we adopted the community event

We drafted our own listing type before discovering that the shared one was
real and in use — Edition Festival publishes its whole programme as
`community.lexicon.calendar.event` records via VenueCMS, and atmo.rsvp
reads them. Forking a live standard to gain three fields would have been
exactly the mistake this project keeps warning about, so:

- **The event is the shared record.** We write it, we read it, we do not
  own it. If a venue already publishes events some other way, we index
  those instead and add nothing.
- **Our layer references it.** `venue.lineup` carries who is on and works
  shown, pinned to the event by strongRef. Same discipline as the creative
  namespace: layers reference the core claim rather than growing it. If
  these fields prove generally useful they belong upstream, in the
  community lexicon, not here.
- **Two tenses, one record.** `community.lexicon.calendar.rsvp` says
  *I'm going*; a bead pointing at the same event says *I was here, and it
  was like this*. Nobody was doing the second one. That is the gap
  CultureBlocs fills, and it now fills it inside an existing network with
  existing publishers rather than one built from nothing.
- **Vendored, not copied.** The community schemas live under
  `lexicons/community/` so the String can validate records that use them;
  `scripts/vendor_community_lexicons.py` refreshes them from the
  authority. Our lexicon publisher deliberately skips them — claiming
  authority over someone else's namespace would be a lie.

## The audience↔work join

This is the part no other system has, and the reason the venue lexicons
exist at all.

A venue publishes a listing. People who came publish their own beads
referencing it — `subject` accepts a strongRef, so a bead points at the
listing's `at://` URI and pins its CID. The venue then **counts public
references**. It collects nothing, stores nothing about a person, and
processes no personal data: the evidence is published by the people who
chose to publish it.

For a grassroots space this is the difference between impossible and
trivial. What such venues need evidence for is unglamorous — funding
applications, licensing and landlord arguments, "this room matters"
cases — and the alternative is either a ticketing platform's dashboard
(someone else's data, gone when you switch) or nothing at all.

Be honest about the stage: early on this is a handful of beads a night.
That is a lovely public record of the evening and useless as analytics.
Sell the memory; let the counting become meaningful later.

**The boundary, stated plainly: public references are countable;
identities are not the venue's to collect.** If a venue wants to know
exactly who came, it is asking for personal data and has left this
model.

## Running a pilot for a venue

You host the String; the venue owns its identity and its records.

1. **Identity.** Create a Bluesky account for the venue and (optionally)
   claim its domain as the handle. Make an app password. Hold it in the
   String:

       curl -X PUT http://localhost:8100/identities/ivyhouse \
         -H 'content-type: application/json' \
         -d '{"handle":"ivyhouse.example","appPassword":"xxxx-xxxx-xxxx-xxxx"}'

2. **Profile, once.**

       python scripts/venue.py profile --name "The Ivy House" \
         --address "..." --capacity 150 \
         --accessibility "step-free entry, accessible toilet" \
         --link "https://…|website"
       python scripts/promote.py publish <record-id> --identity ivyhouse

   It publishes at rkey `self`, so re-publishing updates in place.

3. **An event per night**, in the shared type:

       python scripts/venue.py event --title "Friday Session" \
         --start 2026-08-14T20:00:00Z --end 2026-08-14T23:00:00Z \
         --address "40 Stuart Rd" --city London --venue-name "The Ivy House" \
         --link "https://dice.fm/…|tickets"
       python scripts/promote.py publish <record-id> --identity ivyhouse

   Optionally add the cultural layer (who is on):

       python scripts/venue.py lineup --event-uri at://…/community.lexicon.calendar.event/… \
         --event-cid bafy… --billing "The Bug Club|live"
       python scripts/promote.py publish <record-id> --identity ivyhouse

   Or use **Doors**, which writes both records from one form.

4. **The audience.** Anyone with a String (or the pocket totem) mints a
   bead with the listing's URI as its subject. The
   `<cultureblocs-strands>` component renders the venue's published
   records live on their own site — no deploys, no dashboard.

5. **What you owe them.** Say plainly that you run the instance, that
   their records are theirs, and that account portability means they can
   move the identity elsewhere without losing anything published.

## Open threads

- **Auracles**: the join is `externalIds` with scheme `auracle`, plus —
  if they expose a DID — a reciprocal link so verification computes from
  the closed loop rather than being granted by either platform.
- **Calendars**: `venue.listing` deliberately carries an `event`
  strongRef so it can point at a general-purpose event record (e.g. the
  Lexicon Community calendar work) instead of forking one.
- **Counting**: a Jetstream listener over `com.cultureblocs.*` turns
  scattered references into a count. ~50 lines, and the moment a second
  person publishes it becomes the interesting piece of infrastructure.
