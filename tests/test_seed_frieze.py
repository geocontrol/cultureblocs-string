"""Artworld rows -> CultureBlocs record bodies. Pure mapping, no I/O."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "string"))
from seed_frieze import fair_event, stand_lineup, day_list  # noqa: E402
from app.lexicon import LexiconRegistry  # noqa: E402

NOW = "2026-08-18T10:00:00Z"
FAIR = {"slug": "frieze-london-2026", "name": "Frieze London",
        "city": "London", "edition_year": 2026}
ROW = {"gallery_id": 42, "name": "Alison Jacques", "section": "Galleries",
       "description": "A London gallery founded in 2004."}


def registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


def test_day_list_is_inclusive_of_both_ends():
    assert day_list("2026-10-15", "2026-10-19") == [
        "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19"]


def test_day_list_handles_a_single_day():
    assert day_list("2026-10-15", "2026-10-15") == ["2026-10-15"]


def test_fair_event_spans_the_run():
    key, body = fair_event(FAIR, "2026-10-15", "2026-10-19", NOW)
    assert key == "frieze:frieze-london-2026:fair"
    assert body["$type"] == "community.lexicon.calendar.event"
    assert body["name"] == "Frieze London 2026"
    assert body["startsAt"].startswith("2026-10-15")
    assert body["endsAt"].startswith("2026-10-19")


def test_fair_event_carries_the_seed_tags():
    """Every seeded record must be identifiable as seeded and removable —
    the event no less than the stands. Rounds also reads the slug back off
    this tag to know which fair it is showing."""
    _, body = fair_event(FAIR, "2026-10-15", "2026-10-19", NOW)
    assert "seed:artworld" in body["tags"]
    assert "fair:frieze-london-2026" in body["tags"]


def test_fair_event_validates():
    _, body = fair_event(FAIR, "2026-10-15", "2026-10-19", NOW)
    problems = registry().validate_record(
        "community.lexicon.calendar.event", body)
    assert not problems, problems


def test_stand_names_the_gallery_through_billing():
    """These galleries have no repo, so `venue` stays empty and the gallery is
    named through billing, whose creditRef requires only a name."""
    _, body = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026",
                           [], NOW)
    assert body["billing"][0] == {"name": "Alison Jacques", "role": "gallery"}
    assert "venue" not in body, "venue must be absent, never faked"


def test_stand_carries_section_and_seed_tags():
    _, body = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026",
                           [], NOW)
    assert "section:Galleries" in body["tags"]
    assert "seed:artworld" in body["tags"]
    assert "fair:frieze-london-2026" in body["tags"]


def test_stand_dedupe_key_is_stable_and_gallery_scoped():
    k1, _ = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026", [], NOW)
    k2, _ = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026", [], "2027-01-01T00:00:00Z")
    assert k1 == k2 == "frieze:frieze-london-2026:stand:42"


def test_artists_become_additional_billing_entries():
    _, body = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026",
                           ["Sheila Hicks", "Ryan Gander"], NOW)
    roles = [b["role"] for b in body["billing"]]
    names = [b["name"] for b in body["billing"]]
    assert roles[0] == "gallery"
    assert roles[1:] == ["artist", "artist"]
    assert names == ["Alison Jacques", "Sheila Hicks", "Ryan Gander"]


def test_stand_with_no_section_still_maps():
    row = dict(ROW, section=None)
    _, body = stand_lineup(row, "spine://records/fair1", "frieze-london-2026", [], NOW)
    assert not any(t.startswith("section:") for t in body["tags"])
    assert "seed:artworld" in body["tags"]


def test_empty_description_is_omitted_not_blank():
    row = dict(ROW, description="")
    _, body = stand_lineup(row, "spine://records/fair1", "frieze-london-2026", [], NOW)
    assert "note" not in body


def test_stand_validates():
    _, body = stand_lineup(ROW, "spine://records/fair1", "frieze-london-2026",
                           ["Sheila Hicks"], NOW)
    problems = registry().validate_record("com.cultureblocs.venue.lineup", body)
    assert not problems, problems


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK: seed_frieze mapping tests passed")
