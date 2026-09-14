"""Shared pytest fixtures."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "string") not in sys.path:
    sys.path.insert(0, str(ROOT / "string"))


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
    for mod in [m for m in sys.modules if m.startswith("app.")]:
        del sys.modules[mod]
    from fastapi.testclient import TestClient
    import app.main as main
    return TestClient(main.app)
