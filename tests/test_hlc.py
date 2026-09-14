"""HLC: stamps must sort causally as plain strings, and must not go backwards
when the wall clock does."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "string"))
from app.hlc import HLC, is_valid, parse  # noqa: E402


class FakeClock:
    def __init__(self, ms: int = 1_700_000_000_000):
        self.ms = ms

    def __call__(self) -> int:
        return self.ms


def test_stamps_from_one_node_increase_lexicographically():
    clock = FakeClock()
    hlc = HLC("brick", clock=clock)
    stamps = []
    for _ in range(3):
        stamps.append(hlc.now())        # same millisecond: counter must carry it
    clock.ms += 1
    stamps.append(hlc.now())
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_a_backwards_wall_clock_does_not_produce_a_backwards_stamp():
    clock = FakeClock()
    hlc = HLC("phone", clock=clock)
    before = hlc.now()
    clock.ms -= 5_000                   # NTP correction, or a phone in a tunnel
    after = hlc.now()
    assert after > before


def test_observe_issues_a_stamp_after_both_sides():
    clock = FakeClock()
    local = HLC("brick", clock=clock)
    mine = local.now()
    theirs = f"{clock.ms + 10_000:013d}-{7:05d}-phone"   # their clock runs fast
    merged = local.observe(theirs)
    assert merged > mine
    assert merged > theirs
    assert local.now() > merged         # and we stay above it afterwards


def test_observe_tolerates_a_malformed_remote_stamp():
    hlc = HLC("brick", clock=FakeClock())
    assert hlc.observe("not-a-stamp") > "0"
    assert hlc.observe(None) > "0"


def test_fixed_width_means_string_order_is_numeric_order():
    """The whole design rests on this: 999 must sort below 1000."""
    clock = FakeClock(999)
    a = HLC("n", clock=clock).now()
    clock2 = FakeClock(1000)
    b = HLC("n", clock=clock2).now()
    assert a < b


def test_counter_overflow_spills_into_the_next_millisecond():
    clock = FakeClock()
    hlc = HLC("n", clock=clock)
    stamps = [hlc.now() for _ in range(100_003)]   # forces the five-digit spill
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


@pytest.mark.parametrize("bad", ["", "abc", "123-456", 42, None])
def test_is_valid_rejects_malformed(bad):
    assert is_valid(bad) is False


def test_node_id_may_contain_dashes():
    hlc = HLC("brick-01-eu", clock=FakeClock())
    millis, counter, node = parse(hlc.now())
    assert node == "brick-01-eu"
