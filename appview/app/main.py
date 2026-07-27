"""The CultureBlocs AppView: a lens over public com.cultureblocs.* records.

It answers the questions a single repository cannot: who has published
what across the network, and — the one that matters for venues — how
many people have publicly referenced this listing.

What it is not: an audience-data platform. It indexes only records their
authors chose to publish, stores nothing about anyone who has not
published, and offers counts of public references rather than profiles
of people.
"""
from __future__ import annotations

import asyncio
import html
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .db import Index, uri_parts
from .ingest import backfill, consume, resolve_handle

DB_PATH = os.environ.get("APPVIEW_DB", "/data/appview.db")
SEED_ACTORS = [a.strip() for a in os.environ.get("APPVIEW_SEED", "").split(",") if a.strip()]
LIVE = os.environ.get("APPVIEW_LIVE", "1") != "0"

index = Index(DB_PATH)
app = FastAPI(title="cultureblocs appview", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    for actor in SEED_ACTORS:
        try:
            res = await asyncio.to_thread(backfill, index, actor)
            print(f"[backfill] {actor}: {res['total']} records", flush=True)
        except Exception as exc:
            print(f"[backfill] {actor} failed: {exc}", flush=True)
    if LIVE:
        asyncio.create_task(consume(index))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "live": LIVE, **index.stats()}


@app.get("/stats")
def stats() -> dict:
    return index.stats()


@app.post("/backfill")
async def do_backfill(actor: str = Query(..., description="handle or DID")) -> dict:
    try:
        return await asyncio.to_thread(backfill, index, actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/records")
def records(collection: str | None = None, did: str | None = None,
            limit: int = 50) -> dict:
    return {"records": index.records(collection, did, limit)}


@app.get("/record")
def record(uri: str) -> dict:
    rec = index.get(uri)
    if rec is None:
        raise HTTPException(status_code=404, detail="not indexed")
    return {**rec, **index.reference_count(uri)}


@app.get("/references")
def references(uri: str) -> dict:
    """Who has publicly pointed at this record — the audience join."""
    return {"uri": uri, **index.reference_count(uri),
            "referrers": index.referrers(uri)}


@app.get("/venue/{actor}")
def venue(actor: str) -> dict:
    """A venue's public record: profile, listings, and how many people
    publicly said they were there."""
    try:
        did = resolve_handle(actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    profile = index.records("com.cultureblocs.venue.profile", did, 1)
    listings = []
    for l in index.records("com.cultureblocs.venue.listing", did, 200):
        counts = index.reference_count(l["uri"])
        listings.append({**l, **counts})
    listings.sort(key=lambda x: (x["value"].get("start") or ""), reverse=True)
    return {"did": did,
            "profile": profile[0] if profile else None,
            "listings": listings,
            "totals": {"listings": len(listings),
                       "references": sum(l["references"] for l in listings),
                       "publishers": len({r["did"] for l in listings
                                          for r in index.referrers(l["uri"])})}}


@app.get("/creative/{actor}")
def creative(actor: str) -> dict:
    """A creative's public claims, and any attestations pointing at them.

    `verified` means both parties independently point at each other —
    computed from the graph, never granted by this service.
    """
    try:
        did = resolve_handle(actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    profile = index.records("com.cultureblocs.creative.profile", did, 1)
    works = []
    for w in index.records("com.cultureblocs.creative.work", did, 200):
        attestations = [r for r in index.referrers(w["uri"]) if r["did"] != did]
        works.append({**w, "attestations": [
            {"by": a["did"], "collection": a["collection"],
             "relationship": (a["value"] or {}).get("relationship"),
             "verified": index.reciprocal(did, a["did"])}
            for a in attestations]})
    claims = index.records("com.cultureblocs.creative.connection", did, 200)
    return {"did": did, "profile": profile[0] if profile else None,
            "works": works, "claims": claims}


EMPTY_PANEL = """
<div class="panel">
  <h3>Nothing indexed yet</h3>
  <p>Two ways in. <b>Live</b>: the firehose delivers records as people
  publish them — nothing appears until someone does. <b>Backfill</b>:
  records published before this AppView started are invisible until you
  ask for them, which is most of them on a first run.</p>
  <p>Index a repo now — try your own handle:</p>
  <form onsubmit="return bf(event)">
    <input id="actor" placeholder="handle or did:plc:…" autocomplete="off">
    <button type="submit">Backfill</button>
  </form>
  <div class="out" id="out"></div>
  <p class="out">To do this on every start, set <code>APPVIEW_SEED</code>
  in docker-compose.yml to a comma-separated list of handles.</p>
</div>
<script>
async function bf(e){
  e.preventDefault();
  const a = document.getElementById('actor').value.trim();
  const out = document.getElementById('out');
  if(!a) return false;
  out.textContent = 'indexing ' + a + '…';
  try{
    const r = await fetch('/backfill?actor=' + encodeURIComponent(a), {method:'POST'});
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail || r.status);
    out.textContent = d.total + ' records indexed — reloading…';
    setTimeout(()=>location.reload(), 700);
  }catch(err){ out.textContent = 'failed: ' + err.message; }
  return false;
}
</script>
"""

ROW = ("<tr><td class='m'>{when}</td><td>{title}</td>"
       "<td class='n'>{refs}</td><td class='n'>{people}</td></tr>")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    s = index.stats()
    coll_rows = "".join(
        f"<tr><td class='m'>{html.escape(k)}</td><td class='n'>{v}</td></tr>"
        for k, v in sorted(s["byCollection"].items()))
    listings = index.records("com.cultureblocs.venue.listing", None, 20)
    rows = ""
    for l in listings:
        c = index.reference_count(l["uri"])
        rows += ROW.format(
            when=html.escape((l["value"].get("start") or "")[:16].replace("T", " ")),
            title=html.escape(l["value"].get("title", "(untitled)")),
            refs=c["references"], people=c["publishers"])
    if not rows:
        rows = ("<tr><td colspan='4' class='m'>no listings indexed yet — "
                "a venue publishes these; see APPVIEW.md</td></tr>")
    if not coll_rows:
        coll_rows = "<tr><td class='m'>nothing indexed yet</td></tr>"
    empty_panel = "" if s["records"] else EMPTY_PANEL
    live = "following the firehose" if LIVE else "firehose disabled (APPVIEW_LIVE=0)"
    return f"""<!doctype html><meta charset=utf-8>
<title>CultureBlocs AppView</title>
<style>
 :root{{--plaster:#FAFAF9;--ink:#1B1D22;--faint:#8A8880;--edge:#E4E2DB;--accent:#2B4BC7}}
 body{{margin:0;background:var(--plaster);color:var(--ink);
   font:16px/1.6 Charter,Georgia,serif;padding:2.5rem 1.4rem}}
 main{{max-width:52rem;margin:0 auto}}
 h1{{font:600 1.6rem Futura,"Avenir Next",sans-serif;letter-spacing:.02em;margin:0 0 .3rem}}
 p.lede{{color:var(--faint);margin:0 0 2rem;max-width:34rem}}
 h2{{font:600 .8rem Futura,"Avenir Next",sans-serif;letter-spacing:.16em;
   text-transform:uppercase;margin:2.2rem 0 .8rem;padding-bottom:.4rem;
   border-bottom:1px solid var(--edge)}}
 table{{border-collapse:collapse;width:100%;font-size:.9rem}}
 td{{padding:.4rem .6rem .4rem 0;border-bottom:1px solid var(--edge)}}
 td.m{{font-family:ui-monospace,Menlo,monospace;font-size:.8rem;color:var(--faint)}}
 td.n{{text-align:right;font-variant-numeric:tabular-nums;width:6rem}}
 .big{{display:flex;gap:2.5rem;margin:1rem 0 0}}
 .big div span{{display:block;font:600 1.8rem Futura,sans-serif}}
 .big div small{{color:var(--faint);font:.7rem/1.4 Futura,sans-serif;
   letter-spacing:.14em;text-transform:uppercase}}
 code{{font-size:.85em}}
 .m2{{font-family:ui-monospace,Menlo,monospace;font-size:.8rem;color:var(--faint)}}
 .panel{{border:1px solid var(--edge);border-left:3px solid var(--accent);
   background:#fff;border-radius:8px;padding:1.1rem 1.3rem;margin:0 0 1.5rem}}
 .panel h3{{font:600 .78rem Futura,"Avenir Next",sans-serif;letter-spacing:.14em;
   text-transform:uppercase;margin:0 0 .5rem}}
 .panel p{{margin:.3rem 0;font-size:.92rem}}
 .panel form{{display:flex;gap:.5rem;margin-top:.9rem;flex-wrap:wrap}}
 .panel input{{flex:1;min-width:14rem;font:.9rem ui-monospace,Menlo,monospace;
   padding:.5rem .6rem;border:1px solid var(--edge);border-radius:4px}}
 .panel button{{font:600 .75rem Futura,sans-serif;letter-spacing:.12em;
   text-transform:uppercase;background:var(--accent);color:#fff;border:0;
   border-radius:4px;padding:.55rem 1rem;cursor:pointer}}
 .panel .out{{font-family:ui-monospace,Menlo,monospace;font-size:.8rem;
   color:var(--faint);margin-top:.6rem}}
</style>
<main>
<h1>CultureBlocs AppView</h1>
<p class="lede">A lens over public <code>com.cultureblocs.*</code> records.
It counts what people chose to publish — never anything about anyone who didn't.</p>
{empty_panel}
<div class="big">
  <div><span>{s['records']}</span><small>records</small></div>
  <div><span>{s['publishers']}</span><small>publishers</small></div>
  <div><span>{s['references']}</span><small>references</small></div>
</div>
<h2>Listings &amp; public references</h2>
<table><tr><td class="m">when</td><td class="m">listing</td>
<td class="n m">refs</td><td class="n m">people</td></tr>{rows}</table>
<h2>Indexed collections</h2>
<table>{coll_rows}</table>
<h2>Status</h2>
<p class="m2">{live}. Records arrive live as people publish; anything
published earlier needs a one-off backfill.</p>
<h2>API</h2>
<table>
<tr><td class="m">GET /venue/{{handle}}</td><td>profile, listings, reference counts</td></tr>
<tr><td class="m">GET /creative/{{handle}}</td><td>works, attestations, computed verification</td></tr>
<tr><td class="m">GET /references?uri=</td><td>who publicly pointed at a record</td></tr>
<tr><td class="m">GET /records?collection=&amp;did=</td><td>raw index</td></tr>
<tr><td class="m">POST /backfill?actor=</td><td>index an existing repo</td></tr>
</table>
</main>"""
