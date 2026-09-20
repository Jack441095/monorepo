"""Unit tests for kenn.routes.ableton_routes."""

from __future__ import annotations

from unittest.mock import MagicMock
from kenn.routes.ableton_routes import (
    handle_ableton_ping,
    handle_ableton_watchdog,
    handle_ableton_capabilities,
)


def test_handle_ableton_ping_when_client_none():
    code, data = handle_ableton_ping(None)
    assert code == 500
    assert data["ok"] is False


def test_handle_ableton_ping_success():
    client = MagicMock()
    client.ping.return_value = True
    client.connection_state = "connected"
    code, data = handle_ableton_ping(client)
    assert code == 200
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["state"] == "connected"


def test_handle_ableton_ping_exception():
    client = MagicMock()
    client.ping.side_effect = RuntimeError("Bridge unavailable")
    code, data = handle_ableton_ping(client)
    assert code == 200
    assert data["ok"] is False
    assert data["connected"] is False
    assert data["state"] == "disconnected"


def test_handle_ableton_watchdog_success():
    client = MagicMock()
    client.get_connection_status.return_value = {
        "state": "connected",
        "consecutive_failures": 0,
        "circuit_broken": False,
    }
    code, data = handle_ableton_watchdog(client)
    assert code == 200
    assert data["ok"] is True
    assert data["watchdog"]["state"] == "connected"


def test_handle_ableton_capabilities_success():
    client = MagicMock()
    client.capability_report.return_value = {
        "schema": "kenn.abletonosc_capabilities.v1",
        "available": True,
    }
    code, data = handle_ableton_capabilities(client)
    assert code == 200
    assert data["available"] is True

