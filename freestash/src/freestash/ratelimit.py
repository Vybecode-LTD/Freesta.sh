"""A small sliding-window rate limiter for the auth endpoints.

In-process on purpose: the API runs as one Railway service. If it ever scales out to several replicas,
move the buckets to Postgres or Redis, or each replica will allow its own full quota.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

SWEEP_EVERY_SECONDS = 60.0


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._clock = clock
        self._longest_window = 0.0
        self._last_sweep = clock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = self._clock()
        with self._lock:
            self._longest_window = max(self._longest_window, window_seconds)
            if now - self._last_sweep > SWEEP_EVERY_SECONDS:
                self._sweep(now)
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def _sweep(self, now: float) -> None:
        """Drop keys idle for longer than any window: keys carry client-chosen emails and IPs, so without
        this the table grows for as long as the process runs."""
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] > self._longest_window]:
            del self._hits[key]
        self._last_sweep = now

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
