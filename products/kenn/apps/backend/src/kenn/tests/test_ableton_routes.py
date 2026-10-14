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


def test_handle_ableton_device_matrix_when_client_none():
    from kenn.routes.ableton_routes import handle_ableton_device_matrix
    code, data = handle_ableton_device_matrix(None)
    assert code == 500
    assert data["ok"] is False


def test_handle_ableton_device_matrix_success():
    from kenn.routes.ableton_routes import handle_ableton_device_matrix
    client = MagicMock()
    client.device_matrix_report.return_value = {
        "schema": "kenn.ableton_device_matrix.v1",
        "devices": [{"name": "Compressor", "type": "audio_effect"}],
    }
    code, data = handle_ableton_device_matrix(client, without_parameters=True)
    assert code == 200
    assert data["schema"] == "kenn.ableton_device_matrix.v1"
    client.device_matrix_report.assert_called_once_with(include_parameters=False)


def test_handle_ableton_device_matrix_exception():
    from kenn.routes.ableton_routes import handle_ableton_device_matrix
    client = MagicMock()
    client.device_matrix_report.side_effect = RuntimeError("OSC timeout")
    code, data = handle_ableton_device_matrix(client)
    assert code == 200
    assert data["available"] is False
    assert "OSC timeout" in data["error"]


def test_handle_osc_session_success():
    from kenn.routes.ableton_routes import handle_osc_session
    client = MagicMock()
    client.query_session_state.return_value = {"status": "connected", "tracks": []}
    code, data = handle_osc_session(client)
    assert code == 200
    assert data["status"] == "connected"


def test_handle_osc_song_time_and_locators():
    from kenn.routes.ableton_routes import handle_osc_song_time, handle_osc_locators
    client = MagicMock()
    client.get_current_song_time.return_value = 16.0
    client.get_locators_with_status.return_value = ([{"name": "Verse", "time": 1.0}], True)

    code, data = handle_osc_song_time(client)
    assert code == 200
    assert data["current_song_time"] == 16.0

    code, data = handle_osc_locators(client)
    assert code == 200
    assert len(data["locators"]) == 1


def test_handle_osc_midi_clip_and_clip_slot():
    from kenn.routes.ableton_routes import handle_osc_midi_clip, handle_osc_clip_slot
    client = MagicMock()
    client.get_midi_clip_state.return_value = {"success": True, "notes": []}
    client.get_clip_slot_state.return_value = {"success": True, "has_clip": True}
    client.query_session_topology.return_value = {"tracks": [{"index": 0, "name": "Kick"}]}

    code, data = handle_osc_midi_clip(client, "0", "0")
    assert code == 200
    assert data["track_name"] == "Kick"

    code, data = handle_osc_clip_slot(client, "0", "0")
    assert code == 200
    assert data["track_name"] == "Kick"
    assert data["has_clip"] is True


def test_handle_osc_device_parameters_and_value_string():
    from kenn.routes.ableton_routes import handle_osc_device_parameters, handle_osc_device_parameter_value_string
    client = MagicMock()
    client.get_device_parameters.return_value = {"success": True, "parameters": []}
    client.get_device_parameter_value_string.return_value = {"success": True, "value_string": "100 Hz"}

    code, data = handle_osc_device_parameters(client, "0", "1")
    assert code == 200
    assert data["success"] is True

    code, data = handle_osc_device_parameter_value_string(client, "0", "1", "2")
    assert code == 200
    assert data["value_string"] == "100 Hz"


def test_handle_arrangement_analysis_requires_session_id():
    from kenn.routes.ableton_routes import handle_arrangement_analysis
    code, data = handle_arrangement_analysis(None, session_id="")
    assert code == 400
    assert data["ok"] is False
    assert "Missing session_id" in data["error"]


