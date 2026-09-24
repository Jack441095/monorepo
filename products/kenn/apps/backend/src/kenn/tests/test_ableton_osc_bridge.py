from __future__ import annotations

import inspect
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import kenn.ableton_osc_bridge as ableton_osc_bridge
from kenn.ableton_osc_bridge import READ_ENDPOINTS, WRITE_ENDPOINTS, AbletonOSCClient
from kenn.abletonosc_protocol import decode_packet, encode_message


def _reply(server: socket.socket, address: tuple[str, int], path: str, args: list) -> None:
    server.sendto(encode_message(path, args), address)


def _track_query_response(path: str, args: list, state: dict) -> list | None:
    track_index = int(args[0]) if args else 0
    if state.get("unsupported_understanding") and path in {
        "/live/view/get/selected_scene", "/live/song/get/cue_points",
        "/live/song/get/num_return_tracks", "/live/song/get/return_track_names",
        "/live/song/get/return_track_devices", "/live/track/get/input_routing_type",
        "/live/track/get/input_routing_channel", "/live/track/get/output_routing_type",
        "/live/track/get/output_routing_channel", "/live/track/get/clips/name",
        "/live/track/get/is_grouped", "/live/track/get/is_foldable", "/live/track/get/group_track",
        "/live/track/get/clips/length", "/live/track/get/clips/color",
        "/live/track/get/arrangement_clips/name", "/live/track/get/arrangement_clips/length",
        "/live/track/get/arrangement_clips/start_time", "/live/track/get/send",
    }:
        return None
    if path == "/live/song/get/num_tracks":
        return [1]
    if path == "/live/song/get/track_names":
        return ["Vocal"]
    if path == "/live/song/get/num_scenes":
        return [0]
    if path == "/live/song/get/scenes/name":
        return []
    if path == "/live/song/get/cue_points":
        return [item for pair in (state.get("cue_points") or []) for item in pair]
    if path == "/live/song/get/num_return_tracks":
        return [len(state.get("return_tracks") or [])]
    if path == "/live/song/get/return_track_names":
        return [rt["name"] for rt in (state.get("return_tracks") or [])]
    if path == "/live/song/get/return_track_devices":
        return_index = int(args[0])
        return_tracks = state.get("return_tracks") or []
        devices = return_tracks[return_index]["devices"] if return_index < len(return_tracks) else []
        return [return_index] + devices
    if path == "/live/song/get/tempo":
        return [120.0]
    if path == "/live/song/get/signature_numerator":
        return [4]
    if path == "/live/song/get/signature_denominator":
        return [4]
    if path == "/live/song/get/root_note":
        return [0]
    if path == "/live/song/get/scale_name":
        return ["Major"]
    if path == "/live/song/get/is_playing":
        return [False]
    if path == "/live/song/get/current_song_time":
        return [float(state.get("current_song_time", 0.0))]
    if path == "/live/view/get/selected_track":
        return [int(state.get("selected_track_index", 0))]
    if path == "/live/view/get/selected_device":
        selected_device = state.get("selected_device")
        if selected_device is None:
            return None
        return [int(selected_device[0]), int(selected_device[1])]
    if path == "/live/view/get/selected_scene":
        return [1]
    if path == "/live/track/get/num_devices":
        return [track_index, 1 if state.get("device") else 0]
    if path == "/live/track/get/has_midi_input":
        return [track_index, bool(state.get("has_midi_input", True))]
    if path == "/live/track/get/devices/name":
        return [track_index, state["device"]] if state.get("device") else [track_index]
    if path == "/live/device/get/parameters/name":
        return [track_index, int(args[1]), "Output"] if state.get("device") else None
    if path == "/live/device/get/parameters/value":
        return [track_index, int(args[1]), 0.0] if state.get("device") else None
    if path == "/live/device/get/parameters/min":
        return [track_index, int(args[1]), -12.0] if state.get("device") else None
    if path == "/live/device/get/parameters/max":
        return [track_index, int(args[1]), 12.0] if state.get("device") else None
    if path == "/live/device/get/parameters/is_quantized":
        return [track_index, int(args[1]), False] if state.get("device") else None
    if path == "/live/device/get/parameter/value_string":
        return [track_index, int(args[1]), int(args[2]), "0 dB"] if state.get("device") else None
    if path == "/live/device/get/name":
        return [track_index, int(args[1]), state["device"]] if state.get("device") else None
    if path == "/live/track/get/volume":
        return [track_index, state["volume"]]
    if path == "/live/track/get/panning":
        return [track_index, 0.0]
    if path == "/live/track/get/mute":
        return [track_index, False]
    if path == "/live/track/get/solo":
        return [track_index, False]
    if path == "/live/track/get/arm":
        return [track_index, False]
    if path == "/live/track/get/output_meter_level":
        value = state.get("output_meter_level")
        return None if value is None else [track_index, value]
    if path == "/live/track/get/output_meter_right":
        value = state.get("output_meter_right")
        return None if value is None else [track_index, value]
    if path == "/live/track/get/is_grouped":
        return [track_index, bool(state.get("is_grouped", False))]
    if path == "/live/track/get/is_foldable":
        return [track_index, bool(state.get("is_foldable", False))]
    if path == "/live/track/get/group_track":
        return [track_index, state.get("group_track")]
    if path == "/live/track/get/send":
        send_index = int(args[1])
        return [track_index, send_index, (state.get("sends") or {}).get(send_index, 0.0)]
    if path in {
        "/live/track/get/input_routing_type", "/live/track/get/input_routing_channel",
        "/live/track/get/output_routing_type", "/live/track/get/output_routing_channel",
    }:
        routing = state.get("routing") or {}
        key = path.rsplit("/", 1)[-1]
        return [track_index, routing.get(key, "Master" if key == "output_routing_type" else "")]
    if path == "/live/track/get/clips/name":
        return [track_index, "Verse", None]
    if path == "/live/track/get/clips/length":
        return [track_index, 16.0, None]
    if path == "/live/track/get/clips/color":
        return [track_index, 123, None]
    if path == "/live/track/get/arrangement_clips/name":
        return [track_index, "Verse Audio"]
    if path == "/live/track/get/arrangement_clips/length":
        return [track_index, 16.0]
    if path == "/live/track/get/arrangement_clips/start_time":
        return [track_index, 1.0]
    return None


def test_osc_codec_round_trips_standard_scalar_types() -> None:
    packet = encode_message("/live/test", [3, 0.5, "EQ Eight", True, False, None])
    assert decode_packet(packet) == [("/live/test", [3, 0.5, "EQ Eight", True, False, None])]


def test_client_builds_snapshot_and_sends_standard_osc() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {
        "volume": 0.5,
        "selected_track_index": 0,
        "selected_device": (0, 0),
        "output_meter_level": 0.82,
        "output_meter_right": 0.78,
    }
    requests: list[str] = []
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    requests.append(path)
                    if path == "/live/track/set/volume":
                        state["volume"] = float(args[1])
                        continue
                    if path == "/live/view/set/selected_track":
                        state["selected_track_index"] = int(args[0])
                        continue
                    if path == "/live/view/set/selected_device":
                        state["selected_device"] = (int(args[0]), int(args[1]))
                        state["selected_track_index"] = int(args[0])
                        continue
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        probe = client.probe_connection()
        assert probe["status"] == "connected"
        assert probe["track_count"] == 1
        assert probe["track_names"] == ["Vocal"]
        topology = client.query_session_topology()
        assert topology["status"] == "connected"
        assert topology["tracks"][0]["name"] == "Vocal"
        assert "volume" not in topology["tracks"][0]
        assert "/live/track/get/volume" not in requests
        assert "/live/song/get/tempo" not in requests
        before = client.query_session_state()
        assert before["status"] == "connected"
        assert before["tracks"][0]["volume"] == 0.5
        assert before["signature_numerator"] == 4
        assert before["signature_denominator"] == 4
        assert before["root_note"] == 0
        assert before["scale_name"] == "Major"
        assert "output_meter_level" not in before["tracks"][0]
        metered = client.query_session_state(include_meters=True)
        assert metered["tracks"][0]["output_meter_level"] == pytest.approx(0.82)
        assert metered["tracks"][0]["output_meter_right"] == pytest.approx(0.78)
        assert client.last_exchange["transport"] == "abletonosc"
        transport = client.get_transport_state()
        assert transport == {"success": True, "is_playing": False}
        assert "/live/song/get/is_playing" in requests
        assert client.get_selected_device() == {"success": True, "track_index": 0, "device_index": 0}
        assert client.set_track_volume(0, 0.75) is True
        after = client.query_session_state()
        assert after["tracks"][0]["volume"] == 0.75
        assert client.set_selected_track(0) is True
        assert client.query_session_state()["selected_track_index"] == 0
        assert client.set_selected_device(0, 0) is True
        assert client.get_selected_device()["device_index"] == 0
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_requests_midi_track_creation_on_standard_song_endpoint() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    received: list[tuple[str, list]] = []
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, _address = server.recvfrom(65507)
                except socket.timeout:
                    return
                received.extend(decode_packet(raw))
                stop.set()
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.create_midi_track(4) is True
        thread.join(timeout=3)
        assert ("/live/song/create_midi_track", [4]) in received
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_requests_audio_track_creation_on_standard_song_endpoint() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    received: list[tuple[str, list]] = []
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2)
        try:
            while not stop.is_set():
                try:
                    raw, _address = server.recvfrom(65507)
                except socket.timeout:
                    return
                received.extend(decode_packet(raw))
                stop.set()
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.create_audio_track(4) is True
        thread.join(timeout=3)
        assert ("/live/song/create_audio_track", [4]) in received
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_requests_return_track_creation_and_naming_on_song_endpoints() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    received: list[tuple[str, list]] = []
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, _address = server.recvfrom(65507)
                except socket.timeout:
                    return
                received.extend(decode_packet(raw))
                if len(received) >= 2:
                    stop.set()
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.create_return_track() is True
        assert client.set_return_track_name(2, "Vocal Verb") is True
        thread.join(timeout=3)
        assert ("/live/song/create_return_track", []) in received
        assert ("/live/song/set/return_track_name", [2, "Vocal Verb"]) in received
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reads_real_return_track_identity_and_devices() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {
        "volume": 0.5,
        "return_tracks": [
            {"name": "A-Reverb", "devices": ["Reverb"]},
            {"name": "B-Delay", "devices": ["Delay"]},
        ],
    }
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        return_tracks = client.get_return_tracks()
        assert return_tracks == [
            {"index": 0, "name": "A-Reverb", "devices": ["Reverb"]},
            {"index": 1, "name": "B-Delay", "devices": ["Delay"]},
        ]
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_adds_and_names_locator_at_current_playhead() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"current_song_time": 16.0, "cue_points": []}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    if path == "/live/song/cue_point/add_or_delete":
                        cursor = state["current_song_time"]
                        existing = next((index for index, (_, beat) in enumerate(state["cue_points"]) if abs(beat - cursor) <= 1e-4), None)
                        if existing is None:
                            state["cue_points"].append(("", cursor))
                        else:
                            state["cue_points"].pop(existing)
                    elif path == "/live/song/cue_point/set/name":
                        index, name = int(args[0]), str(args[1])
                        old_name, beat = state["cue_points"][index]
                        state["cue_points"][index] = (name, beat)
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.get_current_song_time() == 16.0
        assert client.get_locators_with_status() == ([], True)
        assert client.add_locator("Chorus") is True
        assert client.get_locators() == [{"index": 0, "name": "Chorus", "time_beats": 16.0}]
        assert client.remove_locator("Chorus", 16.0) is True
        assert client.get_locators() == []
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_builds_explicit_read_only_session_understanding() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {
        "volume": 0.5,
        "device": "Compressor",
        "routing": {"input_routing_type": "Ext. In", "input_routing_channel": "1", "output_routing_type": "Master", "output_routing_channel": "1/2"},
        "sends": {0: 0.25},
        "return_tracks": [{"name": "A-Reverb", "devices": ["Hybrid Reverb"]}],
        "cue_points": [("Verse", 1.0), ("Drop", 33.0)],
        "selected_device": (0, 0),
        "is_grouped": True,
        "is_foldable": False,
        "group_track": 1,
    }
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        result = client.query_session_understanding()
        track = result["tracks"][0]
        assert result["read_only"] is True
        assert result["selected_scene_index"] == 1
        assert result["selected_device_track_index"] == 0
        assert result["selected_device_index"] == 0
        assert result["selected_device_name"] == "Compressor"
        assert result["locators"] == [{"index": 0, "name": "Verse", "time_beats": 1.0}, {"index": 1, "name": "Drop", "time_beats": 33.0}]
        assert result["return_tracks"] == [{"index": 0, "name": "A-Reverb", "devices": [{"index": 0, "name": "Hybrid Reverb"}]}]
        assert track["output_routing_type"] == "Master"
        assert track["clip_slots"] == [{"index": 0, "has_clip": True, "name": "Verse", "length": 16.0, "color": 123}, {"index": 1, "has_clip": False}]
        assert track["arrangement_clips"] == [{"index": 0, "name": "Verse Audio", "length_beats": 16.0, "start_time_beats": 1.0}]
        assert track["sends"] == [{"index": 0, "return_track_index": 0, "return_track_name": "A-Reverb", "value": 0.25}]
        assert track["is_grouped"] is True
        assert track["is_foldable"] is False
        assert track["group_track_index"] == 1
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_session_understanding_distinguishes_unsupported_reads_from_empty_observations() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"volume": 0.5, "unsupported_understanding": True}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0, query_timeout=0.03)
    try:
        result = client.query_session_understanding()
        track = result["tracks"][0]
        assert result["status"] == "connected"
        assert "locators" not in result
        assert "return_tracks" not in result
        assert "clip_slots" not in track
        assert "arrangement_clips" not in track
        assert "sends" not in track
        assert result["understanding_capabilities"] == {
            "return_tracks": False,
            "groups": False,
            "selected_scene": False,
            "selected_device": False,
            "locators": False,
            "routing": False,
            "session_clip_inventory": False,
            "arrangement_clip_inventory": False,
            "track_sends": False,
        }
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_imports_sample_into_clip_slot_and_reports_real_clip_name() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()
    received: list[tuple] = []

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    if path == "/live/track/import_sample":
                        received.append(tuple(args))
                        _reply(server, address, path, [args[0], args[1], True, "Fake Kick One"])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        result = client.import_sample_to_clip_slot(2, 0, "/some/absolute/path/Kick One.wav")
        assert result == {"success": True, "clip_name": "Fake Kick One"}
        assert received == [(2, 0, "/some/absolute/path/Kick One.wav")]
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reports_import_failure_honestly() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    if path == "/live/track/import_sample":
                        _reply(server, address, path, [args[0], args[1], False, "Sample file not found in the Live browser."])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        result = client.import_sample_to_clip_slot(2, 0, "/missing/file.wav")
        assert result == {"success": False, "error": "Sample file not found in the Live browser."}
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reads_and_writes_a_real_send_value() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"sends": {0: 0.25}}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    if path == "/live/track/set/send":
                        state["sends"][int(args[1])] = float(args[2])
                        continue
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.get_track_send(2, 0) == pytest.approx(0.25)
        assert client.set_track_send(2, 0, 0.6) is True
        assert client.get_track_send(2, 0) == pytest.approx(0.6)
        assert client.get_track_send(2, 1) in (None, pytest.approx(0.0))
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reads_empty_return_tracks_honestly() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"volume": 0.5, "return_tracks": []}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                packets = decode_packet(raw)
                for path, args in packets:
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.get_return_tracks() == []
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_serializes_concurrent_standard_osc_queries() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"volume": 0.5}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: client.query_session_state(), range(12)))
        assert len(results) == 12
        assert all(result["status"] == "connected" for result in results)
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_batched_topology_matches_out_of_order_track_replies() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()
    pending: list[tuple[str, list]] = []

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    if path == "/live/song/get/num_tracks":
                        _reply(server, address, path, [2])
                    elif path == "/live/song/get/track_names":
                        _reply(server, address, path, ["Kick", "Vocal"])
                    else:
                        pending.append((path, list(args)))
                        if len(pending) == 4:
                            # Deliberately reverse the two-track replies to
                            # prove matching uses the echoed track index.
                            for pending_path, pending_args in reversed(pending):
                                track_index = int(pending_args[0])
                                if pending_path == "/live/track/get/num_devices":
                                    response = [track_index, 1]
                                else:
                                    response = [track_index, "EQ Eight" if track_index == 1 else "Compressor"]
                                _reply(server, address, pending_path, response)
                            pending.clear()
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        state = client.query_session_topology()
        assert state["status"] == "connected"
        assert state["tracks"] == [
            {"index": 0, "name": "Kick", "devices": [{"index": 0, "name": "Compressor"}]},
            {"index": 1, "name": "Vocal", "devices": [{"index": 0, "name": "EQ Eight"}]},
        ]
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_device_matrix_inventories_exact_parameters_without_writes() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"volume": 0.5, "device": "Glue Compressor"}
    requests: list[str] = []
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    requests.append(path)
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        report = client.device_matrix_report()
        assert report["status"] == "connected"
        assert report["observed_families"] == ["Glue Compressor"]
        assert report["entries"][0]["qualification"] == "qualified"
        assert report["entries"][0]["parameter_probe"] == {
            "success": True,
            "parameter_count": 1,
            "parameters": [{"index": 0, "name": "Output", "value": 0.0, "min": -12.0, "max": 12.0, "readable": True, "quantized": False}],
        }
        assert "/live/device/set/parameter/value" not in requests
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_accepts_large_standard_osc_parameter_replies() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    if path.endswith("/parameters/name"):
                        _reply(server, address, path, [0, 0] + [f"{index} Gain A" for index in range(112)])
                    elif path.endswith("/parameters/value"):
                        _reply(server, address, path, [0, 0] + [0.0] * 112)
                    elif path.endswith("/parameters/min"):
                        _reply(server, address, path, [0, 0] + [-15.0] * 112)
                    elif path.endswith("/parameters/max"):
                        _reply(server, address, path, [0, 0] + [15.0] * 112)
                    elif path == "/live/device/get/name":
                        _reply(server, address, path, [0, 0, "EQ Eight"])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        result = client.get_device_parameters(0, 0)
        assert result["success"] is True
        assert len(result["parameters"]) == 112
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reads_targeted_ui_value_string() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    if path == "/live/device/get/parameter/value_string":
                        _reply(server, address, path, [args[0], args[1], args[2], "4:1"])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        assert client.get_device_parameter_value_string(3, 1, 5) == {
            "success": True,
            "track_index": 3,
            "device_index": 1,
            "parameter_index": 5,
            "value_string": "4:1",
        }
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_client_reads_and_writes_one_midi_clip_slot() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()
    state = {"has_clip": False, "length": 0.0, "notes": [], "is_playing": False, "is_triggered": False}

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    return
                for path, args in decode_packet(raw):
                    if path == "/live/clip_slot/get/has_clip":
                        _reply(server, address, path, [args[0], args[1], state["has_clip"]])
                    elif path == "/live/clip/get/is_midi_clip":
                        _reply(server, address, path, [args[0], args[1], True])
                    elif path == "/live/clip/get/length":
                        _reply(server, address, path, [args[0], args[1], state["length"]])
                    elif path == "/live/clip/get/notes":
                        flat = []
                        for note in state["notes"]:
                            flat.extend(note)
                        _reply(server, address, path, [args[0], args[1], *flat])
                    elif path == "/live/clip_slot/get/is_playing":
                        _reply(server, address, path, [args[0], args[1], state["is_playing"]])
                    elif path == "/live/clip_slot/get/is_triggered":
                        _reply(server, address, path, [args[0], args[1], state["is_triggered"]])
                    elif path == "/live/clip_slot/fire":
                        state["is_playing"] = True
                        state["is_triggered"] = False
                    elif path == "/live/clip_slot/stop":
                        state["is_playing"] = False
                        state["is_triggered"] = False
                    elif path == "/live/clip_slot/create_clip":
                        state["has_clip"] = True
                        state["length"] = float(args[2])
                    elif path == "/live/clip/add/notes":
                        state["notes"] = [list(args[offset:offset + 5]) for offset in range(2, len(args), 5)]
                    elif path == "/live/clip/remove/notes":
                        state["notes"] = []
                    elif path == "/live/clip_slot/delete_clip":
                        state["has_clip"] = False
                        state["notes"] = []
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0)
    try:
        empty = client.get_midi_clip_state(0, 0)
        assert empty["success"] is True
        assert empty["has_clip"] is False
        notes = [{"pitch": 36, "start_time": 0.0, "duration": 1.0, "velocity": 100, "mute": False}]
        assert client.create_midi_clip(0, 0, 4.0) is True
        assert client.add_midi_notes(0, 0, notes) is True
        populated = client.get_midi_clip_state(0, 0)
        assert populated["has_clip"] is True
        assert populated["is_midi_clip"] is True
        assert populated["notes"] == notes
        assert client.remove_all_midi_notes(0, 0) is True
        assert client.get_midi_clip_state(0, 0)["notes"] == []
        assert client.add_midi_notes(0, 0, notes) is True
        assert client.launch_clip(0, 0) is True
        assert client.get_clip_playback_state(0, 0)["is_playing"] is True
        assert client.stop_clip(0, 0) is True
        assert client.get_clip_playback_state(0, 0)["is_playing"] is False
        assert client.delete_midi_clip(0, 0) is True
        assert client.get_midi_clip_state(0, 0)["has_clip"] is False
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


# Bridge methods no active KENN feature calls today -- their OSC address
# deliberately isn't part of the declared capability contract. Adding a new
# caller for one of these should come with adding its address to
# READ_ENDPOINTS/WRITE_ENDPOINTS in the same change, not silently.
_KNOWN_UNDECLARED_DEAD_ADDRESSES = frozenset({
    "/live/clip/load",  # load_clip() has no caller; sample import uses import_sample_to_clip_slot instead
    "/live/song/create_scene",  # create_scene() has no caller; scene creation isn't a wired KENN action
    "/live/scene/set/name",  # only reachable via the same unused create_scene()
})


def test_capability_contract_declares_every_actively_used_osc_address() -> None:
    """READ_ENDPOINTS/WRITE_ENDPOINTS is the explicit contract GET
    /api/ableton/capabilities reports to a caller (e.g. a companion UI). It
    previously fell behind real functionality -- return-track enumeration,
    send control, scene launch, and sample import all shipped without their
    OSC address ever being added to either list. This scans the bridge
    module's own source for every "/live/..." address literal and fails if
    one is used by a method with a real caller elsewhere in the codebase but
    isn't declared."""
    source = inspect.getsource(ableton_osc_bridge)
    addresses = set(re.findall(r'"(/live/[a-z_/]+)"', source))
    declared = set(READ_ENDPOINTS) | set(WRITE_ENDPOINTS)
    undeclared = addresses - declared - _KNOWN_UNDECLARED_DEAD_ADDRESSES
    assert not undeclared, f"OSC addresses used by the bridge but missing from READ_ENDPOINTS/WRITE_ENDPOINTS: {sorted(undeclared)}"


def test_watchdog_ping_and_connection_state_transitions() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(0.5)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    continue
                packets = decode_packet(raw)
                for path, args in packets:
                    if path == "/live/song/get/num_tracks":
                        _reply(server, address, path, [1])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    client = AbletonOSCClient(
        send_port=port,
        recv_port=0,
        query_timeout=0.2,
        enable_circuit_breaker=True,
    )
    try:
        assert client.connection_state == "disconnected"
        assert client.is_connected is False

        # Ping success
        assert client.ping(timeout=0.5) is True
        assert client.connection_state == "connected"
        assert client.is_connected is True

        status = client.get_connection_status()
        assert status["state"] == "connected"
        assert status["circuit_breaker_enabled"] is True
        assert status["missed_heartbeats"] == 0
        assert status["last_successful_heartbeat"] > 0

        # Stop server to simulate connection drop
        stop.set()
        thread.join(timeout=3)

        # First missed ping -> degraded
        assert client.ping(timeout=0.05) is False
        assert client.connection_state == "degraded"
        assert client.is_connected is False

        # Second missed ping -> disconnected
        assert client.ping(timeout=0.05) is False
        assert client.connection_state == "disconnected"
        assert client.is_connected is False

        # Circuit breaker fast-fails queries when disconnected without waiting for query_timeout
        start = time.monotonic()
        res = client._query_args("/live/song/get/tempo")
        elapsed = time.monotonic() - start
        assert res is None
        assert elapsed < 0.05
    finally:
        client.close()


def test_watchdog_background_thread() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(0.5)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    continue
                packets = decode_packet(raw)
                for path, args in packets:
                    if path == "/live/song/get/num_tracks":
                        _reply(server, address, path, [2])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    client = AbletonOSCClient(
        send_port=port,
        recv_port=0,
        query_timeout=0.2,
    )
    try:
        assert client.connection_state == "disconnected"
        client.start_watchdog(interval=0.05, timeout=0.1)
        time.sleep(0.2)
        assert client.connection_state == "connected"
        assert client.is_connected is True
        client.stop_watchdog()
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_breaker_enabled_first_snapshot_connects_without_prior_probe() -> None:
    """A fresh breaker-enabled client must attempt first contact.

    Regression: the breaker mistook the initial "disconnected" state for a
    known outage and short-circuited every query, so a newly started
    companion reported Live offline forever until something called
    ping()/probe_connection() first.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    state = {"volume": 0.5}
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(2.0)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    continue
                for path, args in decode_packet(raw):
                    response = _track_query_response(path, args, state)
                    if response is not None:
                        _reply(server, address, path, response)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(
        send_port=port, recv_port=0, defer_bind=True, enable_circuit_breaker=True
    )
    try:
        assert client.connection_state == "disconnected"
        snapshot = client.query_session_state(include_mixer=False, force_refresh=True)
        assert snapshot["status"] == "connected"
        assert [track["name"] for track in snapshot["tracks"]] == ["Vocal"]
        assert client.connection_state == "connected"
        again = client.query_session_state(include_mixer=False, force_refresh=True)
        assert again["status"] == "connected"
    finally:
        client.close()
        stop.set()
        thread.join(timeout=3)


def test_breaker_still_fast_fails_after_a_genuine_failure() -> None:
    """One full timeout against a dead endpoint, then fast failure."""
    dead_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dead_send.bind(("127.0.0.1", 0))
    dead_send_port = dead_send.getsockname()[1]
    dead_send.close()
    client = AbletonOSCClient(
        send_port=dead_send_port,
        recv_port=0,
        defer_bind=True,
        enable_circuit_breaker=True,
        query_timeout=0.2,
    )
    try:
        assert client.query_session_state(
            include_mixer=False, force_refresh=True
        )["status"] == "offline"
        start = time.monotonic()
        assert client.query_session_state(
            include_mixer=False, force_refresh=True
        )["status"] == "offline"
        assert time.monotonic() - start < 0.15
    finally:
        client.close()


def test_open_breaker_lets_one_trial_read_through_and_recovers() -> None:
    """Regression (2026-09-24 soak): one missed reply opened the breaker and every later read was skipped, so
    KENN reported Live offline for 4 hours while Live was running, until someone pressed Test."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    answering = threading.Event()
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(0.2)
        try:
            while not stop.is_set():
                try:
                    raw, address = server.recvfrom(65507)
                except socket.timeout:
                    continue
                if not answering.is_set():
                    continue  # Live busy: the request goes unanswered
                for path, _args in decode_packet(raw):
                    if path == "/live/song/get/tempo":
                        _reply(server, address, path, [120.0])
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(host="127.0.0.1", send_port=port, recv_port=0, query_timeout=0.1,
                              enable_circuit_breaker=True)
    client._breaker_retry_seconds = 0.3
    try:
        for _ in range(2):
            assert client.ping(timeout=0.05) is False
        assert client.connection_state == "disconnected"

        started = time.monotonic()
        assert client._query_args("/live/song/get/tempo") is None  # still inside the wait: skipped, no timeout
        assert time.monotonic() - started < 0.05

        answering.set()
        time.sleep(0.35)
        assert client._query_args("/live/song/get/tempo") == [120.0]  # the trial read reaches Live
        assert client.connection_state == "connected"
        assert client._query_args("/live/song/get/tempo") == [120.0]
    finally:
        stop.set()
        client.close()
        thread.join(timeout=3)
