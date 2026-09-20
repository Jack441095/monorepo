"""Unit tests for Ableton Live OSC Listener."""

import socket
import struct
import time
from kenn.m4l.osc_listener import AbletonOSCListener


def test_osc_packet_parsing():
    listener = AbletonOSCListener()

    # Encode test packet for /live/song/get/tempo [128.0]
    address = b"/live/song/get/tempo\x00\x00\x00\x00"
    tags = b",f\x00\x00"
    val = struct.pack(">f", 128.0)
    packet = address + tags + val

    addr, args = listener._parse_osc_packet(packet)
    assert addr == "/live/song/get/tempo"
    assert len(args) == 1
    assert abs(args[0] - 128.0) < 0.01


def test_osc_listener_state_update():
    listener = AbletonOSCListener(port=9998)
    listener.start()

    # Send UDP test packet to listener
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    address = b"/live/track/get/volume\x00\x00"
    tags = b",if\x00"
    track_idx = struct.pack(">i", 2)
    volume = struct.pack(">f", -6.0)
    packet = address + tags + track_idx + volume

    sock.sendto(packet, ("127.0.0.1", 9998))
    time.sleep(0.1)

    listener.stop()

    assert 2 in listener.state_cache["tracks"]
    assert abs(listener.state_cache["tracks"][2]["volume"] - (-6.0)) < 0.01
