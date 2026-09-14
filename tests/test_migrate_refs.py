"""scripts/migrate_refs.py backfills annotation subject refs, once."""
import importlib.util
import sqlite3
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


def test_main_backs_up_writes_still_in_the_wal(tmp_path: Path) -> None:
    """The String runs SQLite in WAL mode and is not guaranteed to checkpoint
    on shutdown, so the newest records may live only in string.db-wal. The
    backup must still contain them."""
    path = tmp_path / "string.db"
    live = Store(str(path))          # stays open: nothing checkpoints the WAL
    live.upsert("a1", "com.cultureblocs.annotation", "ar", T,
                {"createdAt": T, "work": {"title": "Gasholder"}})

    migrate_refs.main(str(path))

    backups = list(tmp_path.glob("string.pre-refs-*.db"))
    assert len(backups) == 1
    conn = sqlite3.connect(backups[0])
    try:
        rows = conn.execute("SELECT body FROM records").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1 and "refs" not in rows[0][0], "backup must predate the migration"
