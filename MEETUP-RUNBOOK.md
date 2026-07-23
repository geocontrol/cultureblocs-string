# Meetup strand runbook

The meetup is the venue-layer pilot: CultureBlocs as organiser, attendee
and toolmaker at once. This runbook takes an evening from announcement
to a published strand on cultureblocs.com/meetup.html — which now
renders LIVE from the @cultureblocs.com repo, so publishing IS the
site update. No deploys anywhere in this document.

## Accounts

Two identities, deliberately:
- @cultureblocs.com  — the ORG speaks: announcement + the official
  meetup strand. Needs its own app password for promote.py.
- @geocontrol.bsky.social — YOU speak: your personal beads from the
  night publish (or not) under your identity as usual.
The same String holds both stories; the BSKY_HANDLE env var at publish
time decides who says what.

## Before the meetup (any time)

1. Mint the announcement bead:

       python scripts/mint.py --kind note \
         --note "Creative × Tech Summer Meetup — a friendly London \
evening for people across technology, data and culture. Newcomers welcome." \
         --tags meetup,announcement \
         --place "Dragon Hall, Covent Garden" \
         --link https://luma.com/4083pmnh --link-title "Register on Luma"

2. Timeline (:8101): group it into a strand — title it e.g.
   "Creative × Tech Summer Meetup — announced", add the Luma link at
   strand level too.
3. Publish as the org:

       python scripts/promote.py list
       BSKY_HANDLE=cultureblocs.com BSKY_APP_PASSWORD=... \
         python scripts/promote.py publish <strand-id>

4. Check cultureblocs.com/meetup.html — the strand is live under
   "Beads from the meetups". The announcement doubles as the org
   account's first visible cultural record.

## Event day

- Totems: charged, cleared (pull + gated clear in Studio), wardrobe
  set (a "meetup" mask?).
- Mint through the evening: arrivals, each share, moments worth
  keeping. Mutual mints for meetings — see consent below.
- Photos on your phone as usual; they attach in the timeline after.

## The telling (day after)

1. Studio: pull the totem, date/name the occasion, push to String.
2. Timeline: annotate, attach photos, fix kinds, group the evening
   into a strand — "Creative × Tech Summer Meetup, <date>" — with
   place and the Luma link.
3. Split the stories: beads for the OFFICIAL strand (welcome, shares,
   themes of the open conversation) vs YOUR strand (who you met, what
   you thought). Two strands from one night is correct, not duplication.
4. Publish each under its identity (BSKY_HANDLE per command, as above).
   The meetup page updates itself; your geekyoto homepage updates itself.

## Consent notes (worth saying out loud at the meetup)

- Encounter beads carry the mutual-mint pact: both pressed, both hold
  the record. Publishing an encounter NAMING someone stays off unless
  they're clearly happy — names in published notes are the one thing
  the privacy strip cannot strip for you.
- Photos of people in a published strand: ask.
- Everything else in a published strand is places, works, times and
  your own words — already covered by the strip (no geo, no devices,
  no mintIds leave the String).
- Nice meetup moment: show the room the strand publishing live, and
  the schema it validates against, resolvable from the domain. The
  system demonstrating itself is the talk.

## Known limitation

Photos don't publish to ATProto yet (media-blob lexicon evolution
pending) — the live embed shows text/links/works only. If the evening
is photo-heavy, additionally export the static bundle into the site
repo (export_public.py --out <site>/meetup) as a stopgap, or wait for
blob support.
