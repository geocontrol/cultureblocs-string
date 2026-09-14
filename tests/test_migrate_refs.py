"""scripts/migrate_refs.py backfills annotation subject refs, once."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.db import Store  # noqa: E402

spec = importlib.util.spec_from_file_location("migrate_refs", ROOT / "scripts/migrate_refs.py")
migrate_refs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate_refs)

T = "2026-09-14T10:00:00Z"


def test_backfills_annotations_once_and_leaves_beads_alone(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "string.db"))
    ann, _ = store.upsert("a1", "com.cultureblocs.annotation", "ar", T,
                          {"createdAt": T, "work": {"title": "Gasholder", "wikidata": "Q1892745"}})
    bead, _ = store.upsert("b1", "com.cultureblocs.bead", "pocket", T,
                           {"createdAt": T, "kind": "watch", "work": {"title": "Severance"}})

    assert migrate_refs.migrate(store) == 1
    assert store.get(ann)["body"]["refs"] == [{
        "type": "work", "role": "subject", "descriptor": {"label": "Gasholder"},
        "externalIds": [{"scheme": "wikidata", "id": "Q1892745"}]}]
    assert "refs" not in store.get(bead)["body"]

    revision = store.get(ann)["revision"]
    assert migrate_refs.migrate(store) == 0
    assert store.get(ann)["revision"] == revision
