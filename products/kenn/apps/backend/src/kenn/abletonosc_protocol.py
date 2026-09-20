"""Small, dependency-free OSC codec used by the KENN AbletonOSC client.

AbletonOSC speaks standard OSC over UDP.  Keeping this codec in KENN avoids
making the companion depend on a second OSC package while matching the wire
format used by the upstream AbletonOSC Remote Script.
"""

from __future__ import annotations

import math
import struct
from typing import Any


class OSCProtocolError(ValueError):
    """Raised when an OSC datagram cannot be decoded safely."""


def _padded(data: bytes) -> bytes:
    return data + (b"\x00" * ((4 - (len(data) % 4)) % 4))


def _read_padded_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        raise OSCProtocolError("OSC string is not NUL terminated")
    try:
        value = data[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OSCProtocolError("OSC string is not valid UTF-8") from exc
    return value, (end + 4) & ~3


def _encode_argument(value: Any) -> tuple[str, bytes]:
    if value is None:
        return "N", b""
    if isinstance(value, bool):
        return ("T", b"") if value else ("F", b"")
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**31) <= value < 2**31:
            raise OSCProtocolError("OSC integer is outside the 32-bit range")
        return "i", struct.pack(">i", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OSCProtocolError("OSC float must be finite")
        return "f", struct.pack(">f", value)
    if isinstance(value, str):
        return "s", _padded(value.encode("utf-8") + b"\x00")
    raise OSCProtocolError(f"Unsupported OSC argument type: {type(value).__name__}")


def encode_message(address: str, args: list[Any] | tuple[Any, ...] = ()) -> bytes:
    """Encode one OSC message with the scalar types used by AbletonOSC."""
    if not isinstance(address, str) or not address.startswith("/"):
        raise OSCProtocolError("OSC address must start with '/'")
    encoded = [_encode_argument(value) for value in args]
    tags = "," + "".join(tag for tag, _ in encoded)
    return _padded(address.encode("utf-8") + b"\x00") + _padded(tags.encode("ascii") + b"\x00") + b"".join(
        payload for _, payload in encoded
    )


def _decode_message(data: bytes) -> tuple[str, list[Any]]:
    address, offset = _read_padded_string(data, 0)
    if not address.startswith("/"):
        raise OSCProtocolError("OSC message has an invalid address")
    tags, offset = _read_padded_string(data, offset)
    if not tags.startswith(","):
        raise OSCProtocolError("OSC message has no type tag string")

    values: list[Any] = []
    for tag in tags[1:]:
        if tag == "i":
            if offset + 4 > len(data):
                raise OSCProtocolError("OSC integer is truncated")
            values.append(struct.unpack(">i", data[offset : offset + 4])[0])
            offset += 4
        elif tag == "f":
            if offset + 4 > len(data):
                raise OSCProtocolError("OSC float is truncated")
            values.append(struct.unpack(">f", data[offset : offset + 4])[0])
            offset += 4
        elif tag == "d":
            if offset + 8 > len(data):
                raise OSCProtocolError("OSC double is truncated")
            values.append(struct.unpack(">d", data[offset : offset + 8])[0])
            offset += 8
        elif tag == "s":
            value, offset = _read_padded_string(data, offset)
            values.append(value)
        elif tag == "T":
            values.append(True)
        elif tag == "F":
            values.append(False)
        elif tag == "N":
            values.append(None)
        else:
            raise OSCProtocolError(f"Unsupported OSC type tag: {tag}")
    return address, values


def decode_packet(data: bytes) -> list[tuple[str, list[Any]]]:
    """Decode an OSC message or bundle into address/argument pairs."""
    if data.startswith(b"#bundle\x00"):
        if len(data) < 16:
            raise OSCProtocolError("OSC bundle is truncated")
        offset = 16  # '#bundle\\0' plus the 8-byte timetag
        messages: list[tuple[str, list[Any]]] = []
        while offset < len(data):
            if offset + 4 > len(data):
                raise OSCProtocolError("OSC bundle element size is truncated")
            size = struct.unpack(">i", data[offset : offset + 4])[0]
            offset += 4
            if size < 0 or offset + size > len(data):
                raise OSCProtocolError("OSC bundle element is truncated")
            messages.extend(decode_packet(data[offset : offset + size]))
            offset += size
        return messages
    return [_decode_message(data)]


__all__ = ["OSCProtocolError", "decode_packet", "encode_message"]
