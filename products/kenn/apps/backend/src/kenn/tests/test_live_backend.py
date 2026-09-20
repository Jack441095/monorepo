from __future__ import annotations

import pytest

from kenn.core.live_backend import ReadOnlyMCPBackend
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
