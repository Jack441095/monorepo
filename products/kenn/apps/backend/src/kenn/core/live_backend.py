"""Provider-neutral Live backend contracts and a read-only MCP adapter.

The production backend is still :class:`AbletonOSCClient`.  This module keeps
the future MCP/Extensions provider at a narrow boundary: an MCP tool caller
must return KENN-shaped read results, while every mutation method is
intentionally disabled until that provider has passed the real-Live
qualification suite.
"""

from __future__ import annotations

from typing import Any, Protocol


class LiveBackend(Protocol):
    """The read/write surface consumed by KENN's guarded action service."""

    def query_session_state(self, include_mixer: bool = True) -> dict[str, Any]: ...

    def query_session_topology(self) -> dict[str, Any]: ...

    def query_session_understanding(self) -> dict[str, Any]: ...

    def get_device_parameters(self, track_index: int, device_index: int) -> dict[str, Any]: ...

    def get_device_parameter_value_string(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> dict[str, Any]: ...

    def get_device_parameter_profile(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> dict[str, Any]: ...


class MCPToolCaller(Protocol):
    """Minimal dependency-free seam for an MCP client implementation.

    The real MCP transport can later be supplied by a stdio or Streamable HTTP
    client without importing an MCP SDK into KENN's core safety code.
    """

    def __call__(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class ReadOnlyMCPBackend:
    """Adapt typed MCP read tools to KENN's inspection surface.

    Expected tool names and return shapes are deliberately small and explicit:

    ``live_snapshot``
        Returns a KENN session snapshot, optionally with ``detail=topology``.
    ``live_parameters``
        Returns ``{"success": true, "device_name": ..., "parameters": [...]}``.
    ``live_parameter_display``
        Returns ``{"success": true, "value_string": ...}``.

    The adapter is read-only by construction.  It is not a drop-in production
    backend until an MCP provider implements the complete mutation contract and
    passes KENN's qualification gates.
    """

    backend_name = "mcp-read-only"

    def __init__(self, call_tool: MCPToolCaller):
        self._call_tool = call_tool

    def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._call_tool(tool_name, arguments)
        if not isinstance(result, dict):
            return {"status": "error", "success": False, "error": f"MCP tool '{tool_name}' returned a non-object result."}
        return result

    def query_session_state(self, include_mixer: bool = True) -> dict[str, Any]:
        return self._call("live_snapshot", {"detail": "full" if include_mixer else "topology"})

    def query_session_topology(self) -> dict[str, Any]:
        return self._call("live_snapshot", {"detail": "topology"})

    def query_session_understanding(self) -> dict[str, Any]:
        """Read richer advisory-only context without granting writes."""
        return self._call("live_snapshot", {"detail": "understanding"})

    def get_tracks(self) -> dict[str, Any]:
        snapshot = self.query_session_state(include_mixer=True)
        return {
            "success": snapshot.get("status") == "connected" or snapshot.get("success") is True,
            "tracks": snapshot.get("tracks", []),
            **({"error": snapshot["error"]} if snapshot.get("error") else {}),
        }

    def get_device_parameters(self, track_index: int, device_index: int) -> dict[str, Any]:
        return self._call(
            "live_parameters",
            {"track_index": int(track_index), "device_index": int(device_index)},
        )

    def get_device_parameter_value_string(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> dict[str, Any]:
        return self._call(
            "live_parameter_display",
            {
                "track_index": int(track_index),
                "device_index": int(device_index),
                "parameter_index": int(parameter_index),
            },
        )

    def get_device_parameter_profile(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> dict[str, Any]:
        parameters = self.get_device_parameters(track_index, device_index)
        items = parameters.get("parameters", []) if isinstance(parameters, dict) else []
        parameter = next(
            (
                item for item in items
                if isinstance(item, dict) and int(item.get("index", -1)) == int(parameter_index)
            ),
            None,
        )
        if parameter is None and 0 <= int(parameter_index) < len(items):
            parameter = items[int(parameter_index)]
        if not isinstance(parameter, dict):
            return {"success": False, "error": "Parameter index is not present on the MCP device."}
        display = self.get_device_parameter_value_string(track_index, device_index, parameter_index)
        return {
            "success": bool(parameters.get("success")),
            "device_name": parameters.get("device_name", ""),
            "parameter": parameter,
            "display": display,
            "display_available": bool(display.get("success")),
        }

    def capability_report(self) -> dict[str, Any]:
        return {
            "schema": "kenn.live_backend_capabilities.v1",
            "backend": self.backend_name,
            "transport": "mcp",
            "status": "read_only",
            "connected": True,
            "read": ["live_snapshot", "live_parameters", "live_parameter_display", "live_parameter_profile"],
            "write": [],
            "write_boundary": "disabled_until_real_live_qualification",
        }

    def _write_disabled(self, operation: str) -> None:
        raise RuntimeError(
            f"MCP backend is read-only; '{operation}' is disabled until the provider passes KENN real-Live qualification."
        )

    def set_track_volume(self, track_index: int, volume: float) -> bool:
        self._write_disabled("set_track_volume")

    def set_track_pan(self, track_index: int, pan: float) -> bool:
        self._write_disabled("set_track_pan")

    def set_track_mute(self, track_index: int, muted: bool) -> bool:
        self._write_disabled("set_track_mute")

    def set_track_solo(self, track_index: int, soloed: bool) -> bool:
        self._write_disabled("set_track_solo")

    def set_track_arm(self, track_index: int, armed: bool) -> bool:
        self._write_disabled("set_track_arm")

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        self._write_disabled("set_device_parameter")

    def close(self) -> None:
        return None


__all__ = ["LiveBackend", "MCPToolCaller", "ReadOnlyMCPBackend"]
