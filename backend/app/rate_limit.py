"""
Rate limiting -- Phase 5, Section 56.

In-process fixed-window limiter, keyed by (bucket, client_ip). Sufficient
for a single-process staging deployment; a real multi-worker/multi-instance
production deployment would need a shared store (Redis) instead of an
in-memory dict -- documented here rather than built speculatively, since no
production hosting exists yet to actually run more than one worker
(docs/HUMAN_COMMERCIAL_REQUIREMENTS.md).

Deliberately simple: exceeding the limit returns 429, never silently drops
or degrades other behavior.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

_windows: dict[tuple[str, str], list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, max_requests: int, window_seconds: float):
    """Returns a FastAPI dependency enforcing `max_requests` per
    `window_seconds` per client IP, scoped to `bucket`."""

    def _dependency(request: Request) -> None:
        key = (bucket, _client_key(request))
        now = time.monotonic()
        timestamps = _windows[key]
        cutoff = now - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if len(timestamps) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests -- try again shortly")
        timestamps.append(now)

    return _dependency


def reset_all() -> None:
    """Test-only: clears all rate-limit state between test cases."""
    _windows.clear()
