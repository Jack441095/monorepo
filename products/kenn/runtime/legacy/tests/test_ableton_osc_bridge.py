"""Unit tests for Ableton Live 12 Real-Time OSC / Remote Script Bridge.

The remote script (`AudioToo_Bridge.py`) subclasses Ableton's real
`_Framework.ControlSurface`, which only exists inside Ableton's embedded
Python runtime. To unit-test it outside Ableton, a minimal fake
`_Framework.ControlSurface` module is injected into `sys.modules` before
import -- this mirrors what real Remote Scripts provide (song(),
log_message(), schedule_message(), disconnect()) without needing Ableton
itself.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

class _FakeControlSurface:
    def __init__(self, c_instance):
        self._c_instance = c_instance

    def song(self):
        return self._c_instance.song()

    def log_message(self, msg):
        pass

    def schedule_message(self, ticks, callback):
        pass

    def disconnect(self):
        pass


_fake_control_surface_module = types.ModuleType("_Framework.ControlSurface")
_fake_control_surface_module.ControlSurface = _FakeControlSurface
_fake_framework_package = types.ModuleType("_Framework")
sys.modules.setdefault("_Framework", _fake_framework_package)
sys.modules["_Framework.ControlSurface"] = _fake_control_surface_module

from kenn.ableton_osc_bridge import AbletonOSCClient
from remote_script.AudioToo_Bridge.AudioToo_Bridge import AudioToo_Bridge


class DummyValue:
    def __init__(self, value, min=0.0, max=1.0, name=""):
        self.value = value
        self.min = min
        self.max = max
        self.name = name


class DummyTrack:
    def __init__(self, name="Audio 1", vol=0.8, pan=0.0):
        self.name = name
        self.mixer_device = type("Mixer", (), {
            "volume": DummyValue(vol),
            "panning": DummyValue(pan, min=-1.0, max=1.0),
        })()
        self.devices = [
            type("Dev", (), {
                "name": "EQ Eight",
                "parameters": [DummyValue(0.0, min=-15.0, max=15.0)],
            })()
        ]
        self.mute = False
        self.solo = False
        self.arm = False


class DummySong:
    def __init__(self):
        self.tracks = [DummyTrack("Drums", 0.85, -0.2), DummyTrack("Vocal", 0.9, 0.0)]
        self.is_playing = False
        self.tempo = 120.0
        self.scenes = [DummyScene(), DummyScene()]

    def create_scene(self, index):
        self.scenes.insert(index, DummyScene())

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False


class DummyCInstance:
    def __init__(self):
        self._song = DummySong()

    def song(self):
        return self._song


def test_ableton_osc_client_command_encoding():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    request_id = client.send_command("/live/test", [1, 2.5])
    assert request_id is not None


def test_query_session_state_passes_through_scenes():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    fake_resp = {
        "ok": True,
        "data": {"tracks": [], "scenes": [{"index": 0, "name": "Intro"}]},
    }
    with patch.object(client, "send_command", return_value=1), \
         patch.object(client, "receive_response", return_value=fake_resp):
        result = client.query_session_state()

    assert result["status"] == "connected"
    assert result["scenes"] == [{"index": 0, "name": "Intro"}]


def test_query_session_state_scenes_empty_when_disconnected():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    with patch.object(client, "send_command", return_value=None):
        result = client.query_session_state()
    assert result["scenes"] == []


def test_ableton_osc_client_clamping():
    """Real bug found live 2026-08-05: set_track_volume/set_track_pan now
    wait for and confirm the remote script's own reply (fixing a stale-
    response bug where an unread write reply corrupted the next unrelated
    query) -- so this test drives them through a fake confirmed reply
    rather than asserting on raw send success."""
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    sent = {}

    def fake_send(address, args=None):
        sent[address] = args
        return 1

    with patch.object(client, "send_command", side_effect=fake_send), \
         patch.object(client, "receive_response", return_value={"id": 1, "ok": True, "data": {"success": True}}):
        assert client.set_track_volume(0, 1.5) is True
        assert client.set_track_pan(0, -2.0) is True

    assert sent["/live/track/set/volume"] == [0, 1.0]
    assert sent["/live/track/set/pan"] == [0, -1.0]


def test_send_and_confirm_returns_false_when_no_reply_received():
    """Nothing is listening on 11099, so the write must report unconfirmed
    (False) rather than the old fire-and-forget behavior of always
    reporting success once the UDP packet was sent."""
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    assert client.set_track_volume(0, 0.5) is False


class _FakeSocket:
    def __init__(self, replies):
        self._replies = iter(replies)

    def settimeout(self, timeout):
        pass

    def recvfrom(self, bufsize):
        return next(self._replies)


def test_receive_response_discards_stale_mismatched_id():
    """The correlation-id fix: a leftover reply from an earlier request
    must not be handed back as the answer to a different request."""
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    client.socket = _FakeSocket([
        (json.dumps({"id": 1, "ok": True, "data": {}}).encode("utf-8"), ("127.0.0.1", 11099)),
        (json.dumps({"id": 2, "ok": True, "data": {"tracks": []}}).encode("utf-8"), ("127.0.0.1", 11099)),
    ])

    resp = client.receive_response(timeout=1.0, expected_id=2)

    assert resp is not None
    assert resp["id"] == 2


def test_remote_script_bridge_packet_handler():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)

    # Test track data retrieval
    t_data = bridge.get_track_data()
    assert "tracks" in t_data
    assert len(t_data["tracks"]) == 2
    assert t_data["tracks"][0]["name"] == "Drums"

    # Test volume adjustment
    res_vol = bridge.set_track_volume(0, 0.75)
    assert res_vol["success"] is True
    assert c_inst.song().tracks[0].mixer_device.volume.value == 0.75

    # Test pan adjustment
    res_pan = bridge.set_track_pan(1, 0.5)
    assert res_pan["success"] is True
    assert c_inst.song().tracks[1].mixer_device.panning.value == 0.5

    # Test device parameter adjustment
    res_dev = bridge.set_device_parameter(0, 0, 0, 3.5)
    assert res_dev["success"] is True
    assert c_inst.song().tracks[0].devices[0].parameters[0].value == 3.5

    bridge.disconnect()


class DummyClipSlot:
    def __init__(self, has_clip=False):
        self.loaded_path = None
        self.has_clip = has_clip
        self.fired = False

    def create_clip_from_sample(self, file_path):
        self.loaded_path = file_path
        self.has_clip = True

    def fire(self):
        self.fired = True


class DummyScene:
    def __init__(self, name=""):
        self.fired = False
        self.name = name

    def fire(self):
        self.fired = True


class DummySidechainInput:
    def __init__(self):
        self.routing_target = None


class DummyCompressor:
    def __init__(self):
        self.name = "Compressor"
        self.parameters = [type("Param", (), {"name": "Sidechain On", "value": 0.0})()]
        self.sidechain_input = DummySidechainInput()


def test_get_track_data_reports_transport_state():
    c_inst = DummyCInstance()
    c_inst.song().is_playing = True
    c_inst.song().tempo = 128.0
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert data["is_playing"] is True
    assert data["tempo"] == 128.0


def test_get_track_data_reports_scene_names():
    c_inst = DummyCInstance()
    c_inst.song().scenes = [DummyScene("Intro"), DummyScene("Drop")]
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert data["scenes"] == [
        {"index": 0, "name": "Intro", "active_clip_count": 0},
        {"index": 1, "name": "Drop", "active_clip_count": 0},
    ]


def test_start_playback_sets_is_playing():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.start_playback()
    assert result["success"] is True
    assert result["is_playing"] is True
    assert c_inst.song().is_playing is True


def test_stop_playback_clears_is_playing():
    c_inst = DummyCInstance()
    c_inst.song().is_playing = True
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.stop_playback()
    assert result["success"] is True
    assert result["is_playing"] is False
    assert c_inst.song().is_playing is False


def test_set_tempo_updates_song_tempo():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.set_tempo(140.0)
    assert result["success"] is True
    assert result["tempo"] == 140.0
    assert c_inst.song().tempo == 140.0


def test_set_tempo_clamps_out_of_range_values():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    assert bridge.set_tempo(5.0)["tempo"] == 20.0
    assert bridge.set_tempo(5000.0)["tempo"] == 999.0


def test_client_transport_methods_send_confirmed_commands():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    sent = {}

    def fake_send(address, args=None):
        sent[address] = args
        return 1

    with patch.object(client, "send_command", side_effect=fake_send), \
         patch.object(client, "receive_response", return_value={"id": 1, "ok": True, "data": {"success": True}}):
        assert client.start_playback() is True
        assert client.stop_playback() is True
        assert client.set_tempo(140.0) is True

    assert sent["/live/song/transport/play"] == []
    assert sent["/live/song/transport/stop"] == []
    assert sent["/live/song/transport/set_tempo"] == [140.0]


def test_handle_packet_dispatches_transport_addresses():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    replies = []

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/song/transport/play", "args": []}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 2, "address": "/live/song/transport/set_tempo", "args": [140.0]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 3, "address": "/live/song/transport/stop", "args": []}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert [r["data"]["success"] for r in replies] == [True, True, True]
    assert c_inst.song().tempo == 140.0
    assert c_inst.song().is_playing is False


def test_get_track_data_reports_mute_solo_arm_state():
    # 2026-08-06: previously omitted entirely -- orchestrator.py's session
    # report has displayed a mute emoji since it was written, but this
    # field never existed here, so it always read as unmuted.
    c_inst = DummyCInstance()
    c_inst.song().tracks[0].mute = True
    c_inst.song().tracks[1].solo = True
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert data["tracks"][0]["muted"] is True
    assert data["tracks"][0]["soloed"] is False
    assert data["tracks"][1]["soloed"] is True
    assert data["tracks"][1]["armed"] is False


def test_get_track_data_reports_output_meter_level_when_present():
    # G2 (docs/KENN_IMPROVEMENT_PLAN.md): the first real signal-adjacent
    # data point (Track.output_meter_level/output_meter_right, both real
    # documented read-only LOM properties) added to the existing bridge
    # with no new infrastructure -- see get_track_data()'s docstring for
    # why this alone doesn't build a working detector.
    c_inst = DummyCInstance()
    c_inst.song().tracks[0].output_meter_level = 0.62
    c_inst.song().tracks[0].output_meter_right = 0.58
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert data["tracks"][0]["output_meter_level"] == 0.62
    assert data["tracks"][0]["output_meter_right"] == 0.58


def test_get_track_data_meter_level_is_none_when_property_absent():
    # DummyTrack doesn't set output_meter_level -- must degrade to None,
    # not crash, exactly like every other optional LOM property this
    # bridge reads via getattr(..., default).
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert data["tracks"][0]["output_meter_level"] is None
    assert data["tracks"][0]["output_meter_right"] is None


def test_get_track_data_ignores_meter_property_errors_on_midi_tracks():
    """Live proxy objects can raise for unsupported meter properties."""
    c_inst = DummyCInstance()

    class MidiOutputTrack(DummyTrack):
        @property
        def output_meter_right(self):
            raise RuntimeError("Tracks with MIDI output have no 'output_meter_right' property!")

    c_inst.song().tracks[1] = MidiOutputTrack("MIDI Lead")
    c_inst.song().tracks[1].output_meter_level = 0.41
    bridge = AudioToo_Bridge(c_inst)

    data = bridge.get_track_data()

    assert len(data["tracks"]) == 2
    assert data["tracks"][1]["output_meter_level"] == 0.41
    assert data["tracks"][1]["output_meter_right"] is None


def test_set_track_mute_toggles_track():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.set_track_mute(0, True)
    assert result["success"] is True
    assert result["muted"] is True
    assert c_inst.song().tracks[0].mute is True


def test_set_track_solo_toggles_track():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.set_track_solo(1, True)
    assert result["success"] is True
    assert c_inst.song().tracks[1].solo is True


def test_set_track_arm_toggles_track():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.set_track_arm(0, True)
    assert result["success"] is True
    assert c_inst.song().tracks[0].arm is True


def test_set_track_arm_rejects_when_track_cannot_be_armed():
    c_inst = DummyCInstance()
    c_inst.song().tracks[0].can_be_armed = False
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.set_track_arm(0, True)
    assert result["success"] is False
    assert "cannot be record-armed" in result["error"].lower()


def test_mute_solo_arm_reject_out_of_range_track():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    assert bridge.set_track_mute(99, True)["success"] is False
    assert bridge.set_track_solo(99, True)["success"] is False
    assert bridge.set_track_arm(99, True)["success"] is False


def test_client_set_track_mute_sends_confirmed_command():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    sent = {}

    def fake_send(address, args=None):
        sent[address] = args
        return 1

    with patch.object(client, "send_command", side_effect=fake_send), \
         patch.object(client, "receive_response", return_value={"id": 1, "ok": True, "data": {"success": True}}):
        assert client.set_track_mute(2, True) is True
        assert client.set_track_solo(2, True) is True
        assert client.set_track_arm(2, True) is True

    assert sent["/live/track/set/mute"] == [2, True]
    assert sent["/live/track/set/solo"] == [2, True]
    assert sent["/live/track/set/arm"] == [2, True]


def test_handle_packet_dispatches_mute_solo_arm():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    replies = []

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/track/set/mute", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 2, "address": "/live/track/set/solo", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 3, "address": "/live/track/set/arm", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert [r["data"]["success"] for r in replies] == [True, True, True]
    assert c_inst.song().tracks[0].mute is True
    assert c_inst.song().tracks[0].solo is True
    assert c_inst.song().tracks[0].arm is True


class DummySongWithUndoSteps(DummySong):
    """Item 4 (docs/KENN_WEEKLY_OPTIMIZATION_PLAN_2026-08-08.md):
    confirmed real via direct inspection of Ableton Live 12's bundled
    Push script (pushbase/undo_step_handler.pyc calls
    self._song.begin_undo_step()/end_undo_step()) -- DummySong itself
    deliberately doesn't have these methods so every pre-existing test
    exercises the "not available on this Live version" fallback path
    unchanged; this subclass is only for the tests that specifically
    verify the wrapping."""

    def __init__(self):
        super().__init__()
        self.undo_step_calls = []

    def begin_undo_step(self):
        self.undo_step_calls.append("begin")

    def end_undo_step(self):
        self.undo_step_calls.append("end")


class DummyCInstanceWithUndoSteps(DummyCInstance):
    def __init__(self):
        self._song = DummySongWithUndoSteps()


def test_volume_write_is_wrapped_in_a_native_undo_step():
    c_inst = DummyCInstanceWithUndoSteps()
    bridge = AudioToo_Bridge(c_inst)

    with patch.object(bridge, "send_response"):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/track/set/volume", "args": [0, 0.6]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert c_inst.song().undo_step_calls == ["begin", "end"]
    assert c_inst.song().tracks[0].mixer_device.volume.value == 0.6


def test_mute_solo_arm_writes_are_each_wrapped_in_their_own_undo_step():
    c_inst = DummyCInstanceWithUndoSteps()
    bridge = AudioToo_Bridge(c_inst)

    with patch.object(bridge, "send_response"):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/track/set/mute", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 2, "address": "/live/track/set/solo", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 3, "address": "/live/track/set/arm", "args": [0, True]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert c_inst.song().undo_step_calls == ["begin", "end", "begin", "end", "begin", "end"]


def test_read_only_track_data_query_is_never_wrapped_in_an_undo_step():
    c_inst = DummyCInstanceWithUndoSteps()
    bridge = AudioToo_Bridge(c_inst)

    with patch.object(bridge, "send_response"):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/song/get/track_data", "args": []}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert c_inst.song().undo_step_calls == []


def test_undo_step_wrapping_falls_back_when_not_available_on_this_live_version():
    # DummySong (no begin_undo_step/end_undo_step) -- confirms the write
    # still happens even when the Live version/API surface doesn't have
    # this method, never silently dropping the write.
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)

    with patch.object(bridge, "send_response"):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/track/set/volume", "args": [0, 0.6]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert c_inst.song().tracks[0].mixer_device.volume.value == 0.6


def test_load_clip_to_track_creates_clip_from_sample():
    # 2026-08-06: this handler had zero test coverage despite being a real,
    # working Live Object Model call (create_clip_from_sample), not a stub
    # as an earlier plan-doc draft incorrectly claimed.
    c_inst = DummyCInstance()
    track = c_inst.song().tracks[0]
    slot = DummyClipSlot()
    track.clip_slots = [slot]
    track.has_audio_input = True
    bridge = AudioToo_Bridge(c_inst)

    result = bridge.load_clip_to_track(0, 0, "/tmp/loop.wav")

    assert result["success"] is True
    assert slot.loaded_path == "/tmp/loop.wav"


def test_load_clip_to_track_rejects_out_of_range_track():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.load_clip_to_track(99, 0, "/tmp/loop.wav")
    assert result["success"] is False
    assert "out of range" in result["error"].lower()


def test_load_clip_to_track_rejects_out_of_range_clip_slot():
    c_inst = DummyCInstance()
    track = c_inst.song().tracks[0]
    track.clip_slots = [DummyClipSlot()]
    track.has_audio_input = True
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.load_clip_to_track(0, 5, "/tmp/loop.wav")
    assert result["success"] is False
    assert "clip slot" in result["error"].lower()


def test_launch_clip_fires_slot_with_a_clip():
    c_inst = DummyCInstance()
    track = c_inst.song().tracks[0]
    slot = DummyClipSlot(has_clip=True)
    track.clip_slots = [slot]
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.launch_clip(0, 0)
    assert result["success"] is True
    assert slot.fired is True


def test_launch_clip_rejects_empty_slot():
    c_inst = DummyCInstance()
    track = c_inst.song().tracks[0]
    slot = DummyClipSlot(has_clip=False)
    track.clip_slots = [slot]
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.launch_clip(0, 0)
    assert result["success"] is False
    assert "no clip" in result["error"].lower()
    assert slot.fired is False


def test_launch_clip_rejects_out_of_range_track_or_slot():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    assert bridge.launch_clip(99, 0)["success"] is False
    c_inst.song().tracks[0].clip_slots = [DummyClipSlot(has_clip=True)]
    assert bridge.launch_clip(0, 5)["success"] is False


def test_launch_scene_fires_scene():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.launch_scene(1)
    assert result["success"] is True
    assert c_inst.song().scenes[1].fired is True
    assert c_inst.song().scenes[0].fired is False


def test_launch_scene_rejects_out_of_range_index():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.launch_scene(99)
    assert result["success"] is False
    assert "out of range" in result["error"].lower()


def test_client_launch_clip_and_scene_send_confirmed_commands():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    sent = {}

    def fake_send(address, args=None):
        sent[address] = args
        return 1

    with patch.object(client, "send_command", side_effect=fake_send), \
         patch.object(client, "receive_response", return_value={"id": 1, "ok": True, "data": {"success": True}}):
        assert client.launch_clip(0, 2) is True
        assert client.launch_scene(3) is True

    assert sent["/live/clip/launch"] == [0, 2]
    assert sent["/live/scene/launch"] == [3]


def test_handle_packet_dispatches_clip_and_scene_launch():
    c_inst = DummyCInstance()
    track = c_inst.song().tracks[0]
    track.clip_slots = [DummyClipSlot(has_clip=True)]
    bridge = AudioToo_Bridge(c_inst)
    replies = []

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/clip/launch", "args": [0, 0]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 2, "address": "/live/scene/launch", "args": [0]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert [r["data"]["success"] for r in replies] == [True, True]


class _BrowserItem:
    def __init__(self, name, is_loadable=False, children=()):
        self.name = name
        self.is_loadable = is_loadable
        self.children = list(children)


def _make_live_mock(device_names):
    """Build a fake Live module whose browser contains the given device names."""
    items = [_BrowserItem(n, is_loadable=True) for n in device_names]
    audio_effects = _BrowserItem("Audio Effects", children=items)
    browser = type("Browser", (), {
        "audio_effects": audio_effects,
        "midi_effects": _BrowserItem("MIDI Effects"),
        "instruments": _BrowserItem("Instruments"),
        "plugins": _BrowserItem("Plugins"),
        "load_item": staticmethod(lambda item: None),
    })()
    app = type("App", (), {"browser": browser})()
    application_mod = type("Application", (), {"get_application": staticmethod(lambda: app)})()
    return type("Live", (), {"Application": application_mod})()


def test_create_device_on_track_uses_create_device_when_available():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    live_mock = _make_live_mock(["EQ Eight"])
    with patch("remote_script.AudioToo_Bridge.AudioToo_Bridge.Live", live_mock):
        result = bridge.create_device_on_track(0, "EqEight")
    assert result["success"] is True
    assert result["device_name"] == "EQ Eight"


def test_create_device_on_track_falls_back_to_create_audio_effect():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    live_mock = _make_live_mock(["Limiter"])
    with patch("remote_script.AudioToo_Bridge.AudioToo_Bridge.Live", live_mock):
        result = bridge.create_device_on_track(0, "Limiter")
    assert result["success"] is True
    assert result["device_name"] == "Limiter"


def test_create_device_on_track_reports_unsupported_when_neither_method_exists():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    live_mock = _make_live_mock([])
    with patch("remote_script.AudioToo_Bridge.AudioToo_Bridge.Live", live_mock):
        result = bridge.create_device_on_track(0, "Compressor")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_configure_sidechain_routing_sets_sidechain_input_target():
    c_inst = DummyCInstance()
    bass_track = c_inst.song().tracks[0]
    kick_track = c_inst.song().tracks[1]
    compressor = DummyCompressor()
    bass_track.devices = [compressor]
    bridge = AudioToo_Bridge(c_inst)

    result = bridge.configure_sidechain_routing(0, 1)

    assert result["success"] is True
    assert compressor.sidechain_input.routing_target is kick_track
    assert compressor.parameters[0].value == 1.0


def test_configure_sidechain_routing_fails_without_compressor():
    c_inst = DummyCInstance()
    c_inst.song().tracks[0].devices = []
    bridge = AudioToo_Bridge(c_inst)
    result = bridge.configure_sidechain_routing(0, 1)
    assert result["success"] is False
    assert "no compressor" in result["error"].lower()


def test_handle_packet_dispatches_clip_load_and_device_create_and_sidechain():
    c_inst = DummyCInstance()
    track0 = c_inst.song().tracks[0]
    track0.clip_slots = [DummyClipSlot()]
    track0.has_audio_input = True
    compressor = DummyCompressor()
    track0.devices = [compressor]
    bridge = AudioToo_Bridge(c_inst)
    replies = []
    live_mock = _make_live_mock(["Utility"])

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)), \
         patch("remote_script.AudioToo_Bridge.AudioToo_Bridge.Live", live_mock):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/clip/load", "args": [0, 0, "/tmp/x.wav"]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 2, "address": "/live/device/create", "args": [0, "Utility"]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )
        bridge.handle_packet(
            json.dumps({"id": 3, "address": "/live/device/sidechain", "args": [0, 1]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert [r["data"]["success"] for r in replies] == [True, True, True]


def test_remote_script_bridge_echoes_request_id_in_response():
    """Real bug found live 2026-08-05: the response must echo the
    request's own id, or the client can't tell a stale reply from the
    one it's actually waiting for."""
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    sent_replies = []

    def fake_send_response(payload, addr):
        sent_replies.append(payload)

    with patch.object(bridge, "send_response", side_effect=fake_send_response):
        data = json.dumps({"id": 42, "address": "/live/song/get/track_data", "args": []}).encode("utf-8")
        bridge.handle_packet(data, ("127.0.0.1", 55555))

    assert len(sent_replies) == 1
    assert sent_replies[0]["id"] == 42
    bridge.disconnect()


def _rack_track_with_macros():
    track = DummyTrack()
    track.devices = [
        type("Dev", (), {
            "name": "Vocal Rack",
            "parameters": [
                DummyValue(0.0, name="Device On"),
                DummyValue(64.0, min=0.0, max=127.0, name="Macro 1"),
                DummyValue(20.0, min=0.0, max=127.0, name="Macro 2"),
            ],
        })()
    ]
    return track


def test_get_device_parameters_lists_macro_knobs_by_name():
    c_inst = DummyCInstance()
    c_inst.song().tracks[0] = _rack_track_with_macros()
    bridge = AudioToo_Bridge(c_inst)

    result = bridge.get_device_parameters(0, 0)

    assert result["success"] is True
    assert result["device_name"] == "Vocal Rack"
    names = [p["name"] for p in result["parameters"]]
    assert names == ["Device On", "Macro 1", "Macro 2"]
    assert result["parameters"][2]["index"] == 2


def test_get_device_parameters_rejects_out_of_range_track_or_device():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)

    assert bridge.get_device_parameters(99, 0)["success"] is False
    assert bridge.get_device_parameters(0, 99)["success"] is False


def test_client_get_device_parameters_sends_confirmed_command():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    fake_resp = {
        "ok": True,
        "data": {"success": True, "device_name": "Vocal Rack", "parameters": [{"index": 1, "name": "Macro 1", "value": 64.0, "min": 0.0, "max": 127.0}]},
    }
    with patch.object(client, "send_command", return_value=1), \
         patch.object(client, "receive_response", return_value=fake_resp):
        result = client.get_device_parameters(0, 0)

    assert result["success"] is True
    assert result["parameters"][0]["name"] == "Macro 1"


def test_client_get_device_parameters_reports_failure_when_disconnected():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    with patch.object(client, "send_command", return_value=None):
        result = client.get_device_parameters(0, 0)
    assert result["success"] is False


def test_handle_packet_dispatches_device_get_parameters():
    c_inst = DummyCInstance()
    c_inst.song().tracks[0] = _rack_track_with_macros()
    bridge = AudioToo_Bridge(c_inst)
    replies = []

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/device/get/parameters", "args": [0, 0]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert replies[0]["data"]["success"] is True
    assert [p["name"] for p in replies[0]["data"]["parameters"]] == ["Device On", "Macro 1", "Macro 2"]


def test_create_scene_appends_at_the_end_and_sets_name():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    existing_count = len(c_inst.song().scenes)

    result = bridge.create_scene("Chorus")

    assert result["success"] is True
    assert result["scene_index"] == existing_count
    assert result["name"] == "Chorus"
    assert len(c_inst.song().scenes) == existing_count + 1


def test_create_scene_without_a_name_leaves_it_blank():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)

    result = bridge.create_scene("")

    assert result["success"] is True
    assert result["name"] == ""


def test_create_scene_reports_failure_when_no_song():
    c_inst = DummyCInstance()
    c_inst._song = None
    bridge = AudioToo_Bridge(c_inst)

    result = bridge.create_scene("Verse")

    assert result["success"] is False


def test_client_create_scene_sends_confirmed_command_and_returns_data():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    fake_resp = {"ok": True, "data": {"success": True, "scene_index": 2, "name": "Bridge"}}
    with patch.object(client, "send_command", return_value=1), \
         patch.object(client, "receive_response", return_value=fake_resp):
        result = client.create_scene("Bridge")

    assert result == {"success": True, "scene_index": 2, "name": "Bridge"}


def test_client_create_scene_reports_failure_when_disconnected():
    client = AbletonOSCClient(host="127.0.0.1", send_port=11099)
    with patch.object(client, "send_command", return_value=None):
        result = client.create_scene("Verse")
    assert result["success"] is False


def test_handle_packet_dispatches_scene_create():
    c_inst = DummyCInstance()
    bridge = AudioToo_Bridge(c_inst)
    replies = []

    with patch.object(bridge, "send_response", side_effect=lambda payload, addr: replies.append(payload)):
        bridge.handle_packet(
            json.dumps({"id": 1, "address": "/live/scene/create", "args": ["Drop"]}).encode("utf-8"),
            ("127.0.0.1", 1),
        )

    assert replies[0]["data"]["success"] is True
    assert replies[0]["data"]["name"] == "Drop"
