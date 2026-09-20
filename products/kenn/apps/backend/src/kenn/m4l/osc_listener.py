"""Ableton Live 12 OSC State Listener for KENN.

Listens for incoming UDP OSC feedback messages from AbletonOSC Remote Script
and updates KENN's active session state cache in real time.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("kenn.osc_listener")


class AbletonOSCListener:
    """UDP listener for Ableton Live OSC feedback messages."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9001):
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.state_cache: dict[str, Any] = {
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
            "tracks": {},
            "master_volume": 0.0,
            "last_updated": 0.0,
        }
        self.callbacks: list[Callable[[str, list[Any]], None]] = []

    def start(self) -> None:
        """Start listening for incoming OSC packets on a background thread."""
        if self._running:
            return
        self._running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.settimeout(0.5)

        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info(f"Ableton OSC Listener started on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stop the background listener thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        logger.info("Ableton OSC Listener stopped")

    def register_callback(self, callback: Callable[[str, list[Any]], None]) -> None:
        """Register a callback for raw OSC events."""
        self.callbacks.append(callback)

    def _listen_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._socket.recvfrom(4096)
                if data:
                    addr, args = self._parse_osc_packet(data)
                    self._update_state(addr, args)
                    for cb in self.callbacks:
                        try:
                            cb(addr, args)
                        except Exception as e:
                            logger.error(f"Error in OSC callback: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"OSC receive error: {e}")

    def _parse_osc_packet(self, data: bytes) -> tuple[str, list[Any]]:
        """Parse raw OSC byte buffer into address string and argument list."""
        try:
            # Address pattern
            null_idx = data.find(b"\x00")
            if null_idx == -1:
                return ("", [])
            address = data[:null_idx].decode("utf-8")

            # Pad to 4 bytes boundary
            offset = (null_idx + 4) & ~3

            if offset >= len(data):
                return (address, [])

            # Type tag string
            tag_null_idx = data.find(b"\x00", offset)
            if tag_null_idx == -1:
                return (address, [])

            tags = data[offset:tag_null_idx].decode("utf-8")
            offset = (tag_null_idx + 4) & ~3

            args = []
            if tags.startswith(","):
                for tag in tags[1:]:
                    if tag == "f":
                        if offset + 4 <= len(data):
                            val = struct.unpack(">f", data[offset:offset+4])[0]
                            args.append(val)
                            offset += 4
                    elif tag == "i":
                        if offset + 4 <= len(data):
                            val = struct.unpack(">i", data[offset:offset+4])[0]
                            args.append(val)
                            offset += 4
                    elif tag == "s":
                        str_null = data.find(b"\x00", offset)
                        if str_null != -1:
                            val = data[offset:str_null].decode("utf-8", errors="ignore")
                            args.append(val)
                            offset = (str_null + 4) & ~3

            return (address, args)
        except Exception:
            return ("", [])

    def _update_state(self, address: str, args: list[Any]) -> None:
        """Update internal state cache based on OSC address routing."""
        self.state_cache["last_updated"] = time.time()

        if address == "/live/song/get/tempo" and args:
            self.state_cache["tempo"] = float(args[0])
        elif address == "/live/track/get/volume" and len(args) >= 2:
            track_idx, vol = int(args[0]), float(args[1])
            tracks = self.state_cache["tracks"]
            if track_idx not in tracks:
                tracks[track_idx] = {}
            tracks[track_idx]["volume"] = vol
        elif address == "/live/track/get/name" and len(args) >= 2:
            track_idx, name = int(args[0]), str(args[1])
            tracks = self.state_cache["tracks"]
            if track_idx not in tracks:
                tracks[track_idx] = {}
            tracks[track_idx]["name"] = name
