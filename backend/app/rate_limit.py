"""
Rate limiting -- Phase 5, Section 56.

In-process fixed-window limiter, keyed by (bucket, client_key). Sufficient
for a single-process staging deployment; a real multi-worker/multi-instance
production deployment would need a shared store (Redis) instead of an
in-memory dict -- documented here rather than built speculatively, since no
production hosting exists yet to actually run more than one worker
(docs/HUMAN_COMMERCIAL_REQUIREMENTS.md).

Client key derivation: behind Railway/Render the socket peer is the proxy,
so every client would collapse onto one shared bucket (turning a 5/min
per-IP limit into a global lockout lever). We therefore take the first
X-Forwarded-For entry, which the trusted edge proxy sets to the real client
and overwrites on the way in. Direct (non-proxied) access falls back to the
socket peer.

Memory: buckets are evicted lazily. A hard cap on tracked buckets bounds
memory against attacker-controllable key space (spoofed IPs); eviction only
removes genuinely stale or capped-out buckets, never live ones.

Deliberately simple: exceeding the limit returns 429, never silently drops
or degrades other behavior.
"""
from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request

_windows: dict[tuple[str, str], deque[float]] = {}

# Hard cap on tracked (bucket, key) pairs. A remote attacker who can vary
# their apparent client key must not be able to grow this dict without
# bound; past the cap, oldest-stale buckets are swept.
MAX_TRACKED_BUCKETS = 10_000

# Rotation constants for timestamp deque cleanup.
_WINDOW_MAXLEN_HINT = 128


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry = the client as seen by the trusted edge proxy.
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _sweep(now: float, window_seconds: float) -> None:
    """Drop buckets whose newest timestamp is outside the current window.
    Only called when the dict exceeds MAX_TRACKED_BUCKETS, so the O(n) scan
    is amortised over a large number of requests."""
    cutoff = now - window_seconds
    stale = [key for key, timestamps in _windows.items() if not timestamps or timestamps[-1] < cutoff]
    for key in stale:
        del _windows[key]
    # If a single window is being flooded with more distinct keys than the
    # cap, drop everything older than half a window so the flood itself
    # cannot keep the dict pinned above the cap.
    if len(_windows) > MAX_TRACKED_BUCKETS:
        deep_cutoff = now - window_seconds / 2
        for key in [k for k, ts in _windows.items() if not ts or ts[-1] < deep_cutoff]:
            del _windows[key]
    # Last resort: evict the least-recently-active buckets by timestamp so
    # the cap is deterministic even when every bucket is brand new (a flood
    # of spoofed keys). Live single clients lose their counter only under a
    # sustained flood, which is itself already an active incident.
    while len(_windows) > MAX_TRACKED_BUCKETS:
        oldest = min(_windows, key=lambda k: _windows[k][-1] if _windows[k] else 0.0)
        del _windows[oldest]


def rate_limit(bucket: str, max_requests: int, window_seconds: float):
    """Returns a FastAPI dependency enforcing `max_requests` per
    `window_seconds` per client IP, scoped to `bucket`."""

    def _dependency(request: Request) -> None:
        key = (bucket, _client_key(request))
        now = time.monotonic()
        timestamps = _windows.get(key)
        if timestamps is None:
            timestamps = _windows[key] = deque(maxlen=max(max_requests, _WINDOW_MAXLEN_HINT))
        cutoff = now - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()  # O(1), unlike list.pop(0)
        if len(timestamps) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests -- try again shortly")
        timestamps.append(now)
        if len(_windows) > MAX_TRACKED_BUCKETS:
            _sweep(now, window_seconds)

    return _dependency


def reset_all() -> None:
    """Test-only: clears all rate-limit state between test cases."""
    _windows.clear()
