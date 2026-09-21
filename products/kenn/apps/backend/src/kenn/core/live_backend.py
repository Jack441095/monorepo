"""Provider-neutral Live backend contracts and read-only MCP adapters.

The bundled backend remains :class:`AbletonOSCClient`; operators can instead
select a local MCP provider at startup.  This module keeps that provider at a
narrow boundary: MCP results are translated into KENN's established read
shapes, while every mutation method is intentionally disabled until the
provider has passed the real-Live qualification suite.
"""

from __future__ import annotations

from typing import Any, Protocol


CONTROL_DECK_READ_TOOLS = frozenset(
    {
        "ableton_status",
        "get_live_set",
        "get_track",
        "list_devices",
        "get_device_parameters",
    }
)


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
        close = getattr(self._call_tool, "close", None)
        if callable(close):
            close()


class ControlDeckMCPBackend(ReadOnlyMCPBackend):
    """Translate Ableton Control Deck's read tools into KENN snapshots.

    Control Deck returns MCP tool envelopes shaped as ``{ok, data, error}``
    and uses camel-case arguments.  KENN keeps that provider detail here so
    the guarded action service continues to consume its established snapshot
    contract.  Mutations remain inherited from :class:`ReadOnlyMCPBackend`
    and therefore fail closed.
    """

    backend_name = "ableton-control-deck-mcp"
    host = "stdio"
    port = None
    send_port = None

    def __init__(self, call_tool: MCPToolCaller):
        super().__init__(call_tool)
        self._connection_state = "unknown"

    @property
    def connection_state(self) -> str:
        return self._connection_state

    def _provider_data(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._call_tool(tool_name, arguments)
        except Exception as exc:
            self._connection_state = "offline"
            return {"_error": str(exc)}
        if not isinstance(result, dict):
            self._connection_state = "offline"
            return {"_error": f"MCP tool '{tool_name}' returned a non-object result."}
        if result.get("ok") is not True:
            error = result.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            self._connection_state = "offline" if tool_name == "ableton_status" else self._connection_state
            return {"_error": str(message or f"MCP tool '{tool_name}' failed.")}
        data = result.get("data")
        if data is None:
            return {}
        if not isinstance(data, dict):
            return {"_error": f"MCP tool '{tool_name}' returned non-object data."}
        self._connection_state = "connected"
        return data

    def probe_connection(self) -> dict[str, Any]:
        data = self._provider_data("ableton_status", {})
        connected = bool(data.get("connected")) and "_error" not in data
        self._connection_state = "connected" if connected else "offline"
        return {
            "status": self._connection_state,
            "connected": connected,
            "backend": self.backend_name,
            "transport": "mcp-stdio",
            **({"error": data["_error"]} if data.get("_error") else {}),
        }

    def ping(self, timeout: float = 0.5) -> bool:
        del timeout  # The configured MCP transport owns its bounded timeout.
        return bool(self.probe_connection()["connected"])

    def get_connection_status(self) -> dict[str, Any]:
        return self.probe_connection()

    @staticmethod
    def _offline(error: str) -> dict[str, Any]:
        return {
            "status": "offline",
            "host": "stdio",
            "port": None,
            "backend": ControlDeckMCPBackend.backend_name,
            "tracks": [],
            "scenes": [],
            "error": error,
        }

    def query_session_state(
        self,
        include_mixer: bool = True,
        include_meters: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        del include_meters, force_refresh
        live_set = self._provider_data("get_live_set", {})
        if live_set.get("_error"):
            return self._offline(str(live_set["_error"]))
        raw_tracks = live_set.get("tracks")
        if not isinstance(raw_tracks, list):
            return self._offline("Control Deck returned no track list.")

        tracks: list[dict[str, Any]] = []
        for position, identity in enumerate(raw_tracks):
            if not isinstance(identity, dict):
                return self._offline("Control Deck returned an invalid track identity.")
            try:
                track_index = int(identity.get("index", position))
            except (TypeError, ValueError):
                return self._offline("Control Deck returned an invalid track index.")
            track: dict[str, Any] = {
                "index": track_index,
                "name": str(identity.get("name", "")),
                "devices": [],
            }
            if include_mixer:
                detail = self._provider_data("get_track", {"trackIndex": track_index})
                if detail.get("_error"):
                    return self._offline(str(detail["_error"]))
                track.update(
                    {
                        "name": str(detail.get("name", track["name"])),
                        "volume": detail.get("volume"),
                        "pan": detail.get("pan"),
                        "muted": bool(detail.get("muted", False)),
                        "soloed": bool(detail.get("soloed", False)),
                        "armed": bool(detail.get("armed", False)),
                    }
                )
            devices = self._provider_data("list_devices", {"trackIndex": track_index})
            if devices.get("_error"):
                return self._offline(str(devices["_error"]))
            raw_devices = devices.get("devices", [])
            if not isinstance(raw_devices, list):
                return self._offline(f"Control Deck returned invalid devices for track {track_index}.")
            track["devices"] = [
                {
                    "index": int(item.get("index", device_position)),
                    "name": str(item.get("name", "")),
                    **({"class_name": str(item["className"])} if item.get("className") else {}),
                }
                for device_position, item in enumerate(raw_devices)
                if isinstance(item, dict)
            ]
            tracks.append(track)

        transport = live_set.get("transport") if isinstance(live_set.get("transport"), dict) else {}
        signature = live_set.get("timeSignature") if isinstance(live_set.get("timeSignature"), dict) else {}
        selected = live_set.get("selectedTrack") if isinstance(live_set.get("selectedTrack"), dict) else {}
        scene_data = live_set.get("scenes") if isinstance(live_set.get("scenes"), dict) else {}
        scenes = scene_data.get("scenes", []) if isinstance(scene_data.get("scenes", []), list) else []
        self._connection_state = "connected"
        return {
            "status": "connected",
            "host": self.host,
            "port": self.port,
            "backend": self.backend_name,
            "tracks": tracks,
            "scenes": [
                {"index": int(item.get("index", index)), "name": str(item.get("name", ""))}
                for index, item in enumerate(scenes)
                if isinstance(item, dict)
            ],
            "tempo": transport.get("tempo"),
            "signature_numerator": signature.get("numerator"),
            "signature_denominator": signature.get("denominator"),
            "is_playing": transport.get("isPlaying"),
            "selected_track_index": selected.get("index"),
            "return_tracks": [],
            "master_track": None,
        }

    def query_session_topology(self) -> dict[str, Any]:
        return self.query_session_state(include_mixer=False, force_refresh=True)

    def query_session_understanding(self) -> dict[str, Any]:
        return self.query_session_state(include_mixer=True, force_refresh=True)

    def get_tracks(self) -> dict[str, Any]:
        snapshot = self.query_session_state(include_mixer=True)
        return {
            "success": snapshot.get("status") == "connected",
            "tracks": snapshot.get("tracks", []),
            **({"error": snapshot["error"]} if snapshot.get("error") else {}),
        }

    def get_device_parameters(self, track_index: int, device_index: int) -> dict[str, Any]:
        data = self._provider_data(
            "get_device_parameters",
            {"trackIndex": int(track_index), "deviceIndex": int(device_index)},
        )
        if data.get("_error"):
            return {"success": False, "error": data["_error"], "parameters": []}
        device = data.get("device") if isinstance(data.get("device"), dict) else {}
        raw_parameters = data.get("parameters", [])
        parameters = []
        if isinstance(raw_parameters, list):
            for position, item in enumerate(raw_parameters):
                if not isinstance(item, dict):
                    continue
                parameters.append(
                    {
                        "index": int(item.get("index", position)),
                        "name": str(item.get("name", "")),
                        "value": item.get("value"),
                        "min": item.get("minimum"),
                        "max": item.get("maximum"),
                        "minimum": item.get("minimum"),
                        "maximum": item.get("maximum"),
                        "display_value": str(item.get("displayValue", "")),
                    }
                )
        return {
            "success": True,
            "device_name": str(device.get("name", "")),
            "parameters": parameters,
        }

    def get_device_parameter_value_string(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> dict[str, Any]:
        parameters = self.get_device_parameters(track_index, device_index)
        for item in parameters.get("parameters", []):
            if int(item.get("index", -1)) == int(parameter_index):
                return {"success": True, "value_string": item.get("display_value", "")}
        return {"success": False, "error": "Parameter index is not present on the MCP device."}

    def get_scene_names(self) -> list[str]:
        snapshot = self.query_session_state(include_mixer=True, force_refresh=True)
        if snapshot.get("status") != "connected":
            return []
        return [
            str(item.get("name", ""))
            for item in snapshot.get("scenes", [])
            if isinstance(item, dict)
        ]

    def get_current_song_time(self) -> float | None:
        live_set = self._provider_data("get_live_set", {})
        transport = live_set.get("transport") if isinstance(live_set.get("transport"), dict) else {}
        value = transport.get("songPositionBeats")
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def get_locators_with_status(self) -> tuple[list[dict[str, Any]], bool]:
        # Control Deck does not expose locator enumeration at the pinned
        # provider revision.  Preserve the distinction between empty and
        # unavailable so no caller can infer an empty arrangement.
        return [], False

    def get_return_tracks_with_status(self) -> tuple[list[dict[str, Any]], bool]:
        # Control Deck's current get_live_set contract lists regular tracks
        # only.  Returning unavailable keeps send/return proposals disabled.
        return [], False

    def get_return_tracks(self) -> list[dict[str, Any]]:
        return self.get_return_tracks_with_status()[0]

    def device_matrix_report(self, *, include_parameters: bool = True) -> dict[str, Any]:
        snapshot = self.query_session_state(include_mixer=False, force_refresh=True)
        if snapshot.get("status") != "connected":
            return {
                "schema": "kenn.ableton_device_matrix.v1",
                "status": "offline",
                "connected": False,
                "transport": "mcp-stdio",
                "entries": [],
                **({"error": snapshot["error"]} if snapshot.get("error") else {}),
            }
        entries: list[dict[str, Any]] = []
        for track in snapshot.get("tracks", []):
            if not isinstance(track, dict):
                continue
            for device in track.get("devices", []):
                if not isinstance(device, dict):
                    continue
                entry: dict[str, Any] = {
                    "track_index": track.get("index"),
                    "track_name": track.get("name", ""),
                    "device_index": device.get("index"),
                    "device_name": device.get("name", ""),
                }
                if include_parameters:
                    parameters = self.get_device_parameters(
                        int(track.get("index", -1)), int(device.get("index", -1))
                    )
                    entry["parameters_available"] = bool(parameters.get("success"))
                    entry["parameters"] = parameters.get("parameters", [])
                    if parameters.get("error"):
                        entry["error"] = parameters["error"]
                entries.append(entry)
        return {
            "schema": "kenn.ableton_device_matrix.v1",
            "status": "connected",
            "connected": True,
            "transport": "mcp-stdio",
            "entries": entries,
            "write_boundary": {
                "report_is_read_only": True,
                "writes_still_require": [
                    "exact identity",
                    "confirmation",
                    "stale check",
                    "readback",
                    "receipt",
                ],
            },
        }

    def capability_report(self) -> dict[str, Any]:
        connection = self.probe_connection()
        return {
            "schema": "kenn.live_backend_capabilities.v1",
            "backend": self.backend_name,
            "provider": "ableton-control-deck",
            "transport": "mcp-stdio",
            "status": "read_only" if connection["connected"] else "offline",
            "connected": connection["connected"],
            "read": sorted(CONTROL_DECK_READ_TOOLS),
            "write": [],
            "write_boundary": "disabled_until_real_live_qualification",
            **({"error": connection["error"]} if connection.get("error") else {}),
        }


__all__ = [
    "CONTROL_DECK_READ_TOOLS",
    "ControlDeckMCPBackend",
    "LiveBackend",
    "MCPToolCaller",
    "ReadOnlyMCPBackend",
]
