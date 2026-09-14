"""The shared fixture suites, run against the Python implementations.

tests/fixtures/*.json are the contract between string/app/lexicon.py and
sdk/js/lexicon.js, between string/app/strip.py and sdk/js/strip.js, and
between string/app/refs.py and sdk/js/refs.js. Both languages run these same cases: see
sdk/js/test/*.test.mjs for the other half.

If you change a validator or a strip rule, change the fixture — and both
implementations will tell you whether they still agree.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.lexicon import LexiconRegistry  # noqa: E402
from app import refs, strip  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


LEXICON_CASES = load("lexicon-cases.json")
STRIP_CASES = load("strip-cases.json")
REFS_CASES = load("refs-cases.json")


@pytest.fixture(scope="module")
def registry() -> LexiconRegistry:
    reg = LexiconRegistry()
    reg.load_dir(ROOT / "lexicons")
    return reg


@pytest.mark.parametrize("case", LEXICON_CASES, ids=lambda c: c["name"][:60])
def test_lexicon_fixture(registry, case):
    assert registry.validate_record(case["nsid"], case["body"]) == case["problems"]


@pytest.mark.parametrize("case", STRIP_CASES, ids=lambda c: c["name"][:60])
def test_strip_fixture(case):
    if case["fn"] == "bead":
        got = strip.strip_bead(case["body"], images=case.get("images"))
    elif case["fn"] == "strand":
        got = strip.strip_strand(case["body"], case.get("items", []))
    elif case["fn"] == "public":
        got = strip.strip_public(case["body"])
    elif case["fn"] == "ref":
        got = strip.strip_ref(case["body"])
    else:
        raise AssertionError(f"unknown strip fn: {case['fn']}")
    assert got == case["expected"]


@pytest.mark.parametrize("case", REFS_CASES, ids=lambda c: c["name"][:60])
def test_refs_fixture(case):
    assert getattr(refs, case["fn"])(*case["args"]) == case["expected"]


def test_strip_never_emits_a_private_key():
    """A blunt backstop over every bead/strand case: whatever the allow lists
    say, these keys must not appear anywhere in a published body. Cheap
    insurance against a future edit that adds a field to BEAD_KEEP without
    thinking about what rides inside it."""
    forbidden = {"geo", "provenance", "media", "mintId", "device", "dedupeKey"}

    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in forbidden, f"{path}.{k} leaked into a published body"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    for case in STRIP_CASES:
        if case["fn"] == "public":
            continue          # public-by-intent records keep their location
        walk(case["expected"], case["name"])
