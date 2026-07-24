"""The String — a validated record bucket for cultureblocs Tier 0 data.
(Beads on a thread; in the lineage of the quipu. Formerly "the Spine".)

Interfaces:
  POST  /records          batch ingest, idempotent on dedupeKey
  GET   /records          query by ?day=YYYY-MM-DD&type=&sourceApp=
  GET   /records/{id}     single record
  PATCH /records/{id}     shallow-merge body fields (annotation edits)
  GET   /changes?since=N  append-only change feed with cursor (sync consumers)
  GET   /days             days with record counts (timeline nav)
  GET   /lexicons         the loaded schema set
  GET   /health

Auth: if SPINE_TOKEN is set, all endpoints require
      Authorization: Bearer <token>. Unset = open (home lab mode).
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import publisher
from .db import Store
from .lexicon import LexiconRegistry

DB_PATH = os.environ.get("STRING_DB") or os.environ.get("SPINE_DB", "/data/string.db")
LEXICON_DIR = Path(os.environ.get("STRING_LEXICONS") or os.environ.get("SPINE_LEXICONS", "/lexicons"))
TOKEN = os.environ.get("STRING_TOKEN") or os.environ.get("SPINE_TOKEN")

app = FastAPI(title="cultureblocs string", version="0.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)

store = Store(DB_PATH)
registry = LexiconRegistry()
registry.load_dir(LEXICON_DIR)


def auth(request: Request) -> None:
    if TOKEN is None:
        return
    header = request.headers.get("authorization", "")
    if header != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="invalid or missing token")


class RecordIn(BaseModel):
    dedupeKey: str = Field(..., min_length=1, max_length=200)
    type: str
    sourceApp: str = Field(..., max_length=100)
    createdAt: str
    body: dict


class BatchIn(BaseModel):
    records: list[RecordIn] = Field(..., max_length=500)


@app.get("/health")
def health():
    return {"ok": True, "lexicons": registry.record_types()}


@app.get("/lexicons", dependencies=[Depends(auth)])
def lexicons():
    return registry.docs


@app.post("/records", dependencies=[Depends(auth)])
def ingest(batch: BatchIn):
    results = []
    for rec in batch.records:
        if rec.type not in registry.docs:
            results.append({"dedupeKey": rec.dedupeKey, "status": "invalid",
                            "problems": [f"unknown record type: {rec.type}"]})
            continue
        problems = registry.validate_record(rec.type, rec.body)
        if problems:
            results.append({"dedupeKey": rec.dedupeKey, "status": "invalid",
                            "problems": problems})
            continue
        rid, status = store.upsert(
            rec.dedupeKey, rec.type, rec.sourceApp, rec.createdAt, rec.body)
        results.append({"dedupeKey": rec.dedupeKey, "status": status, "id": rid})
    return {"results": results}


@app.get("/records", dependencies=[Depends(auth)])
def query(day: str | None = None, type: str | None = None,
          sourceApp: str | None = None, limit: int = 500):
    return {"records": store.query(day=day, rtype=type,
                                   source_app=sourceApp, limit=min(limit, 2000))}


@app.get("/records/{rid}", dependencies=[Depends(auth)])
def get_one(rid: str):
    rec = store.get(rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")
    return rec


class PatchIn(BaseModel):
    fields: dict


@app.patch("/records/{rid}", dependencies=[Depends(auth)])
def patch(rid: str, body: PatchIn):
    current = store.get(rid)
    if current is None:
        raise HTTPException(status_code=404, detail="not found")
    merged = {**current["body"], **body.fields}
    problems = registry.validate_record(current["type"], merged)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    return store.patch(rid, body.fields)


@app.get("/changes", dependencies=[Depends(auth)])
def changes(since: int = 0, limit: int = 500):
    items = store.changes_since(since, min(limit, 2000))
    cursor = items[-1]["seq"] if items else since
    return {"changes": items, "cursor": cursor}


class IdentityIn(BaseModel):
    handle: str
    appPassword: str
    pds: str = "https://bsky.social"


@app.get("/identities", dependencies=[Depends(auth)])
def list_identities():
    """Names, handles, PDS — never the app passwords."""
    return {"identities": store.identities()}


@app.put("/identities/{name}", dependencies=[Depends(auth)])
def put_identity(name: str, body: IdentityIn):
    store.identity_put(name, body.handle, body.appPassword, body.pds)
    return {"identities": store.identities()}


@app.delete("/identities/{name}", dependencies=[Depends(auth)])
def delete_identity(name: str):
    if not store.identity_delete(name):
        raise HTTPException(status_code=404, detail="not found")
    return {"identities": store.identities()}


class PublishIn(BaseModel):
    identity: str


@app.post("/publish/{strand_id}", dependencies=[Depends(auth)])
def publish(strand_id: str, body: PublishIn):
    ident = store.identity_get(body.identity)
    if ident is None:
        raise HTTPException(status_code=404, detail="unknown identity")
    try:
        return publisher.publish_strand(store, strand_id, ident, media_dir=MEDIA_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"publish failed: {exc}")


@app.post("/unpublish/{strand_id}", dependencies=[Depends(auth)])
def unpublish(strand_id: str, body: PublishIn):
    ident = store.identity_get(body.identity)
    if ident is None:
        raise HTTPException(status_code=404, detail="unknown identity")
    try:
        return publisher.unpublish_strand(store, strand_id, ident)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"unpublish failed: {exc}")


class PublishedIn(BaseModel):
    uri: str
    hash: str


@app.post("/records/{rid}/published", dependencies=[Depends(auth)])
def set_published(rid: str, body: PublishedIn):
    if not store.set_published(rid, body.uri, body.hash):
        raise HTTPException(status_code=404, detail="not found")
    return store.get(rid)


@app.delete("/records/{rid}/published", dependencies=[Depends(auth)])
def clear_published(rid: str):
    if not store.set_published(rid, None, None):
        raise HTTPException(status_code=404, detail="not found")
    return store.get(rid)


@app.delete("/records/{rid}", dependencies=[Depends(auth)])
def delete(rid: str):
    """For curation records (strands). Beads are mint facts — the UI should
    not offer deletion for them, but the API does not police intent."""
    if not store.delete(rid):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": rid}


# -- media: content-addressed blob store ---------------------------------
MEDIA_DIR = Path(os.environ.get("STRING_MEDIA") or os.environ.get("SPINE_MEDIA", "/data/media"))
MEDIA_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
             "image/gif": ".gif", "image/heic": ".heic"}
MEDIA_NAME = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]{2,5}$")


@app.post("/media", dependencies=[Depends(auth)])
async def upload_media(request: Request):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty body")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="max 25MB")
    mime = request.headers.get("content-type", "application/octet-stream").split(";")[0]
    ext = MEDIA_EXT.get(mime, ".bin")
    name = hashlib.sha256(data).hexdigest() + ext
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    path = MEDIA_DIR / name
    if not path.exists():                     # content-addressed: idempotent
        path.write_bytes(data)
    return {"uri": f"/media/{name}", "mime": mime, "bytes": len(data)}


@app.get("/media/{name}")
def get_media(name: str):
    if not MEDIA_NAME.match(name):
        raise HTTPException(status_code=400, detail="bad media name")
    path = MEDIA_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path)


@app.get("/days", dependencies=[Depends(auth)])
def days():
    return {"days": store.days()}
