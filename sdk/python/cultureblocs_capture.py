"""cultureblocs capture SDK (Python).

Offline-first: records are appended to a local JSONL queue immediately,
then flushed to the Spine when it is reachable. Safe to flush repeatedly —
the Spine dedupes on dedupeKey, and this queue only removes entries the
Spine has confirmed (created or duplicate).

Usage:
    q = CaptureQueue("~/.cultureblocs/queue.jsonl", app="culturebloc-bridge")
    q.capture("com.cultureblocs.bead", dedupe_key=mint_id,
              created_at="2026-07-08T14:03:00Z", body={...})
    q.flush("http://spine:8100", token=None)   # whenever online
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


class CaptureQueue:
    def __init__(self, path: str, app: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.app = app

    def capture(self, rtype: str, dedupe_key: str, created_at: str, body: dict) -> None:
        entry = {"dedupeKey": dedupe_key, "type": rtype,
                 "sourceApp": self.app, "createdAt": created_at, "body": body}
        with self.path.open("a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def pending(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def flush(self, base_url: str, token: str | None = None,
              batch_size: int = 200, timeout: int = 15) -> dict:
        """POST pending records in batches; rewrite queue keeping only failures."""
        pending = self.pending()
        if not pending:
            return {"sent": 0, "kept": 0}
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        confirmed: set[str] = set()
        invalid: list[dict] = []
        for i in range(0, len(pending), batch_size):
            chunk = pending[i:i + batch_size]
            req = urllib.request.Request(
                base_url.rstrip("/") + "/records",
                data=json.dumps({"records": chunk}).encode(),
                headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                results = json.loads(resp.read())["results"]
            for r in results:
                if r["status"] in ("created", "duplicate"):
                    confirmed.add(r["dedupeKey"])
                else:
                    invalid.append(r)
        keep = [e for e in pending if e["dedupeKey"] not in confirmed]
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as f:
            for e in keep:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        tmp.replace(self.path)
        return {"sent": len(confirmed), "kept": len(keep), "invalid": invalid}
