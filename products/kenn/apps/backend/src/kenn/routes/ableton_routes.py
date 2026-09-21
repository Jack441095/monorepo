"""Modular Ableton route handlers for KENN server.

Handles /api/ableton/ping, /api/ableton/watchdog, and /api/ableton/capabilities.
"""

from __future__ import annotations

from typing import Any


def handle_ableton_ping(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/ping."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        success = live_client.ping(timeout=0.5)
        return 200, {
            "ok": True,
            "connected": bool(success),
            "state": getattr(live_client, "connection_state", "unknown"),
        }
    except Exception as exc:
        return 200, {
            "ok": False,
            "connected": False,
            "state": "disconnected",
            "error": str(exc),
        }


def handle_ableton_watchdog(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/watchdog."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        status = live_client.get_connection_status()
        return 200, {
            "ok": True,
            "watchdog": status,
        }
    except Exception as exc:
        return 200, {
            "ok": False,
            "error": str(exc),
        }


def handle_ableton_capabilities(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/capabilities."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        return 200, live_client.capability_report()
    except Exception as exc:
        return 200, {
            "schema": "kenn.abletonosc_capabilities.v1",
            "available": False,
            "host": getattr(live_client, "host", "127.0.0.1"),
            "port": getattr(live_client, "port", 11000),
            "error": str(exc),
            "verified_features": {},
            "supported_parameters": {},
        }
