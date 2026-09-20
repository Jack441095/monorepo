"""HTTP write-boundary controls shared by business route dispatchers."""

from __future__ import annotations

import enquiry_guard


def enforce_write_boundary(handler, access: str) -> bool:
    """Reject unsafe origin or excessive write traffic before route dispatch."""
    if access in {"public", "demo"} and not handler.request_is_same_origin():
        handler.send_json(403, {"error": "Cross-origin request rejected."})
        return False
    scope = {
        "demo": ("demo_write", "Too many demo requests. Try again shortly."),
        "authenticated-write": (
            "dashboard_write",
            "Too many dashboard changes. Try again shortly.",
        ),
    }.get(access)
    if scope and enquiry_guard.is_rate_limited(
        getattr(handler, "client_address", None), scope=scope[0]
    ):
        handler.send_json(429, {"error": scope[1]})
        return False
    return True

