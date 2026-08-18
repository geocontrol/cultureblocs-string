# Rounds

Rounds is a local-first fair planner and note-taker for walking an art
fair. It's a zero-dependency PWA (vanilla ES modules, no build step)
served at **:8107**: browse the exhibitor list, star stands into a
day-by-day plan, capture short notes on what you saw, and — separately,
and only when you choose — say publicly that you attended.

## Seeded fair data is Tier 0 and never leaves this machine

`scripts/seed_frieze.py` imports a fair's exhibitor list from Artworld
into the String as `com.cultureblocs.venue.lineup` records plus one
`community.lexicon.calendar.event` for the run. For
`frieze-london-2026` that's **177 exhibitors** — 121 Galleries, 35
Focus, 9 The Code Universe, 7 Artist-to-Artist, 5 Editions. No stand
numbers exist in the source data, so `venue` stays absent on every
lineup. Ten gallery descriptions exceed the `note` field's
2000-grapheme limit; rather than drop those ten galleries outright,
their descriptions are truncated to the limit with a trailing ellipsis.

Why local only: saying "this named gallery is exhibiting at this named
fair" is a public claim about a third party who hasn't made it. It
happens to be true — that's exactly why publishing it is tempting —
but true is not the same as attested, and no gallery has said it. So
the stands and the fair event that seeds them are Tier 0: written with
`sourceApp: seed-frieze`, tagged `seed:artworld`, held on the local
String, none carrying a `published_uri`, and refused by the publishing
path. The seed script itself refuses to run against any `--string`
host that isn't demonstrably local (localhost/loopback, or a tailnet
`*.ts.net` address) — a mistyped flag must not be able to push this
data somewhere public.

## Seeding

    python scripts/seed_frieze.py --start 2026-01-01 --end 2026-01-03

The current seed carries **deliberately absurd placeholder dates**
(2026-01-01 to 2026-01-03) because Frieze London 2026's real dates
aren't known yet. Re-run the seed with the real `--start`/`--end` once
they're announced: it's idempotent, matching on `dedupeKey`, so this
corrects the fair event and every stand in place rather than creating
duplicates. `--fair` defaults to `frieze-london-2026`; `--string`
defaults to `http://localhost:8100`.

## Running

    docker compose up -d string rounds

Rounds is served at `http://localhost:8107`; it talks to the String at
`http://localhost:8100` by default. Open Rounds, pick the Stands
screen — it fills once the String is reachable, and stays filled from
the local cache when it isn't.

## Offline-first

Rounds is built for a hall with no usable connectivity. A note
captured on a stand (`✎`) is queued on the device (IndexedDB) the
instant it's saved, independent of whether the String is reachable
right then. The footer's queue-status count shows how many notes are
still held; Rounds retries the flush automatically (on boot, after
every save, and on `online`), and a note is only cleared locally once
the String durably accepts it (`created` or `duplicate`). Nothing is
lost by walking out of signal — it's held, not dropped — and flushing
the same queue twice creates no duplicate beads.

## Saying you're going

The Fair screen has an "I'm going" control. Pressing it writes your
own `community.lexicon.calendar.event` record — not a claim about any
gallery, just that a public occasion exists and that you're attending
it, which is yours to say. Unlike a note, this write goes straight to
the String rather than through the offline queue: if the String isn't
reachable the button says so, and you press "I'm going" again once it
is. Pressing it twice for a day already saved creates nothing new
(`dedupeKey` covers that too).

That event record is saved locally, same as everything else in
Rounds, until you publish it — and Timeline is **not** how you do
that. Timeline's only publish control operates on strands
(`strand-publish`); it has no publish affordance for a standalone
record. The one route someone would actually find there — select the
event, group it into a strand, publish the strand — *looks* like it
works and doesn't: the strand publisher only carries beads and
annotations into the strand (`BEAD_TYPES`), so a calendar event inside
a strand is silently dropped, and the UI still shows the strand as
published. You'd walk away believing your attendance is on the
network when it never left the String.

The route that actually publishes a standalone record like this one
is the CLI, using a held identity:

    python scripts/promote.py publish <record-id> --identity <name>

Find `<record-id>` with `GET /records?type=community.lexicon.calendar.event`
(it's the `id` on the row with `sourceApp: rounds`). This calls
`POST /publish/{id}` directly rather than going through strand
assembly, which is why it works for an event where the strand route
doesn't. `--identity` names a publishing identity already held by the
String (`PUT /identities/{name}`, or set up from Timeline).

**The RSVP is not written here.** A `community.lexicon.calendar.rsvp`
(`going`) points at its event with a `strongRef` — both an `at://` URI
and a CID, neither of which exists until the event has actually been
published. Writing an RSVP against an unpublished event would mean
inventing a CID: a lie in exactly the field this project relies on to
make references tamper-evident. So the sequence is: save the event
here, publish it with the command above, then add the RSVP once the
published record — and its real CID — exists.

## Testing

    node --test 'rounds/test/*.test.mjs'
