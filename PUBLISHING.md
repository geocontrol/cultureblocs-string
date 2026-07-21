# Publishing the lexicons: giving cultureblocs.com an ATProto identity

The goal: make `com.cultureblocs.bead` (and siblings) *formally resolvable* —
any ATProto tooling, anywhere, can go NSID → DNS → DID → schema record and
fetch the exact JSON this repo carries. Four steps, ~half a day including
DNS propagation. No self-hosted PDS required; a hosted account plus DNS is
the whole mechanism, and account migration keeps the sovereignty option open.

## 1 · Create the account

Create a Bluesky account for the project (e.g. `cultureblocs.bsky.social`).
This account is the *organisation*, not you personally — it will hold the
schema records, and later publish venue/meetup records.

## 2 · Claim the handle `cultureblocs.com`

In the Bluesky app: Settings → Account → Handle → "I have my own domain" →
DNS verification. It shows the account DID (`did:plc:…`). Add at your DNS
provider (Vercel DNS if the domain lives there):

    TXT  _atproto.cultureblocs.com   "did=did:plc:XXXXXXXXXXXX"

Verify in the app once DNS propagates. The account's handle is now the
domain itself — the website and the identity are one thing.

## 3 · The lexicon authority record

One more TXT record tells resolvers which DID speaks for the
`com.cultureblocs.*` namespace (same DID as step 2):

    TXT  _lexicon.cultureblocs.com   "did=did:plc:XXXXXXXXXXXX"

This is the line that makes cultureblocs.com the *schema authority* in the
protocol sense, not just the marketing sense.

## 4 · Publish the schema records

Make an **app password** (Settings → Privacy & Security → App Passwords),
then from this repo:

    python scripts/publish_lexicons.py --dry-run     # see what will happen
    BSKY_HANDLE=cultureblocs.com \
    BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx \
      python scripts/publish_lexicons.py

Each lexicon lands as a `com.atproto.lexicon.schema` record whose rkey is
its NSID. Re-running overwrites in place — editing a lexicon and re-running
IS the update mechanism (version-note breaking changes in the lexicon's
description; additive changes like new knownValues are safe by design).

## Verify

    python scripts/publish_lexicons.py --verify

Checks the `_lexicon` DNS record resolves to a DID and fetches every schema
record back from the PDS, unauthenticated — the same path any stranger's
tooling takes. When it prints all-ok:

- update the site: the "Status: draft … formal publication to follow" line
  in cultureblocs-site's build.py hero becomes "published and resolvable",
  rerun build.py, commit;
- the account can also post — the meetup announcement from
  @cultureblocs.com is a nice first skeet.

## Security notes

The app password grants write access to the account: keep it out of the
repo (env vars only — .gitignore already excludes .env), and revoke it
from settings when publication sessions are done. The DNS records are
public by design.
