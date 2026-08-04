"""Minimal in-process sliding-window rate limiter.

Used to throttle login attempts so an attacker can't brute-force passwords
online (PBKDF2 slows one guess but nothing capped the *number* of guesses).

Caveat: state is per-process, so with N gunicorn workers the effective limit is
~N× the configured value — still a hard ceiling that turns an unbounded online
attack into a bounded one. A Redis-backed counter would make it exact across
workers; that's the upgrade path if this ever needs to be authoritative.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> None:
        dq = self._events[key]
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        if not dq:
            self._events.pop(key, None)

    def is_blocked(self, key: str) -> bool:
        now = time.time()
        self._prune(key, now)
        return len(self._events.get(key, ())) >= self.max_events

    def record(self, key: str) -> None:
        self._events[key].append(time.time())

    def reset(self, key: str) -> None:
        self._events.pop(key, None)
