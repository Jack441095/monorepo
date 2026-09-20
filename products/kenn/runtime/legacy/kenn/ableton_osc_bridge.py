"""Ableton Live 12 Real-Time OSC / UDP Remote Script Bridge.

Provides bidirectional real-time communication between KENN/Thursday and Ableton Live 12.
Supports querying session tracks, volume/pan, device parameters, and triggering remote track adjustments.
"""

from __future__ import annotations

import json
import socket
import logging
import time
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_LIVE_OSC_HOST = "127.0.0.1"
DEFAULT_LIVE_OSC_PORT = 11000  # Default LiveOSC listening port
DEFAULT_RESPONSE_PORT = 11001

class AbletonOSCClient:
    """Client for controlling Ableton Live 12 via OSC / UDP packets."""

    def __init__(self, host: str = DEFAULT_LIVE_OSC_HOST, send_port: int = DEFAULT_LIVE_OSC_PORT, recv_port: int = DEFAULT_RESPONSE_PORT):
        self.host = host
        self.send_port = send_port
        self.recv_port = recv_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(1.0)
        self._next_id = 0

    def send_command(self, address: str, args: Optional[List[Any]] = None) -> Optional[int]:
        """Send a UDP payload packet to Ableton Live. Returns the request id
        used (pass to receive_response to match the correct reply), or None
        if the send itself failed."""
        self._next_id += 1
        request_id = self._next_id
        try:
            payload = json.dumps({"id": request_id, "address": address, "args": args or []}).encode("utf-8")
            self.socket.sendto(payload, (self.host, self.send_port))
            return request_id
        except Exception as exc:
            logger.error("Failed to send OSC command to Ableton Live: %s", exc)
            return None

    def receive_response(self, timeout: float = 1.0, expected_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Receive a UDP response packet from Ableton Live Remote Script.

        If `expected_id` is given, mismatched/stale replies left over from a
        prior command (the remote script always sends one response per
        request, but earlier callers here didn't always read theirs) are
        discarded rather than handed back as if they answered this call --
        found live 2026-08-05: a write's unread reply was being picked up by
        the next, unrelated session-state query, corrupting its track list.
        """
        deadline_budget = timeout
        try:
            while deadline_budget > 0:
                self.socket.settimeout(deadline_budget)
                start = time.monotonic()
                data, _ = self.socket.recvfrom(8192)
                deadline_budget -= (time.monotonic() - start)
                if not data:
                    continue
                parsed = json.loads(data.decode("utf-8"))
                if expected_id is None or parsed.get("id") == expected_id:
                    return parsed
        except (socket.timeout, BlockingIOError):
            pass
        except Exception as exc:
            logger.error("Failed to receive OSC response from Ableton Live: %s", exc)
        return None

    def query_session_state(self) -> Dict[str, Any]:
        """Query active tracks, volume levels, and return tracks from Ableton Live 12."""
        request_id = self.send_command("/live/song/get/track_data")
        if request_id is None:
            return {"status": "offline", "tracks": [], "scenes": []}

        resp = self.receive_response(timeout=0.5, expected_id=request_id)
        if resp and resp.get("ok"):
            data = resp.get("data", {})
            return {
                "status": "connected",
                "host": self.host,
                "port": self.send_port,
                "tracks": data.get("tracks", []),
                "scenes": data.get("scenes", []),
                "tempo": data.get("tempo"),
                "is_playing": data.get("is_playing"),
                "selected_track_index": data.get("selected_track_index"),
                "return_tracks": data.get("return_tracks", []),
                "master_track": data.get("master_track"),
            }

        return {
            "status": "dispatched",
            "host": self.host,
            "port": self.send_port,
            "message": "OSC query dispatched to Ableton Live 12",
            "tracks": [],
            "scenes": [],
        }

    def _send_and_confirm(self, address: str, args: List[Any]) -> bool:
        """Send a command and wait for its own matching reply so no stale
        response is left in the socket for the next caller to misread.
        Returns whether Ableton actually confirmed the change (not just
        whether the UDP packet was sent)."""
        request_id = self.send_command(address, args)
        if request_id is None:
            return False
        resp = self.receive_response(timeout=0.5, expected_id=request_id)
        if resp is None:
            return False
        data = resp.get("data") or {}
        return bool(resp.get("ok")) and bool(data.get("success", True))

    def set_track_volume(self, track_index: int, volume: float) -> bool:
        """Set track volume level (0.0 to 1.0)."""
        clamped_vol = max(0.0, min(1.0, float(volume)))
        return self._send_and_confirm("/live/track/set/volume", [track_index, clamped_vol])

    def set_track_pan(self, track_index: int, pan: float) -> bool:
        """Set track pan level (-1.0 left to 1.0 right)."""
        clamped_pan = max(-1.0, min(1.0, float(pan)))
        return self._send_and_confirm("/live/track/set/pan", [track_index, clamped_pan])

    def set_track_mute(self, track_index: int, muted: bool) -> bool:
        """Mute/unmute a track."""
        return self._send_and_confirm("/live/track/set/mute", [track_index, bool(muted)])

    def set_track_solo(self, track_index: int, soloed: bool) -> bool:
        """Solo/unsolo a track."""
        return self._send_and_confirm("/live/track/set/solo", [track_index, bool(soloed)])

    def set_track_arm(self, track_index: int, armed: bool) -> bool:
        """Record-arm/disarm a track."""
        return self._send_and_confirm("/live/track/set/arm", [track_index, bool(armed)])

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        """Set VST/Audio Effect device parameter value."""
        return self._send_and_confirm("/live/device/set/parameter", [track_index, device_index, parameter_index, value])

    def get_device_parameters(self, track_index: int, device_index: int) -> Dict[str, Any]:
        """List a device's parameters (name/value/min/max), including Rack
        macro knobs -- used to resolve a named macro ("Macro 2") to the
        parameter_index set_device_parameter() needs, since the session
        poll (query_session_state) deliberately doesn't carry full
        per-device parameter lists."""
        request_id = self.send_command("/live/device/get/parameters", [track_index, device_index])
        if request_id is None:
            return {"success": False, "error": "Not connected to Ableton Live"}
        resp = self.receive_response(timeout=0.5, expected_id=request_id)
        if resp is None:
            return {"success": False, "error": "No response from Ableton Live"}
        data = resp.get("data") or {}
        if not resp.get("ok") or not data.get("success", False):
            return {"success": False, "error": data.get("error") or resp.get("error") or "Unknown error"}
        return data

    def load_clip(self, track_index: int, clip_slot_index: int, file_path: str) -> bool:
        """Load an audio file into a clip slot on target track index."""
        return self._send_and_confirm("/live/clip/load", [track_index, clip_slot_index, file_path])

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        """Fire (launch playback of) the clip in a track's clip slot."""
        return self._send_and_confirm("/live/clip/launch", [track_index, clip_slot_index])

    def launch_scene(self, scene_index: int) -> bool:
        """Fire (launch) a scene by index."""
        return self._send_and_confirm("/live/scene/launch", [scene_index])

    def create_scene(self, name: str = "") -> Dict[str, Any]:
        """Append a new scene at the end of the session, optionally named
        (D3.4, docs/KENN_FUTURE_PLAN.md Phase 3). Returns a data dict
        (not a bool) since the caller needs the real assigned
        scene_index back to reference it (e.g. to launch it next)."""
        request_id = self.send_command("/live/scene/create", [name])
        if request_id is None:
            return {"success": False, "error": "Not connected to Ableton Live"}
        resp = self.receive_response(timeout=0.5, expected_id=request_id)
        if resp is None:
            return {"success": False, "error": "No response from Ableton Live"}
        data = resp.get("data") or {}
        if not resp.get("ok") or not data.get("success", False):
            return {"success": False, "error": data.get("error") or resp.get("error") or "Unknown error"}
        return data

    def create_device(self, track_index: int, device_name: str) -> bool:
        """Create/insert a new DAW device on target track index."""
        return self._send_and_confirm("/live/device/create", [track_index, device_name])

    def configure_sidechain(self, bass_track_index: int, kick_track_index: int) -> bool:
        """Configure sidechain routing between a bass track and a kick track."""
        return self._send_and_confirm("/live/device/sidechain", [bass_track_index, kick_track_index])

    def start_playback(self) -> bool:
        """Start song playback from the current position."""
        return self._send_and_confirm("/live/song/transport/play", [])

    def stop_playback(self) -> bool:
        """Stop song playback."""
        return self._send_and_confirm("/live/song/transport/stop", [])

    def set_tempo(self, bpm: float) -> bool:
        """Set song tempo (roughly 20-999 BPM)."""
        clamped_bpm = max(20.0, min(999.0, float(bpm)))
        return self._send_and_confirm("/live/song/transport/set_tempo", [clamped_bpm])


# Singleton client instance
live_client = AbletonOSCClient()
