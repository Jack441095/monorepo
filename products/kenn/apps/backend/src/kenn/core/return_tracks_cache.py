"""Return-track cache refresh for the chat-to-Live gate.

The cached Live snapshot never lists return tracks, and a message about one
(a send, or its level) needs them. This helper decides when to refetch and
attaches the result; ``server.py`` keeps owning the global so existing
monkeypatching (``test_return_mixer.py`` sets ``server._RETURNS_CACHE``)
keeps working unchanged.

The clock and the fetch are arguments, not imports, so tests pin exact
seconds and a fake bridge instead of sleeping 20 s or touching Live. The
20 s TTL is per-message cost control: this path runs for every chat message,
and a returns poll on each one would serialize chat behind OSC round-trips.
"""

from __future__ import annotations

from typing import Any, Callable

# Seconds a fetched return-track list stays fresh. Long enough that a burst
# of follow-ups ("lower it more", "now mute it") reuses one poll; short
# enough that a return added mid-conversation appears without a restart.
RETURN_TRACKS_CACHE_TTL_S = 20.0


def attach_return_tracks(
    snapshot: dict[str, Any],
    cached: tuple[float, list] | None,
    *,
    now: float,
    fetch: Callable[[], list | None],
    ttl_s: float = RETURN_TRACKS_CACHE_TTL_S,
) -> tuple[dict[str, Any], tuple[float, list] | None]:
    """Return ``(snapshot, cached)`` with return tracks attached when present.

    A miss or a stale entry refetches; a fetch failure clears the cache (so
    the next message retries) and leaves the snapshot untouched rather than
    attaching a half answer. A fresh entry is reused without touching Live.
    """
    if cached is None or now - cached[0] > ttl_s:
        try:
            tracks = fetch()
        except Exception:
            tracks = None
        cached = (now, tracks) if tracks is not None else None
    if cached is not None:
        snapshot = {**snapshot, "return_tracks": cached[1]}
    return snapshot, cached
