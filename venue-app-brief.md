# CultureBlocs for venues — project brief

*A separate app, a separate audience, a separate repo. Working title
options at the end.*

## Why it is not part of the String

The String is a diary. Its whole architecture exists to serve one
person's private record: local-first storage, a Tier 0 that never leaves
the machine, a telling ritual at the end of the day, and publishing as a
deliberate promotion of a few chosen moments.

**A venue has none of that.** Everything a venue makes — its profile,
its listings — is public from the moment it is written. There is no
private tier to protect, no beads to annotate, no strands to tell. Which
means the venue tool needs almost none of the String's machinery, and
putting it in the same interface would burden a bar manager with
concepts built for someone keeping a cultural diary.

The two apps share schemas and a network. They should share nothing
else.

## Who it is for

A person at a small venue, on a laptop behind the bar or a phone in the
office, twenty minutes before doors. Not technical. Not paid to do
admin. Already using a ticketing platform, Instagram, and a whiteboard.

The jobs, in their words:

- "Put Friday's gig up somewhere it counts."
- "Show me that people were here" — for funding applications, licensing
  hearings, landlord and council arguments, sponsorship conversations.
- "Give me something to put in the Arts Council form" — evidence with a
  date, a number and a source.
- "Don't make me sign up to another platform that owns my data."

## Non-goals (state these on the tin)

- **Not ticketing.** Dice, Eventbrite and the door take stay where they
  are; the listing links out.
- **Not audience CRM.** No attendee lists, no marketing database, no
  emails. Public references are countable; identities are not the
  venue's to collect.
- **Not a calendar.** It does not manage staff rotas or room bookings.
- **Not a website builder** — though it does produce one public page and
  an embeddable widget, because that is nearly free.
- **Not analytics theatre.** Early numbers are small and the app should
  say so rather than dress three references as a dashboard.

## Architecture: a thin client, not a second String

    ┌──────────────────────────┐
    │   Venue app (browser)    │  hosted once, used by many venues
    │  profile · listings ·    │
    │  the room · export       │
    └───────┬──────────┬───────┘
            │ write    │ read
            ▼          ▼
      venue's own    CultureBlocs
      ATProto repo    AppView (:8104)
      (their PDS)    counts + references

Consequences worth stating plainly:

- **No per-venue server.** "Running an instance for them" becomes
  hosting one small web app, not a container per venue.
- **No database of venues.** The app holds no venue records of its own;
  it reads and writes the venue's repository. If the app disappears, the
  venue's data is untouched and still resolvable.
- **Sovereignty is real, not rhetorical.** The account is theirs; ATProto
  account migration means they can move host and keep every published
  listing, URI and reference intact.
- **The AppView is read-only infrastructure.** The app never writes to
  it; it asks it questions.

### Auth

- **Pilot**: ATProto app password, stored server-side per session. Ugly
  but working, and the venue can revoke it from their account settings.
- **Proper**: ATProto OAuth, so the venue signs in with their own
  handle and grants scoped access without handing over a credential.
  This is the right end state and worth doing before any venue beyond
  the pilot.

## MVP surface (five screens)

1. **Sign in** — handle + app password (later OAuth). Explains in one
   sentence what the app will write to their repo.
2. **Venue profile** — name, address, capacity, accessibility notes,
   links. Published once at `rkey: self`; editing republishes in place.
3. **Listings** — a list of upcoming and past, with *Add* and *Edit*.
   The form is deliberately short: title, date and time, who's on
   (billing), a link out for tickets, an optional description. Cancel
   and postpone are status changes, not deletions.
4. **The room** — per listing: how many people publicly referenced it,
   how many distinct publishers, and the public notes they wrote. The
   evidence view. Honest empty state: "nobody has published about this
   yet — that's normal early on."
5. **Export** — the feature that earns the app its keep: a printable
   or CSV summary for a funding application. Listings in a date range,
   reference counts, quoted public notes with their sources, and a
   plain-English footer explaining the methodology (public,
   self-published, voluntary — not a headcount).

## The missing bridge: getting audiences to actually reference a listing

Nobody will hand-type an `at://` URI at a gig. Two mechanics, both
small, and without them the audience half of this doesn't happen:

- **A QR code per listing**, printed by the app for the wall, the door
  or the poster. It opens the Pocket Totem with the listing pre-loaded,
  so minting a bead about tonight is one tap and the reference is
  attached automatically. (Requires a small Pocket Totem change: accept
  `?ref=at://…` and attach it as the bead's `subject`.)
- **A short public listing page** with the same one-tap affordance, for
  people who find the gig online rather than in the room.

Design constraint: neither should require the attendee to have anything
set up in advance beyond the Pocket Totem, and neither should ask for
identity. Somebody with nothing installed sees a nice page about the
night and no nag.

## Public output

- **`/{venue-handle}`** — a public page: profile, upcoming listings,
  past nights with what people published. Their own URL to hand out.
- **An embed** — the same content as a web component for their existing
  website, exactly as `<cultureblocs-strands>` works for personal
  strands.

## Data and privacy stance (put it in the UI, not just the docs)

- The app writes only what the venue types, to the venue's own
  repository.
- It reads only records people chose to publish.
- It shows counts and public notes. It does not build profiles of
  attendees, and it cannot tell the venue who was in the room.
- Early numbers are small; the app should present them as *a public
  record of the night*, not as attendance figures.

## Pilot: two Peckham venues

What we provide: the hosted app, an ATProto account set up with their
domain as handle if they have one, the QR codes, and a walkthrough of
the first listing.

What they own: the account, the records, the right to leave with
everything.

What we ask: put up four to six listings over a couple of months, stick
the QR codes up, and tell us where the form annoys them.

What success looks like at this stage — deliberately modest: listings
get published without help after the first one, the QR gets used at
least once a night, and the export produces something a venue would
actually paste into a funding form. Reference counts in double figures
would be a bonus, not the test.

## Build sequence

1. Repo skeleton, auth, profile create/edit, listing create/edit/cancel
   — enough for a venue to publish. *The pilot can start here.*
2. The room view + AppView integration.
3. QR codes + Pocket Totem `?ref=` support. *This is what makes the
   audience side real.*
4. Public venue page and embed.
5. Export for funding applications.
6. OAuth, replacing app passwords.

## Open questions for the venues

- Do they have a domain to use as a handle, or should we host one?
- Where do listings currently originate — Dice, Instagram, a whiteboard?
  (Import may matter more than authoring.)
- What does their funding application actually ask for? The export
  should mirror those fields, not our idea of them.
- Who at the venue would use this — one person or several? (Multi-user
  changes auth sooner rather than later.)

## Naming

The family is String, beads, strands, totem, Studio. For the venue side,
words from the room itself:

- **Doors** — "doors at 7:30". Idiomatic, warm, about the moment an
  audience arrives.
- **Bill** — the lineup; also what gets posted outside.
- **Marquee** — the signage over the entrance.
- **Foyer** — the threshold between street and room.

*Doors* is the strongest: it is the venue's own word for the beginning
of a night, and "put it on Doors" sounds like something a promoter would
actually say.
