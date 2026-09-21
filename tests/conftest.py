"""Shared pytest fixtures."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "string") not in sys.path:
    sys.path.insert(0, str(ROOT / "string"))


@pytest.fixture(autouse=True)
def publisher_network_restored():
    """Put the publisher's network functions back after every test.

    Tests stub `_login`, `_xrpc` and `_upload_blob` to keep the suite
    offline, and each of them should do that through `monkeypatch`. This is
    the backstop for the one that forgets: a fake left on the module leaks
    into every test that runs afterwards, and the direction to fear is a
    false pass — a test asserting that a publish was refused before it
    reached the network cannot tell a refusal from a fake that answered.
    tests/test_test_isolation.py fails if a leak gets past this.
    """
    import app.publisher as publisher
    saved = {name: getattr(publisher, name)
             for name in ("_login", "_xrpc", "_upload_blob")}
    yield
    for name, fn in saved.items():
        setattr(publisher, name, fn)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The String API on a fresh database, with the repo's lexicons and no token.

    string/app/main.py builds its Store at import time from the environment,
    so app.* is re-imported per test to pick up the temporary paths.
    """
    monkeypatch.setenv("STRING_DB", str(tmp_path / "string.db"))
    monkeypatch.setenv("STRING_LEXICONS", str(ROOT / "lexicons"))
    monkeypatch.delenv("STRING_TOKEN", raising=False)
    monkeypatch.delenv("SPINE_TOKEN", raising=False)
    # The parent package goes too: leaving it means its stale `publisher`,
    # `syndicate` and `refs` attributes survive, and a re-import rebinds
    # them one by one rather than starting clean.
    for mod in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[mod]
    from fastapi.testclient import TestClient
    import app.main as main
    return TestClient(main.app)
