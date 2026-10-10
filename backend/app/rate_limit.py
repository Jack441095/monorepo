"""
Rate limiting -- Phase 5, Section 56.

In-process fixed-window limiter, keyed by (bucket, client_key). Counters are
local to each process: multiple production instances do not share a quota.
An edge limit or shared store is required for a deployment-wide quota.

Client key derivation: Fly's edge provides Fly-Client-IP, which identifies
the connection it accepted. The production API resolves directly to Fly, so
we use that platform header instead of the caller-controlled X-Forwarded-For
chain. If the header is missing on Fly, use the socket peer rather than
trusting a spoofable forwarded value. Outside Fly, X-Forwarded-For remains a
local development fallback; direct access falls back to the socket peer.

Memory: buckets are evicted lazily. A hard cap on tracked buckets bounds
memory against attacker-controllable key space (spoofed IPs); eviction only
removes genuinely stale or capped-out buckets, never live ones.

Deliberately simple: exceeding the limit returns 429, never silently drops
or degrades other behavior.
"""
from __future__ import annotations

import os
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
    fly_client_ip = request.headers.get("fly-client-ip", "").strip()
    if fly_client_ip:
        return fly_client_ip

    # Fly terminates public connections and supplies Fly-Client-IP. If it is
    # absent, a shared proxy bucket is safer than letting callers spoof XFF.
    if os.getenv("FLY_APP_NAME"):
        return request.client.host if request.client else "unknown"

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Local reverse-proxy runs may not have Fly's trusted client header.
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
