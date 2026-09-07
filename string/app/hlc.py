"""Hybrid logical clocks — ordering writes across devices without trusting
any one device's wall clock.

A stamp is  <millis>-<counter>-<node>  with fixed-width numeric parts, so
plain lexicographic comparison is causal comparison. That matters more than
it looks: it means SQLite can ORDER BY it, JSON can carry it, and a client
can compare two stamps with `<` in any language without a parser.

Why not wall-clock timestamps: two devices minting offline will disagree
about the time, sometimes by minutes, and the phone's clock jumping
backwards after an NTP sync must not silently un-order a write that already
happened. Why not a plain counter: it carries no relationship to real time,
so a human reading the change log learns nothing.

The rule is the usual one. A local event takes max(now, last)+tiebreak. A
received event takes max(now, last, remote)+tiebreak, which is what makes a
device that hears about a later write stop issuing stamps beneath it.

Phase 0 only stamps writes. Applying remote ops (observe()) is what Phase 2
needs it for; it is here now so the stamps written today are usable then.
"""
from __future__ import annotations

import os
import socket
import time
import uuid

MAX_COUNTER = 99_999          # five digits; see _stamp


def default_node_id() -> str:
    """This machine's identity in a stamp. Stable across restarts where the
    operator sets STRING_DEVICE_ID (they should, on a host that matters);
    otherwise the hostname, which is stable enough for a home lab, with a
    random suffix as the last resort."""
    explicit = os.environ.get("STRING_DEVICE_ID")
    if explicit:
        return explicit[:32]
    try:
        host = socket.gethostname().split(".")[0]
        if host:
            return host[:32]
    except OSError:
        pass
    return uuid.uuid4().hex[:12]


def parse(stamp: str) -> tuple[int, int, str]:
    """(millis, counter, node). Raises ValueError on a malformed stamp."""
    parts = stamp.split("-", 2)
    if len(parts) != 3:
        raise ValueError(f"malformed HLC stamp: {stamp!r}")
    return int(parts[0]), int(parts[1]), parts[2]


def is_valid(stamp: object) -> bool:
    if not isinstance(stamp, str):
        return False
    try:
        parse(stamp)
    except ValueError:
        return False
    return True


class HLC:
    def __init__(self, node: str | None = None, *, clock=None):
        self.node = node or default_node_id()
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._millis = 0
        self._counter = 0

    def _stamp(self) -> str:
        # A counter that has run out of digits would break the fixed-width
        # ordering, so spill into the next millisecond instead. Reaching this
        # takes 100k writes inside one millisecond, but a stamp that sorts
        # wrongly is worse than one that is a millisecond optimistic.
        if self._counter > MAX_COUNTER:
            self._millis += 1
            self._counter = 0
        return f"{self._millis:013d}-{self._counter:05d}-{self.node}"

    def now(self) -> str:
        """Stamp a local write."""
        phys = self._clock()
        if phys > self._millis:
            self._millis, self._counter = phys, 0
        else:
            self._counter += 1          # clock stalled or went backwards
        return self._stamp()

    def observe(self, remote: str | None) -> str:
        """Stamp a write caused by a remote one, strictly after both."""
        if not is_valid(remote):
            return self.now()
        r_millis, r_counter, _ = parse(remote)
        phys = self._clock()
        millis = max(phys, self._millis, r_millis)
        if millis == self._millis and millis == r_millis:
            counter = max(self._counter, r_counter) + 1
        elif millis == self._millis:
            counter = self._counter + 1
        elif millis == r_millis:
            counter = r_counter + 1
        else:
            counter = 0                 # physical clock moved us past both
        self._millis, self._counter = millis, counter
        return self._stamp()
