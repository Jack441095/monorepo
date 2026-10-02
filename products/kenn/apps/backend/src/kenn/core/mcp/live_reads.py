"""Exact read-only Live reads: clip slots, devices, parameters, and the read-only inventories.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def live_midi_clip(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    clip_slot_index = facade._index(args, "clip_slot_index")
    return facade.client.get(
        "/api/ableton/osc/midi-clip",
        {"track_index": track_index, "clip_slot_index": clip_slot_index},
    )


def live_clip_slot(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    clip_slot_index = facade._index(args, "clip_slot_index")
    return facade.client.get(
        "/api/ableton/osc/clip-slot",
        {"track_index": track_index, "clip_slot_index": clip_slot_index},
    )


def live_devices(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    snapshot = facade.client.get("/api/ableton/osc/session", {"detail": "topology"})
    tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
    track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
    if track is None:
        raise ValueError(f"track_index {track_index} is not present in the current Live snapshot")
    return {
        "status": snapshot.get("status"),
        "track_index": track_index,
        "track_name": track.get("name", ""),
        "devices": track.get("devices", []),
    }


def live_parameters(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    device_index = facade._index(args, "device_index")
    return facade.client.get("/api/ableton/osc/device-parameters", {"track_index": track_index, "device_index": device_index})


def live_parameter_display(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    device_index = facade._index(args, "device_index")
    parameter_index = facade._index(args, "parameter_index")
    return facade.client.get(
        "/api/ableton/osc/device-parameter-value-string",
        {"track_index": track_index, "device_index": device_index, "parameter_index": parameter_index},
    )


def live_parameter_profile(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    track_index = facade._index(args, "track_index")
    device_index = facade._index(args, "device_index")
    parameter_index = facade._index(args, "parameter_index")
    info = facade.client.get(
        "/api/ableton/osc/device-parameters",
        {"track_index": track_index, "device_index": device_index},
    )
    parameters = info.get("parameters", []) if isinstance(info, dict) else []
    parameter = next(
        (
            item for item in parameters
            if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index
        ),
        None,
    )
    if parameter is None and 0 <= parameter_index < len(parameters):
        parameter = parameters[parameter_index]
    if not isinstance(parameter, dict):
        raise ValueError(f"parameter_index {parameter_index} is not present on the current Live device")
    display = facade.client.get(
        "/api/ableton/osc/device-parameter-value-string",
        {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
        },
    )
    return {
        "success": bool(info.get("success")) if isinstance(info, dict) else False,
        "track_index": track_index,
        "device_index": device_index,
        "device_name": info.get("device_name", "") if isinstance(info, dict) else "",
        "parameter": parameter,
        "display": display,
        "display_available": bool(isinstance(display, dict) and display.get("success")),
    }


def compare_live_devices(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    coordinates = {
        "left": (facade._index(args, "left_track_index"), facade._index(args, "left_device_index")),
        "right": (facade._index(args, "right_track_index"), facade._index(args, "right_device_index")),
    }
    snapshot = facade.client.get("/api/ableton/osc/session", {"detail": "topology"})
    if not isinstance(snapshot, dict) or snapshot.get("status") != "connected":
        return {
            "ok": False,
            "schema": "kenn.live_device_comparison.v1",
            "status": "offline",
            "error": "The current Live topology is not connected; device comparison is unavailable.",
            "read_only": True,
            "mutation_authorized": False,
        }

    def exact_identity(track_index: int, device_index: int) -> dict[str, Any]:
        tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
        track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
        if track is None:
            raise ValueError(f"track_index {track_index} is not present in the current Live snapshot")
        devices = [item for item in track.get("devices", []) if isinstance(item, dict)]
        device = next((item for item in devices if int(item.get("index", -1)) == device_index), None)
        if device is None:
            raise ValueError(f"device_index {device_index} is not present on track_index {track_index}")
        return {
            "track_index": track_index,
            "track_name": str(track.get("name", ""))[:128],
            "device_index": device_index,
            "device_name": str(device.get("name", ""))[:128],
        }

    identities = {side: exact_identity(*pair) for side, pair in coordinates.items()}
    parameter_sets: dict[str, dict[str, Any]] = {}
    for side, identity in identities.items():
        info = facade.client.get(
            "/api/ableton/osc/device-parameters",
            {"track_index": identity["track_index"], "device_index": identity["device_index"]},
        )
        if not isinstance(info, dict) or info.get("success") is not True:
            raise ValueError(f"Could not read parameters for the {side} device")
        if str(info.get("device_name", "")) != identity["device_name"]:
            raise ValueError(f"The {side} device identity changed during comparison")
        parameter_sets[side] = info

    def keyed_parameters(values: Any) -> dict[tuple[str, int], dict[str, Any]]:
        seen: dict[str, int] = {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            parameter_name = str(item.get("name", "")).strip()
            if not parameter_name:
                continue
            normalized = parameter_name.casefold()
            occurrence = seen.get(normalized, 0)
            seen[normalized] = occurrence + 1
            result[(normalized, occurrence)] = item
        return result

    left_parameters = keyed_parameters(parameter_sets["left"].get("parameters"))
    right_parameters = keyed_parameters(parameter_sets["right"].get("parameters"))
    rows: list[dict[str, Any]] = []
    keys = list(left_parameters) + [key for key in right_parameters if key not in left_parameters]
    for key in keys:
        left = left_parameters.get(key)
        right = right_parameters.get(key)
        row: dict[str, Any] = {
            "name": (left or right).get("name", ""),
            "matched": left is not None and right is not None,
        }
        if left is not None:
            row["left"] = {field: left[field] for field in ("index", "value", "min", "max", "quantized") if field in left}
        if right is not None:
            row["right"] = {field: right[field] for field in ("index", "value", "min", "max", "quantized") if field in right}
        left_value = left.get("value") if left else None
        right_value = right.get("value") if right else None
        if (
            isinstance(left_value, (int, float)) and not isinstance(left_value, bool)
            and math.isfinite(float(left_value))
            and isinstance(right_value, (int, float)) and not isinstance(right_value, bool)
            and math.isfinite(float(right_value))
        ):
            row["delta_right_minus_left"] = round(float(right_value) - float(left_value), 6)
        rows.append(row)
    differing = sum(
        1 for row in rows
        if row.get("matched") is True and row.get("delta_right_minus_left") not in (None, 0.0)
    )
    return {
        "ok": True,
        "schema": "kenn.live_device_comparison.v1",
        "status": "complete",
        "left": identities["left"],
        "right": identities["right"],
        "matched_parameter_count": sum(1 for row in rows if row.get("matched") is True),
        "differing_parameter_count": differing,
        "parameters": rows[:128],
        "comparison_basis": "Matched parameter names and current raw Live values; display units may differ and are not inferred here.",
        "limitations": [
            "This reports current parameter metadata and raw values, not an audible preference or sonic quality verdict.",
            "Unmatched parameters are shown separately; KENN does not invent equivalence between different controls.",
            "A comparison never authorizes a Live write; any change requires a separate exact proposal, confirmation, stale check, and readback.",
        ],
        "read_only": True,
        "mutation_authorized": False,
    }


def kenn_capabilities(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    return facade.client.get("/api/ableton/capabilities")


def live_device_matrix(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    include_parameters = args.get("include_parameters", True)
    if not isinstance(include_parameters, bool):
        raise ValueError("include_parameters must be boolean")
    return facade.client.get(
        "/api/ableton/device-matrix",
        {"parameters": "1" if include_parameters else "0"},
    )
