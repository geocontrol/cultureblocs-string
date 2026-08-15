"""Smoke check: the creative.work lexicon accepts an images-bearing record,
and pre-existing records without images still validate."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.lexicon import LexiconRegistry  # noqa: E402


def build_registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


def test_work_with_images_validates():
    reg = build_registry()
    rec = {
        "$type": "com.cultureblocs.creative.work",
        "title": "Untitled #1",
        "createdAt": "2026-08-12T10:00:00Z",
        "images": [
            {"image": {"$type": "blob",
                       "ref": {"$link": "bafkreieuchh6testcid"},
                       "mimeType": "image/png",
                       "size": 12345},
             "alt": "A test image.",
             "aspectRatio": {"width": 800, "height": 600}},
        ],
    }
    problems = reg.validate_record("com.cultureblocs.creative.work", rec)
    assert not problems, f"Expected valid record, got problems: {problems}"


def test_work_without_images_still_validates():
    reg = build_registry()
    rec = {
        "$type": "com.cultureblocs.creative.work",
        "title": "Legacy work",
        "createdAt": "2024-01-01T00:00:00Z",
    }
    problems = reg.validate_record("com.cultureblocs.creative.work", rec)
    assert not problems, f"Expected valid record, got problems: {problems}"


if __name__ == "__main__":
    test_work_with_images_validates()
    test_work_without_images_still_validates()
    print("OK: creative.work images smoke test passed")
