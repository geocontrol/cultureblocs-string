# The AppView: making public references legible

A single repository can only answer questions about itself. The AppView
answers the ones that need the whole network — and in particular the one
the venue pilot depends on:

> How many people publicly said they were at this?

It is a **lens over public records**, not an audience-data platform. It
indexes only what people chose to publish to their own repositories,
holds nothing about anyone who has not published, and reports counts of
public references rather than profiles of people. Everything it knows,
anyone could have fetched themselves; the AppView just saves them the
walk.

    docker compose up -d --build appview      # :8104

## How data gets in

**Live**: a WebSocket to Jetstream, filtered server-side to the eight
`com.cultureblocs.*` collections. The filtering matters — the global
firehose carries millions of events an hour, and asking for our
collections means the rest never reaches us. In practice the process
sits idle at near-zero CPU and wakes when someone publishes.

**Backfill**: records published before the AppView existed would
otherwise be invisible, so any repo can be indexed on demand:

    curl -X POST "http://localhost:8104/backfill?actor=ivyhouse.example"

Set `APPVIEW_SEED` in compose to a comma-separated list of handles to
backfill at every startup. Deletes on the network remove records from
the index; the Jetstream cursor is persisted, so a restart resumes
rather than re-reads.

## The reference graph

Any `{"uri": "at://…"}` object anywhere inside a record is treated as a
reference. That is deliberately structural rather than field-by-field: a
bead's `subject`, a strand's `items`, a connection's `subject`, a
listing's `venue` and `event` all use the same strongRef shape — and so
will fields not yet invented. Where a CID is present it is stored, which
is what makes an attestation tamper-evident: if the target is rewritten,
the pinned CID no longer matches.

## Endpoints

| Endpoint | What it answers |
|---|---|
| `GET /` | dashboard: totals, listings with reference counts |
| `GET /venue/{handle-or-did}` | profile, listings, and public references per listing |
| `GET /creative/{handle-or-did}` | works, attestations pointing at them, computed verification |
| `GET /references?uri=` | who publicly pointed at this record |
| `GET /record?uri=` | one record plus its reference count |
| `GET /records?collection=&did=` | raw index |
| `POST /backfill?actor=` | index an existing repo |
| `GET /stats`, `GET /health` | totals |

`verified` on an attestation means **both parties independently point at
each other**. It is computed from the graph at read time, never granted
by this service and never stored as a flag — nobody approves anything,
and the loop either closes or it doesn't.

## What this is careful not to become

- **No identity resolution beyond DIDs.** It does not join references to
  names, emails or accounts elsewhere.
- **No inference about non-publishers.** Someone who attended and
  published nothing is, correctly, invisible.
- **Counts, not dossiers.** `/venue` returns how many people referenced
  a listing, not a list of who they are as people. The DIDs are public
  and appear in `/references`, because the records themselves are public
  — but nothing is compiled about them.
- **No ranking, no feed, no algorithm.** It answers questions; it does
  not decide what matters.

If a venue wants to know exactly who came, it is asking for personal
data and has left this model. See CREATIVE-AND-VENUE.md.
