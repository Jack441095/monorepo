"""Per-client, per-scope request rate limiting for kenn/server.py.

Extracted 2026-07-14 as part of decomposing server.py (1,163 lines,
docs/codebase_scan_12_07.md §2.2 "large un-decomposed files"). Pure,
self-contained state -- no test currently monkeypatches these names, so
this is a plain extraction with no monkeypatch-copy-semantics risk (see
the llm_improvement.py decomposition, same session, for what that risk
looks like and how to fix it when it does apply).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler

RATE_LIMITS = {
    "ask": (30, 60),
    "audiogen": (8, 60 * 60),
    "audiogen_status": (80, 60),
    "suggest": (80, 60),
    "feedback": (60, 60),
    "mix_review": (6, 60 * 60),
    "mix_review_status": (120, 60),
    "automix_upload": (6, 60 * 60),
    "automix_status": (120, 60),
    "stem_separate_upload": (6, 60 * 60),
    "stem_separate_status": (120, 60),
    "report": (60, 60),
    "mutation": (60, 60),
}
RATE_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
RATE_LOCK = threading.Lock()
MAX_TRACKED_BUCKETS = 10_000
_MAX_WINDOW_SECONDS = max(window for _, window in RATE_LIMITS.values())


def client_key(handler: BaseHTTPRequestHandler) -> str:
    for header in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
        value = str(handler.headers.get(header, "")).split(",", 1)[0].strip()
        if value:
            return value[:80]
    host = handler.client_address[0] if handler.client_address else "unknown"
    return str(host)[:80]


def rate_allowed(key: str, scope: str) -> tuple[bool, int]:
    limit, window = RATE_LIMITS.get(scope, (60, 60))
    now_ts = time.time()
    bucket_key = (key, scope)
    with RATE_LOCK:
        bucket = RATE_BUCKETS[bucket_key]
        while bucket and now_ts - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = max(1, int(window - (now_ts - bucket[0])))
            return False, retry
        bucket.append(now_ts)
        # A distinct (key, scope) pair never revisited would otherwise sit in
        # RATE_BUCKETS forever once its own deque empties out -- every unique
        # client_key (an untrusted, client-supplied header value on some
        # deployments) creates one. Bound the number of tracked buckets
        # rather than only the entries inside each one.
        if len(RATE_BUCKETS) > MAX_TRACKED_BUCKETS:
            _evict_stale_buckets(now_ts)
    return True, 0


def _evict_stale_buckets(now_ts: float) -> None:
    """Call under RATE_LOCK: drop buckets whose entries have all expired."""
    stale = [
        bucket_key
        for bucket_key, bucket in RATE_BUCKETS.items()
        if not bucket or now_ts - bucket[-1] > _MAX_WINDOW_SECONDS
    ]
    for bucket_key in stale:
        del RATE_BUCKETS[bucket_key]
