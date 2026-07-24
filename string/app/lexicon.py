"""Minimal Lexicon validator.

Validates record bodies against the subset of the atproto Lexicon language
used by the com.cultureblocs.* schemas: object, string (datetime/uri/did
formats, maxGraphemes, knownValues advisory), number, integer, boolean,
ref, union, array.

Deliberately small. When promotion to a real PDS lands, the PDS performs
authoritative validation; this keeps Tier 0 data honest in the meantime.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$"
)
DID_RE = re.compile(r"^did:[a-z0-9]+:.+$")


class LexiconError(ValueError):
    pass


class LexiconRegistry:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def load_dir(self, path: Path) -> None:
        for f in sorted(path.rglob("*.json")):
            doc = json.loads(f.read_text())
            if "id" in doc and "defs" in doc:
                self.docs[doc["id"]] = doc

    def record_types(self) -> list[str]:
        out = []
        for nsid, doc in self.docs.items():
            main = doc["defs"].get("main")
            if main and main.get("type") == "record":
                out.append(nsid)
        return out

    def _resolve(self, ref: str, current_nsid: str) -> dict:
        if ref.startswith("#"):
            nsid, frag = current_nsid, ref[1:]
        elif "#" in ref:
            nsid, frag = ref.split("#", 1)
        else:
            nsid, frag = ref, "main"
        doc = self.docs.get(nsid)
        if doc is None:
            raise LexiconError(f"unknown lexicon: {nsid}")
        schema = doc["defs"].get(frag)
        if schema is None:
            raise LexiconError(f"unknown def: {nsid}#{frag}")
        return schema

    def validate_record(self, nsid: str, body: dict) -> list[str]:
        """Return list of problems; empty list means valid."""
        doc = self.docs.get(nsid)
        if doc is None:
            return [f"unknown record type: {nsid}"]
        main = doc["defs"].get("main", {})
        if main.get("type") != "record":
            return [f"{nsid} is not a record lexicon"]
        problems: list[str] = []
        self._check(main["record"], body, nsid, "$", problems)
        return problems

    def _check(self, schema: dict, value, nsid: str, path: str, problems: list[str]) -> bool:
        t = schema.get("type")
        if t == "ref":
            try:
                target = self._resolve(schema["ref"], nsid)
            except LexiconError as e:
                problems.append(f"{path}: {e}")
                return False
            tnsid = schema["ref"].split("#")[0] if "#" in schema["ref"] and not schema["ref"].startswith("#") else nsid
            return self._check(target, value, tnsid, path, problems)

        if t == "union":
            for ref in schema.get("refs", []):
                trial: list[str] = []
                try:
                    target = self._resolve(ref, nsid)
                except LexiconError:
                    continue
                tnsid = ref.split("#")[0] if "#" in ref and not ref.startswith("#") else nsid
                if self._check(target, value, tnsid, path, trial) and not trial:
                    return True
            problems.append(f"{path}: does not match any union variant {schema.get('refs')}")
            return False

        if t == "object":
            if not isinstance(value, dict):
                problems.append(f"{path}: expected object")
                return False
            ok = True
            for req in schema.get("required", []):
                if req not in value:
                    problems.append(f"{path}.{req}: required field missing")
                    ok = False
            props = schema.get("properties", {})
            for k, v in value.items():
                if k == "$type":
                    continue
                sub = props.get(k)
                if sub is None:
                    continue  # unknown fields tolerated (forward compat)
                if not self._check(sub, v, nsid, f"{path}.{k}", problems):
                    ok = False
            return ok

        if t == "array":
            if not isinstance(value, list):
                problems.append(f"{path}: expected array")
                return False
            maxlen = schema.get("maxLength")
            if maxlen is not None and len(value) > maxlen:
                problems.append(f"{path}: exceeds maxLength {maxlen}")
                return False
            items = schema.get("items")
            ok = True
            for i, item in enumerate(value):
                if items and not self._check(items, item, nsid, f"{path}[{i}]", problems):
                    ok = False
            return ok

        if t == "string":
            if not isinstance(value, str):
                problems.append(f"{path}: expected string")
                return False
            fmt = schema.get("format")
            if fmt == "datetime" and not DATETIME_RE.match(value):
                problems.append(f"{path}: not an ISO 8601 datetime: {value!r}")
                return False
            if fmt == "did" and not DID_RE.match(value):
                problems.append(f"{path}: not a DID: {value!r}")
                return False
            maxg = schema.get("maxGraphemes")
            if maxg is not None and len(value) > maxg:
                problems.append(f"{path}: exceeds maxGraphemes {maxg}")
                return False
            # knownValues are advisory in Lexicon: unknown values allowed.
            return True

        if t == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                problems.append(f"{path}: expected integer")
                return False
            return True

        if t == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{path}: expected number")
                return False
            return True

        if t == "boolean":
            if not isinstance(value, bool):
                problems.append(f"{path}: expected boolean")
                return False
            return True

        if t == "blob":
            # blob fields are populated by the PDS at publish time; locally we
            # accept the standard blob object shape without deep checks.
            if not isinstance(value, dict):
                problems.append(f"{path}: expected blob object")
                return False
            return True

        if t == "unknown":
            return True

        problems.append(f"{path}: unsupported schema type {t!r}")
        return False
