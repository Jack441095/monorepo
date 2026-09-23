"""Stateful fake Live backend replaying a recorded session fixture.

Selected only by ``KENN_LIVE_BACKEND=fake`` for Live-free tests and CI. It is
never a fallback: every snapshot says ``backend: "fake"`` so nothing produced
against it can pass for real-Live evidence. Fixtures are recorded from real
Live by ``tooling/scripts/record_fake_live_fixture.py``.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from kenn.core.device_units import raw_to_display

FIXTURE_ENV = "KENN_FAKE_LIVE_FIXTURE"
DEFAULT_FIXTURE = Path(__file__).with_name("fake_live_fixtures") / "investor_demo.json"
_NUMBER_WITH_UNIT = re.compile(r"^\s*(-?\d+(?:\.(\d+))?)\s*(.*)$")


def _display(parameter: dict[str, Any], device_name: str) -> str:
    """Approximate Live's display string for a raw value from recorded formats."""
    value = float(parameter["value"])
    recorded = parameter.get("recorded_display")
    recorded_value = parameter.get("recorded_value")
    if recorded is not None and recorded_value is not None and abs(value - float(recorded_value)) < 1e-9:
        return str(recorded)
    if parameter.get("quantized") and recorded in {"On", "Off"}:
        return "On" if value >= 0.5 else "Off"
    match = _NUMBER_WITH_UNIT.match(str(recorded or ""))
    unit = match.group(3).strip() if match else ""
    decimals = len(match.group(2) or "") if match else 2
    if match and recorded_value is not None and abs(float(match.group(1)) - float(recorded_value)) < 1e-6:
        return f"{value:.{decimals}f} {unit}".strip()
    for profile_unit in ("db", "hz", "%", "ms", "ratio", "dB"):
        shown, error = raw_to_display(
            device_name=device_name, parameter_name=str(parameter["name"]), raw=value, unit=profile_unit
        )
        if error is None and shown is not None:
            return f"{float(shown):.{decimals}f} {unit}".strip()
    return f"{value:.2f}"


class FakeLiveBackend:
    """In-memory Live double covering the investor-demo command surface."""

    backend_name = "fake"

    def __init__(self, fixture_path: Path | str | None = None) -> None:
        path = Path(fixture_path or os.environ.get(FIXTURE_ENV) or DEFAULT_FIXTURE)
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture.get("schema") != "kenn.fake_live_fixture.v1":
            raise RuntimeError(f"Unsupported fake Live fixture: {path}")
        self.fixture_path = path
        self._lock = threading.RLock()
        self._session = copy.deepcopy(fixture["session"])
        self._session.update({"status": "connected", "backend": "fake", "host": "fake", "port": 0})
        self._returns = copy.deepcopy(fixture.get("return_tracks") or [])
        self._devices: dict[tuple[int, int], dict[str, Any]] = {}
        for key, info in (fixture.get("devices") or {}).items():
            track_index, device_index = (int(part) for part in key.split(":"))
            self._devices[(track_index, device_index)] = self._with_recorded_displays(info)
        self._templates = {info["device_name"]: copy.deepcopy(info) for info in self._devices.values()}
        self._sends = {
            (int(track), send): float(value or 0.0)
            for track, values in (fixture.get("sends") or {}).items()
            for send, value in enumerate(values)
        }
        self._selected_device = dict(fixture.get("selected_device") or {"track_index": 0, "device_index": 0})
        self.writes: list[tuple[Any, ...]] = []

    @staticmethod
    def _with_recorded_displays(info: dict[str, Any]) -> dict[str, Any]:
        info = copy.deepcopy(info)
        for parameter in info.get("parameters", []):
            parameter["recorded_value"] = parameter.get("value")
            parameter["recorded_display"] = parameter.pop("value_display", None)
        return info

    def _track(self, index: int) -> dict[str, Any] | None:
        tracks = self._session.get("tracks", [])
        return tracks[index] if 0 <= int(index) < len(tracks) else None

    def _reindex_devices(self, track_index: int) -> None:
        track = self._track(track_index)
        if track is None:
            return
        entries = sorted((d, info) for (t, d), info in self._devices.items() if t == track_index)
        for d, _info in entries:
            del self._devices[(track_index, d)]
        for new_index, (_d, info) in enumerate(entries):
            self._devices[(track_index, new_index)] = info
        track["devices"] = [{"index": i, "name": info["device_name"]} for i, (_d, info) in enumerate(entries)]

    # --- reads -------------------------------------------------------------

    def probe_connection(self) -> dict[str, Any]:
        with self._lock:
            names = [str(t.get("name")) for t in self._session.get("tracks", [])]
            return {"status": "connected", "host": "fake", "port": 0, "backend": "fake",
                    "track_count": len(names), "track_names": names}

    def query_session_state(self, *, include_mixer: bool = True, include_meters: bool = False,
                            force_refresh: bool = False, **_kwargs: Any) -> dict[str, Any]:
        with self._lock:
            state = copy.deepcopy(self._session)
            state["return_tracks"] = copy.deepcopy(self._returns)
            return state

    def ping(self, *, timeout: float = 0.5) -> bool:
        return True

    @property
    def connection_state(self) -> str:
        return "connected"

    @property
    def is_connected(self) -> bool:
        return True

    def get_connection_status(self) -> dict[str, Any]:
        return {"state": "connected", "host": "fake", "port": 0, "recv_port": 0, "backend": "fake",
                "last_successful_heartbeat": None, "missed_heartbeats": 0, "circuit_breaker_enabled": False,
                "last_exchange": None}

    def capability_report(self) -> dict[str, Any]:
        from kenn.ableton_osc_bridge import CAPABILITY_SCHEMA, READ_ENDPOINTS, WRITE_ENDPOINTS

        probe = self.probe_connection()
        return {
            "schema": CAPABILITY_SCHEMA,
            "transport": "fake",
            "protocol": "fake",
            "host": "fake",
            "send_port": 0,
            "response_port": 0,
            "status": "connected",
            "connected": True,
            "track_count": probe["track_count"],
            "track_names": probe["track_names"],
            "endpoints": {"read": list(READ_ENDPOINTS), "write": list(WRITE_ENDPOINTS)},
            "write_boundary": {
                "confirmation_required": True,
                "service": "LiveActionService",
                "readback_required": True,
                "replay_rejection": True,
            },
        }

    def query_session_topology(self) -> dict[str, Any]:
        return self.query_session_state(include_mixer=False)

    def query_session_understanding(self) -> dict[str, Any]:
        state = self.query_session_state(include_meters=True)
        state["return_tracks"] = [
            {"index": item["index"], "name": item["name"],
             "devices": [{"index": i, "name": name} for i, name in enumerate(item.get("devices") or [])]}
            for item in self.get_return_tracks()
        ]
        return state

    def get_return_tracks(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._returns)

    def get_return_tracks_with_status(self) -> tuple[list[dict[str, Any]], bool]:
        return self.get_return_tracks(), True

    def get_selected_device(self) -> dict[str, Any]:
        with self._lock:
            return {"success": True, **self._selected_device}

    def get_track_send(self, track_index: int, send_index: int) -> float | None:
        with self._lock:
            return self._sends.get((int(track_index), int(send_index)))

    def get_device_parameters(self, track_index: int, device_index: int) -> dict[str, Any]:
        with self._lock:
            info = self._devices.get((int(track_index), int(device_index)))
            if info is None:
                return {"success": False, "error": "No complete response from AbletonOSC for that device."}
            parameters = [
                {k: v for k, v in p.items() if k not in {"recorded_value", "recorded_display"}}
                for p in info["parameters"]
            ]
            return {"success": True, "device_name": info["device_name"], "parameters": copy.deepcopy(parameters)}

    def get_device_parameter(self, track_index: int, device_index: int, parameter_index: int) -> dict[str, Any]:
        info = self.get_device_parameters(track_index, device_index)
        if not info.get("success"):
            return info
        parameters = info["parameters"]
        if not 0 <= int(parameter_index) < len(parameters):
            return {"success": False, "error": "Parameter index out of range"}
        return {"success": True, "device_name": info["device_name"], "parameter": parameters[int(parameter_index)]}

    def get_device_parameter_value_string(self, track_index: int, device_index: int,
                                          parameter_index: int) -> dict[str, Any]:
        with self._lock:
            info = self._devices.get((int(track_index), int(device_index)))
            if info is None or not 0 <= int(parameter_index) < len(info["parameters"]):
                return {"success": False, "error": "No value-string response from AbletonOSC."}
            parameter = info["parameters"][int(parameter_index)]
            return {"success": True, "track_index": int(track_index), "device_index": int(device_index),
                    "parameter_index": int(parameter_index), "value_string": _display(parameter, info["device_name"])}

    def get_current_song_time(self) -> float:
        return 0.0

    def get_scene_names(self) -> list[str]:
        with self._lock:
            return [str(s.get("name", "")) for s in self._session.get("scenes", [])]

    def get_track_has_midi_input(self, index: int) -> bool | None:
        track = self._track(index)
        return None if track is None else bool(track.get("has_midi_input", False))

    # --- writes ------------------------------------------------------------

    def _set_track_field(self, index: int, field: str, value: Any, label: str) -> bool:
        with self._lock:
            track = self._track(index)
            if track is None:
                return False
            track[field] = value
            self.writes.append((label, int(index), value))
            return True

    def set_track_volume(self, index: int, value: float) -> bool:
        return self._set_track_field(index, "volume", float(value), "volume")

    def set_track_pan(self, index: int, value: float) -> bool:
        return self._set_track_field(index, "pan", float(value), "pan")

    def set_track_mute(self, index: int, value: bool) -> bool:
        return self._set_track_field(index, "muted", bool(value), "mute")

    def set_track_solo(self, index: int, value: bool) -> bool:
        return self._set_track_field(index, "soloed", bool(value), "solo")

    def set_track_arm(self, index: int, value: bool) -> bool:
        return self._set_track_field(index, "armed", bool(value), "arm")

    def set_track_name(self, index: int, value: str) -> bool:
        return self._set_track_field(index, "name", str(value), "name")

    def set_track_send(self, track_index: int, send_index: int, value: float) -> bool:
        with self._lock:
            if self._track(track_index) is None or not 0 <= int(send_index) < len(self._returns):
                return False
            self._sends[(int(track_index), int(send_index))] = float(value)
            self.writes.append(("send", int(track_index), int(send_index), float(value)))
            return True

    def set_selected_track(self, index: int) -> bool:
        with self._lock:
            if self._track(index) is None:
                return False
            self._session["selected_track_index"] = int(index)
            self.writes.append(("focus", int(index)))
            return True

    def set_selected_device(self, track_index: int, device_index: int) -> bool:
        with self._lock:
            if (int(track_index), int(device_index)) not in self._devices:
                return False
            self._selected_device = {"track_index": int(track_index), "device_index": int(device_index)}
            self._session["selected_track_index"] = int(track_index)
            self.writes.append(("focus_device", int(track_index), int(device_index)))
            return True

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        with self._lock:
            info = self._devices.get((int(track_index), int(device_index)))
            if info is None or not 0 <= int(parameter_index) < len(info["parameters"]):
                return False
            parameter = info["parameters"][int(parameter_index)]
            clamped = min(float(parameter["max"]), max(float(parameter["min"]), float(value)))
            parameter["value"] = clamped
            self.writes.append(("device_parameter", int(track_index), int(device_index), int(parameter_index), clamped))
            return True

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> dict[str, Any]:
        with self._lock:
            track = self._track(track_index)
            template = self._templates.get(str(device_name))
            if track is None or template is None:
                return {"success": False, "error": f"The fake Live fixture has no '{device_name}' template."}
            existing = sorted(d for (t, d) in self._devices if t == int(track_index))
            position = len(existing) if int(insertion_index) < 0 else min(int(insertion_index), len(existing))
            for d in reversed(existing):
                if d >= position:
                    self._devices[(int(track_index), d + 1)] = self._devices.pop((int(track_index), d))
            fresh = copy.deepcopy(template)
            for parameter in fresh["parameters"]:
                parameter["value"] = parameter["recorded_value"]
            self._devices[(int(track_index), position)] = fresh
            self._reindex_devices(int(track_index))
            self.writes.append(("insert_device", int(track_index), position, str(device_name)))
            return {"success": True, "track_index": int(track_index), "device_index": position,
                    "device_name": str(device_name)}

    def remove_device_with_result(self, track_index: int, device_index: int, device_name: str) -> dict[str, Any]:
        with self._lock:
            info = self._devices.get((int(track_index), int(device_index)))
            if info is None or info["device_name"] != str(device_name):
                return {"success": False, "error": "Device identity did not match; nothing removed."}
            del self._devices[(int(track_index), int(device_index))]
            self._reindex_devices(int(track_index))
            self.writes.append(("remove_device", int(track_index), int(device_index), str(device_name)))
            return {"success": True, "track_index": int(track_index), "device_index": int(device_index),
                    "device_name": str(device_name)}

    def start_playback(self) -> bool:
        with self._lock:
            self._session["is_playing"] = True
            return True

    def stop_playback(self) -> bool:
        with self._lock:
            self._session["is_playing"] = False
            return True


__all__ = ["DEFAULT_FIXTURE", "FIXTURE_ENV", "FakeLiveBackend"]
