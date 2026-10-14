"""Non-blocking Ableton subsystem summary for ``/api/health``.

We keep this beside the gateway instead of inside ``server.py`` so the HTTP
layer only asks "what did the auditor last see?". Health is a liveness
endpoint for the KENN process itself: it must not synchronously compete with
the Mixing Doctor or a command request for the shared AbletonOSC exchange
lock, or a healthy server looks dead whenever Live is offline or slow. The
background auditor owns the periodic OSC poll; health reports its latest
bounded cache instead. ``unknown`` is honest before that first poll completes.
"""

from __future__ import annotations

from typing import Any


def cached_ableton_health() -> dict[str, Any]:
    """Return a non-blocking Ableton subsystem summary for ``/api/health``.

    Health is a liveness endpoint for the KENN process itself.  It must not
    synchronously compete with the Mixing Doctor or a command request for the
    shared AbletonOSC exchange lock: doing so can make a healthy HTTP server
    appear dead whenever Live is offline or slow.  The background auditor owns
    the periodic OSC poll; health reports its latest bounded cache instead.
    ``unknown`` is honest before that first poll has completed.
    """
    try:
        from kenn.mixing_doctor import get_latest_session_state

        snapshot = get_latest_session_state()
        status = str(snapshot.get("status") or "unknown") if isinstance(snapshot, dict) else "unknown"
        if status not in {"connected", "offline", "dispatched", "unknown"}:
            status = "unknown"
        return {"status": status, "connected": status == "connected"}
    except Exception as exc:
        return {"status": "error", "connected": False, "error": str(exc)[:256]}
