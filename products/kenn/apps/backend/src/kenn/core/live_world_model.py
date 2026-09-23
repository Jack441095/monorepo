"""One read-only, evidence-only picture of the open Live set.

Built from the client's existing reads plus the KENN world-model endpoints
(return and master mixers, device trees with rack chains). A section Live did
not answer is marked unavailable and left absent; nothing is inferred. The
fingerprint changes whenever any structural or mixer value changes, so later
proposals can be bound to the exact model they were planned against.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

WORLD_MODEL_SCHEMA = "kenn.live_world_model.v1"
_VOLATILE_KEYS = {"output_meter_level", "output_meter_left", "output_meter_right", "current_song_time",
                  "playing_position", "latency", "read_at"}


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def fingerprint(model: dict[str, Any]) -> str:
    body = {k: v for k, v in model.items() if k not in {"fingerprint", "availability"}}
    canonical = json.dumps(_strip_volatile(body), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _call(client: Any, name: str, *args: Any) -> dict[str, Any]:
    method = getattr(client, name, None)
    if not callable(method):
        return {"success": False, "error": f"backend has no {name}"}
    try:
        result = method(*args)
    except Exception as exc:  # a read failure marks the section unavailable, never the whole model
        return {"success": False, "error": str(exc)}
    return result if isinstance(result, dict) else {"success": False, "error": "unexpected response"}


def read_world_model(client: Any) -> dict[str, Any]:
    reader = getattr(client, "query_session_understanding", None) or client.query_session_state
    state = reader()
    # An older Remote Script never answers the KENN reads; each would wait for
    # the reply timeout. Probe once and skip the rest if it stays silent.
    supported = {"kenn_reads": True}

    def kenn_read(name: str, *args: Any) -> dict[str, Any]:
        if not supported["kenn_reads"]:
            return {"success": False, "error": "skipped: Remote Script lacks KENN reads"}
        result = _call(client, name, *args)
        if not result.get("success") and "does not answer" in str(result.get("error", "")):
            supported["kenn_reads"] = False
        return result

    if state.get("status") != "connected":
        return {"schema": WORLD_MODEL_SCHEMA, "status": state.get("status", "offline"),
                "error": state.get("error", "Live is not connected.")}

    availability: dict[str, bool] = {}
    tracks = [dict(t) for t in state.get("tracks", []) if isinstance(t, dict)]
    device_trees_ok = True
    for track in tracks:
        tree = kenn_read("get_device_tree", "track", int(track["index"]))
        if tree.get("success"):
            track["device_tree"] = tree.get("devices", [])
        else:
            device_trees_ok = False

    returns: list[dict[str, Any]] = []
    return_mixers_ok = True
    for item in state.get("return_tracks") or []:
        entry = {"index": item.get("index"), "name": item.get("name"),
                 "devices": [d.get("name") if isinstance(d, dict) else d for d in item.get("devices") or []]}
        mixer = kenn_read("get_bus_mixer", "return", int(item.get("index", -1)))
        if mixer.get("success"):
            entry.update({k: mixer[k] for k in ("volume", "panning", "mute", "solo") if k in mixer})
        else:
            return_mixers_ok = False
        tree = kenn_read("get_device_tree", "return", int(item.get("index", -1)))
        if tree.get("success"):
            entry["device_tree"] = tree.get("devices", [])
        returns.append(entry)

    master: dict[str, Any] | None = None
    master_mixer = kenn_read("get_bus_mixer", "master", -1)
    if master_mixer.get("success"):
        master = {k: master_mixer[k] for k in ("name", "volume", "panning", "devices") if k in master_mixer}
        tree = kenn_read("get_device_tree", "master", -1)
        if tree.get("success"):
            master["device_tree"] = tree.get("devices", [])

    capabilities = state.get("understanding_capabilities") if isinstance(state.get("understanding_capabilities"), dict) else {}
    availability.update({key: bool(value) for key, value in capabilities.items()})
    availability.update({
        "device_trees": device_trees_ok and bool(tracks),
        "return_mixers": return_mixers_ok and bool(returns),
        "master": master is not None,
        "kenn_reads": supported["kenn_reads"],
    })

    selection: dict[str, Any] = {"track_index": state.get("selected_track_index")}
    if isinstance(state.get("selected_track_kind"), dict):
        selection["track_kind"] = state["selected_track_kind"]
    for key in ("selected_device_track_index", "selected_device_index", "selected_device_name", "selected_scene_index"):
        if key in state:
            selection[key.removeprefix("selected_")] = state[key]

    model = {
        "schema": WORLD_MODEL_SCHEMA,
        "status": "connected",
        "backend": state.get("backend", "abletonosc"),
        "song": {k: state.get(k) for k in ("tempo", "signature_numerator", "signature_denominator",
                                           "root_note", "scale_name", "is_playing")},
        "tracks": tracks,
        "returns": returns,
        "master": master,
        "scenes": state.get("scenes", []),
        "locators": state.get("locators", []),
        "selection": selection,
        "availability": availability,
    }
    model["fingerprint"] = fingerprint(model)
    return model


__all__ = ["WORLD_MODEL_SCHEMA", "fingerprint", "read_world_model"]
