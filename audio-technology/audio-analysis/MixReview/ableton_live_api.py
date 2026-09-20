"""Ableton Live OSC client bridge for applying mix repairs."""

from __future__ import annotations

import socket
import struct
import logging

logger = logging.getLogger("ableton_live_api")


class AbletonOSCClient:
    """A zero-dependency OSC client to communicate with AbletonOSC Remote Script."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _encode_message(self, address: str, args: list) -> bytes:
        # Encode address
        addr_bytes = address.encode("utf-8")
        addr_padded = addr_bytes + b"\x00" * (4 - (len(addr_bytes) % 4))
        if len(addr_bytes) % 4 == 0:
            addr_padded = addr_bytes + b"\x00" * 4

        # Build type tags and arguments
        tags = ","
        arg_bytes = b""
        for arg in args:
            if isinstance(arg, int):
                tags += "i"
                arg_bytes += struct.pack(">i", arg)
            elif isinstance(arg, float):
                tags += "f"
                arg_bytes += struct.pack(">f", arg)
            elif isinstance(arg, str):
                tags += "s"
                str_bytes = arg.encode("utf-8")
                str_padded = str_bytes + b"\x00" * (4 - (len(str_bytes) % 4))
                if len(str_bytes) % 4 == 0:
                    str_padded = str_bytes + b"\x00" * 4
                arg_bytes += str_padded
            else:
                raise TypeError(f"Unsupported OSC argument type: {type(arg)}")

        tags_bytes = tags.encode("utf-8")
        tags_padded = tags_bytes + b"\x00" * (4 - (len(tags_bytes) % 4))
        if len(tags_bytes) % 4 == 0:
            tags_padded = tags_bytes + b"\x00" * 4

        return addr_padded + tags_padded + arg_bytes

    def send(self, address: str, *args) -> None:
        """Send an OSC message to Ableton Live."""
        try:
            packet = self._encode_message(address, list(args))
            self.sock.sendto(packet, (self.host, self.port))
        except Exception as e:
            logger.error(f"Failed to send OSC message to {self.host}:{self.port} - {e}")

    def set_parameter(self, track_idx: int, device_idx: int, param_idx: int, value: float) -> None:
        """Set a parameter value for a device on a track in Ableton Live."""
        self.send("/live/device/set/parameter/value", track_idx, device_idx, param_idx, value)

    def apply_repair_chain(self, repair_chain: dict) -> bool:
        """Apply a repair chain to Ableton Live tracks and devices."""
        try:
            track = repair_chain.get("track", 0)
            device = repair_chain.get("device", 0)

            # Map track ID
            if isinstance(track, str) and track.lower() == "master":
                track_idx = -1
            else:
                try:
                    track_idx = int(track)
                except ValueError:
                    track_idx = 0

            device_idx = int(device)

            for param in repair_chain.get("params", []):
                # Accepts "parameter" or "param" keys
                param_idx = int(param.get("parameter") or param.get("param") or 0)
                val = float(param.get("value", 0.0))
                self.set_parameter(track_idx, device_idx, param_idx, val)
            return True
        except Exception as e:
            logger.error(f"Error applying repair chain to Ableton: {e}")
            return False
