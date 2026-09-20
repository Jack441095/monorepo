"""Short-TTL cache for slow read-only status commands.

`client.business_status()` shells out (~10–15s measured). Routine company
awareness must not pay that per turn. This cache bounds staleness honestly:
callers receive ``(text, age_seconds)`` and must surface age whenever it is
material. Force-refresh bypasses the cache; on refresh failure the stale
value is served rather than nothing.
"""

from __future__ import annotations

import threading
import time

from thursday import client

DEFAULT_TTL_S = 300.0

_lock = threading.Lock()
_text: str | None = None
_at: float = 0.0


def get_business_status(
    *, force_refresh: bool = False, ttl_seconds: float = DEFAULT_TTL_S
) -> tuple[str, float]:
    """Return ``(status_text, age_seconds)``, refreshing when stale.

    - fresh cache within TTL → cached text;
    - expired or force_refresh → live read (slow), then cached;
    - live read fails after a previous success → stale text served;
    - live read fails with no cache → raises (callers degrade honestly
      rather than presenting failure text as a healthy reading).
    """
    global _text, _at

    with _lock:
        if not force_refresh and _text is not None:
            if (time.time() - _at) < ttl_seconds:
                return _text, time.time() - _at

    try:
        fresh = client.business_status()
    except Exception as exc:  # noqa: BLE001 — degrade honestly
        if _text is not None:
            return _text, time.time() - _at
        raise

    with _lock:
        _text = fresh
        _at = time.time()
    return fresh, 0.0


def invalidate() -> None:
    global _text, _at
    with _lock:
        _text = None
        _at = 0.0


def age_note(age_seconds: float, *, warn_after_s: float = 120.0) -> str:
    """Human note for materially old data; empty string for fresh reads."""
    if age_seconds < warn_after_s:
        return ""
    minutes = int(age_seconds // 60)
    return f"(business status cached {minutes} min ago)"


__all__ = ["get_business_status", "invalidate", "age_note", "DEFAULT_TTL_S"]
