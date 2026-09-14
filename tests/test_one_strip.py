"""There is one strip. The publisher and both scripts use strip.py's
functions rather than private copies that could drift (R5).

Checked by where each function is defined, not by identity: the `client`
fixture re-imports app.* per test, so the same function can exist as two
objects in one session."""
import importlib.util
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402

STRIP_PY = str(ROOT / "string" / "app" / "strip.py")


def defined_in_strip(fn) -> bool:
    return inspect.getsourcefile(fn) == STRIP_PY


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publisher_uses_the_canonical_strip() -> None:
    assert defined_in_strip(publisher.strip_bead)
    assert defined_in_strip(publisher.strip_strand)
    assert defined_in_strip(publisher.strip_public)


def test_promote_uses_the_canonical_strip() -> None:
    promote = load_script("promote")
    assert defined_in_strip(promote.strip_bead)
    assert defined_in_strip(promote.strip_strand)


def test_static_export_is_the_canonical_strip_plus_media() -> None:
    export = load_script("export_public")
    assert defined_in_strip(export.strip_strand)
    body = {"$type": "com.cultureblocs.bead", "kind": "visit",
            "geo": {"lat": 1, "lng": 2, "precision": "exact"},
            "media": [{"uri": "/media/a.jpg", "alt": "A gasholder", "mime": "image/jpeg"}]}
    assert export.strip_item(body) == {
        "$type": "com.cultureblocs.bead", "kind": "visit",
        "media": [{"uri": "/media/a.jpg", "alt": "A gasholder"}]}
