"""Tiny in-process sliding-window rate limiter for login attempts.

Keyed by client identifier (IP). This is a per-process limiter — adequate for
single-instance deployments and as a first line of defence. Behind multiple web
workers or a load balancer you'd move this to Redis; the interface stays the same.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_s: int = 60) -> bool:
    """Return True if `key` is under `limit` events in the trailing window."""
    now = time.monotonic()
    q = _hits[key]
    cutoff = now - window_s
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def reset(key: str) -> None:
    _hits.pop(key, None)