from __future__ import annotations

import pytest

from kenn.core.live_backend import ControlDeckMCPBackend, ReadOnlyMCPBackend
from kenn.core.live_backend_factory import create_live_backend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


def test_read_only_mcp_backend_maps_snapshot_and_parameter_tools() -> None:
    calls: list[tuple[str, dict]] = []

    def call_tool(name: str, arguments: dict) -> dict:
        calls.append((name, arguments))
        if name == "live_snapshot":
            return {
                "status": "connected",
                "tracks": [{"index": 3, "name": "4-Audio", "devices": [{"index": 1, "name": "Glue Compressor"}]}],
            }
        if name == "live_parameters":
            return {
                "success": True,
                "device_name": "Glue Compressor",
                "parameters": [{"index": 4, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0}],
            }
        if name == "live_parameter_display":
            return {"success": True, "value_string": "1"}
        raise AssertionError(name)

    backend = ReadOnlyMCPBackend(call_tool)
    assert backend.query_session_topology()["status"] == "connected"
    assert backend.query_session_understanding()["status"] == "connected"
    assert backend.get_device_parameters(3, 1)["device_name"] == "Glue Compressor"
    assert backend.get_device_parameter_value_string(3, 1, 4)["value_string"] == "1"
    assert calls == [
        ("live_snapshot", {"detail": "topology"}),
        ("live_snapshot", {"detail": "understanding"}),
        ("live_parameters", {"track_index": 3, "device_index": 1}),
        ("live_parameter_display", {"track_index": 3, "device_index": 1, "parameter_index": 4}),
    ]


def test_read_only_mcp_backend_cannot_write_or_advertise_write_tools() -> None:
    calls: list[tuple[str, dict]] = []
    backend = ReadOnlyMCPBackend(lambda name, arguments: calls.append((name, arguments)) or {})

    with pytest.raises(RuntimeError, match="read-only"):
        backend.set_device_parameter(3, 1, 4, 4.0)
    with pytest.raises(RuntimeError, match="read-only"):
        backend.set_track_volume(3, 0.5)

    report = backend.capability_report()
    assert report["status"] == "read_only"
    assert report["write"] == []
    assert calls == []


def test_read_only_mcp_backend_enters_kenn_proposal_path_but_cannot_apply() -> None:
    calls: list[tuple[str, dict]] = []

    def call_tool(name: str, arguments: dict) -> dict:
        calls.append((name, arguments))
        if name == "live_snapshot":
            return {
                "status": "connected",
                "tracks": [
                    {"index": 0, "name": "1-MIDI", "devices": []},
                    {"index": 1, "name": "2-MIDI", "devices": []},
                    {"index": 2, "name": "3-Audio", "devices": []},
                    {"index": 3, "name": "4-Audio", "devices": [{"index": 1, "name": "Glue Compressor"}]},
                ],
            }
        if name == "live_parameters":
            return {
                "success": True,
                "device_name": "Glue Compressor",
                "parameters": [{"index": 4, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0}],
            }
        if name == "live_parameter_display":
            return {"success": True, "value_string": "1"}
        raise AssertionError(name)

    backend = ReadOnlyMCPBackend(call_tool)
    service = LiveActionService(backend)
    planned = handle_command(
        "set Glue Compressor Attack to 4 on track 4",
        session_id="mcp-read-only-command",
        service=service,
    )
    assert planned["status"] == "confirmation_required"
    assert "Live displays 1" in planned["answer"]

    proposal = planned["proposal"]
    applied = handle_command(
        "set Glue Compressor Attack to 4 on track 4",
        session_id="mcp-read-only-command",
        service=service,
        proposal=proposal,
        confirm_token=proposal["confirmation_token"],
        idempotency_key=proposal["id"],
    )
    assert applied["status"] == "failed"
    assert "read-only" in applied["answer"]
    assert not any(name.startswith("set_") for name, _ in calls)


def test_control_deck_backend_maps_real_provider_tool_contract() -> None:
    calls: list[tuple[str, dict]] = []

    def call_tool(name: str, arguments: dict) -> dict:
        calls.append((name, arguments))
        if name == "ableton_status":
            return {"ok": True, "data": {"connected": True}}
        if name == "get_live_set":
            return {
                "ok": True,
                "data": {
                    "tracks": [{"index": 0, "name": "Drums"}],
                    "scenes": {"scenes": [{"index": 0, "name": "Intro"}]},
                    "transport": {
                        "tempo": 126.0,
                        "isPlaying": True,
                        "songPositionBeats": 32.5,
                    },
                    "timeSignature": {"numerator": 4, "denominator": 4},
                    "selectedTrack": {"index": 0, "name": "Drums"},
                },
            }
        if name == "get_track":
            assert arguments == {"trackIndex": 0}
            return {
                "ok": True,
                "data": {
                    "index": 0,
                    "name": "Drums",
                    "volume": 0.75,
                    "pan": -0.1,
                    "muted": False,
                    "soloed": True,
                    "armed": False,
                },
            }
        if name == "list_devices":
            assert arguments == {"trackIndex": 0}
            return {
                "ok": True,
                "data": {
                    "devices": [
                        {"index": 0, "name": "Drum Buss", "className": "AudioEffectGroupDevice"}
                    ]
                },
            }
        if name == "get_device_parameters":
            assert arguments == {"trackIndex": 0, "deviceIndex": 0}
            return {
                "ok": True,
                "data": {
                    "device": {"name": "Drum Buss"},
                    "parameters": [
                        {
                            "index": 2,
                            "name": "Drive",
                            "value": 0.4,
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "displayValue": "40%",
                        }
                    ],
                },
            }
        raise AssertionError(name)

    backend = ControlDeckMCPBackend(call_tool)
    snapshot = backend.query_session_state()
    assert snapshot == {
        "status": "connected",
        "host": "stdio",
        "port": None,
        "backend": "ableton-control-deck-mcp",
        "tracks": [
            {
                "index": 0,
                "name": "Drums",
                "devices": [
                    {"index": 0, "name": "Drum Buss", "class_name": "AudioEffectGroupDevice"}
                ],
                "volume": 0.75,
                "pan": -0.1,
                "muted": False,
                "soloed": True,
                "armed": False,
            }
        ],
        "scenes": [{"index": 0, "name": "Intro"}],
        "tempo": 126.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "is_playing": True,
        "selected_track_index": 0,
        "return_tracks": [],
        "master_track": None,
    }
    parameters = backend.get_device_parameters(0, 0)
    assert parameters["device_name"] == "Drum Buss"
    assert parameters["parameters"][0]["display_value"] == "40%"
    assert backend.get_device_parameter_value_string(0, 0, 2) == {
        "success": True,
        "value_string": "40%",
    }
    assert backend.get_scene_names() == ["Intro"]
    assert backend.get_current_song_time() == 32.5
    assert backend.get_locators_with_status() == ([], False)
    assert backend.get_return_tracks_with_status() == ([], False)
    matrix = backend.device_matrix_report()
    assert matrix["status"] == "connected"
    assert matrix["entries"][0]["device_name"] == "Drum Buss"
    assert matrix["entries"][0]["parameters_available"] is True
    report = backend.capability_report()
    assert report["connected"] is True
    assert report["status"] == "read_only"
    assert report["write"] == []

    with pytest.raises(RuntimeError, match="read-only"):
        backend.set_device_parameter(0, 0, 2, 0.5)
    assert not any(name.startswith("set_") for name, _arguments in calls)


def test_control_deck_backend_fails_closed_on_provider_error() -> None:
    backend = ControlDeckMCPBackend(
        lambda name, arguments: {
            "ok": False,
            "error": {"code": "ABLETON_UNAVAILABLE", "message": "Live is not linked."},
        }
    )
    snapshot = backend.query_session_state()
    assert snapshot["status"] == "offline"
    assert snapshot["backend"] == "ableton-control-deck-mcp"
    assert snapshot["tracks"] == []
    assert snapshot["error"] == "Live is not linked."


def test_live_backend_factory_requires_explicit_mcp_command() -> None:
    sentinel = object()
    assert create_live_backend(lambda: sentinel, environ={}) is sentinel

    with pytest.raises(RuntimeError, match="KENN_LIVE_MCP_COMMAND"):
        create_live_backend(
            lambda: sentinel,
            environ={"KENN_LIVE_BACKEND": "control-deck-mcp"},
        )


def test_live_backend_factory_builds_control_deck_backend_without_starting_process() -> None:
    backend = create_live_backend(
        lambda: object(),
        environ={
            "KENN_LIVE_BACKEND": "control-deck-mcp",
            "KENN_LIVE_MCP_COMMAND": "node /opt/control-deck/dist/src/index.js",
            "KENN_LIVE_MCP_TIMEOUT_SECONDS": "3.5",
        },
    )
    assert isinstance(backend, ControlDeckMCPBackend)
    assert backend._call_tool.command == ("node", "/opt/control-deck/dist/src/index.js")
    assert backend._call_tool.timeout_seconds == 3.5
    backend.close()
