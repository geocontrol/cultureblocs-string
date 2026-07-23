---
name: cultureblocs-string
description: Work with a CultureBlocs String — a personal cultural-memory record store. Use when the user asks to mint a bead (record a cultural moment - a gig, film, book, exhibition, listening session), annotate or edit beads, group beads into strands, publish or unpublish a strand to ATProto/Bluesky, export strands for a static site, or check what's in their String. Triggers: "mint a bead", "add to my string", "publish my strand", "what's on my string today", "cultureblocs".
---

# CultureBlocs String

The String is a local record store (default http://localhost:8100) holding
lexicon-validated cultural memory records (com.cultureblocs.*). All commands
run from the cultureblocs-string repo root. If STRING_TOKEN is set, pass
--token or set the env var.

## Mint a bead (record a moment)
    python scripts/mint.py --note "TEXT" [--kind bloc|visit|dwell|encounter|read|listen|watch|screening|performance|note] [--tags a,b] [--place "NAME"] [--link URL --link-title "LABEL"] [--time ISO8601]
Kind guidance: read/listen/watch for at-home culture; visit for being out;
bloc when unsure. Never invent a --time; omit it for "now".

## Inspect
    curl -s "http://localhost:8100/records?day=YYYY-MM-DD" | jq
    curl -s "http://localhost:8100/days" | jq
Strands: GET /records?type=com.cultureblocs.strand

## Edit a bead
    curl -s -X PATCH http://localhost:8100/records/{id} -H 'content-type: application/json' -d '{"fields":{"note":"...","tags":["..."]}}'
Fields shallow-merge and re-validate. Never edit mint facts (createdAt,
provenance) — only the envelope (note, tags, subject, links, kind, media).

## Strands (grouping)
Create via POST /records with type com.cultureblocs.strand, body.items =
[{"uri":"spine://records/<bead-id>"}...]. The timeline UI (:8101) is the
usual way; only script it when asked.

## Publish / unpublish to the Atmosphere (ATProto)
List held identities first:
    curl -s http://localhost:8100/identities | jq
Then:
    python scripts/promote.py list
    python scripts/promote.py publish <strand-id> --identity <name>
    python scripts/promote.py unpublish <strand-id> --identity <name>
    python scripts/promote.py status        # drift since publish
IMPORTANT: publishing is public and immediate. Always confirm with the user
which identity to use and that they intend the strand public. Never add an
identity or publish without an explicit user request.

## Static export (geekyoto-style site embed)
    python scripts/export_public.py list
    python scripts/export_public.py export <strand-id> --out <site>/cultureblocs

## Safety rails
- Machine sources (scrobbler) mint proposals; a human keeps or releases them.
- Do not DELETE beads; DELETE is for strands (curation) only.
- Privacy strip on publish/export is automatic (geo, provenance, media out);
  what remains in a note is the user's own words — surface any names of
  people in notes before publishing and ask.
