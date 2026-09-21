"""The suite must start every test with the real publisher, not a leftover fake.

Several tests stub `publisher._login`, `_xrpc` and `_upload_blob` to keep the
suite offline. A stub left behind leaks into whatever runs next, and the
dangerous direction is a false pass: a test that expects a publish to be
refused before it reaches the network cannot tell a refusal from a fake that
quietly answered. This file sorts after every stubbing test, so it fails if
one of them leaves its fake in place.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app import publisher  # noqa: E402

NETWORK = ("_login", "_xrpc", "_upload_blob")


def test_the_publisher_still_holds_its_own_network_functions():
    for name in NETWORK:
        fn = getattr(publisher, name)
        assert getattr(fn, "__module__", None) == "app.publisher", (
            f"publisher.{name} is {fn!r} — an earlier test left a fake behind; "
            "stub with monkeypatch.setattr so pytest puts it back")
        assert fn.__name__ == name
