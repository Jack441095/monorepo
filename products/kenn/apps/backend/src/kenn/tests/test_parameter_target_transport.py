"""Exercise shipped registration and OSC bytes, with explicit stand-ins for Live objects."""
from __future__ import annotations

import importlib
import socket
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from kenn.ableton_osc_bridge import AbletonOSCClient
from kenn.abletonosc_protocol import decode_packet, encode_message
from kenn.core.live_action_service import LiveActionService


class Parameter:
    name = original_name = "Drive"
    min, max, is_quantized, is_enabled, state, automation_state = 0.0, 1.0, False, True, 0, 0
    def __init__(self):
        self._value, self.writes = 0.25, []
    @property
    def value(self):
        return self._value
    @value.setter
    def value(self, value):
        self._value = value
        self.writes.append(value)
    def str_for_value(self, value):
        return f"{value:.2f} raw"


class Registration:
    def __init__(self):
        self.handlers = {}
    def add_handler(self, path, callback):
        assert path not in self.handlers
        self.handlers[path] = callback


@pytest.fixture
def bundle(monkeypatch):
    # Only the framework base is stubbed. The actual SongHandler must register the actual new callbacks.
    name = "kenn_test_abletonosc"
    package = types.ModuleType(name)
    package.__path__ = [str(Path(__file__).resolve().parents[5] / "integrations/ableton-osc/abletonosc")]
    monkeypatch.setitem(sys.modules, name, package)
    base = types.ModuleType(name + ".handler")
    class Base:
        def _call_method(self, *args):
            raise NotImplementedError
        _get_property = _set_property = _start_listen = _stop_listen = _call_method
    base.AbletonOSCHandler = Base
    monkeypatch.setitem(sys.modules, name + ".handler", base)
    monkeypatch.setitem(sys.modules, "Live", types.ModuleType("Live"))
    module = importlib.import_module(name + ".song")
    parameter = Parameter()
    device = SimpleNamespace(name="Test Filter", class_name="Test", parameters=[parameter], chains=[])
    rack = device
    for family in ("Drum Rack", "MIDI Effect Rack", "Audio Effect Rack", "Instrument Rack"):
        rack = SimpleNamespace(name=family, class_name="Rack", parameters=[], chains=[SimpleNamespace(name="Bass", devices=[rack])])
    track = SimpleNamespace(name="Duplicate", devices=[device, rack])
    song = SimpleNamespace(tracks=[track], return_tracks=[track], master_track=track)
    handler = module.SongHandler.__new__(module.SongHandler)
    handler.song, handler.osc_server = song, Registration()
    handler.init_api()
    yield handler, parameter
    # Avoid retaining the stand-in framework in another test's import cache.
    for key in list(sys.modules):
        if key.startswith(name + "."):
            del sys.modules[key]


@pytest.mark.parametrize("kind,path", [("track", [0]), ("return", [0]), ("master", [0]), ("track", [1, 0, 0, 0, 0, 0, 0, 0, 0])])
def test_real_registration_serialization_and_lost_ack_readback(bundle, kind, path):
    handler, parameter = bundle
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(0.05)
    stopped, errors, received = threading.Event(), [], []
    def serve():
        while not stopped.is_set():
            try:
                raw, peer = server.recvfrom(65507)
            except socket.timeout:
                continue
            try:
                for address, args in decode_packet(raw):
                    received.append(address)
                    response = handler.osc_server.handlers[address](args)
                    if address.endswith("/write"):
                        continue  # Drop only the acknowledgement: the service must observe the value, never resend.
                    server.sendto(encode_message(address, ["stale-nonce", response[1]]), peer)
                    server.sendto(encode_message(address, response), peer)
            except Exception as exc:
                errors.append(exc)
    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    client = AbletonOSCClient(send_port=server.getsockname()[1], recv_port=0, query_timeout=0.15)
    try:
        service = LiveActionService(client)
        result = service.propose_addressed_parameter_action(address={"kind": kind, "index": 0, "device_path": path},
            parameter_index=0, parameter_name="Drive", device_name="Test Filter", value=0.75, unit="raw", session_id="bundle-test")
        assert result["ok"], result
        proposal = result["proposal"]
        result = service.execute_device_action(proposal, confirm_token=proposal["confirmation_token"], session_id="bundle-test")
        assert result["receipt"]["verified"], result
        assert result["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
        assert parameter.writes == [0.75]
        assert received.count("/live/kenn/parameter_target/write") == 1
        assert received.count("/live/kenn/parameter_target/features") >= 3
        assert not errors
    finally:
        client.close()
        stopped.set()
        worker.join(timeout=1)
        server.close()


def test_bundle_refuses_replacement_replay_and_missing_permission_flags(bundle):
    handler, parameter = bundle
    targets = handler.parameter_targets
    address = {"kind": "track", "index": 0, "device_path": [0]}
    expected = targets.read(address, 0)
    assert targets.write(address, 0, 0.5, expected)["sent"]
    with pytest.raises(ValueError):
        targets.write(address, 0, 0.5, expected)
    expected = targets.read(address, 0)
    handler.song.tracks[0].devices[0].parameters[0] = Parameter()
    with pytest.raises(ValueError, match="objects"):
        targets.read(address, 0, expected["observation_token"])
    parameter = handler.song.tracks[0].devices[0].parameters[0]
    parameter.state = None
    expected = targets.read(address, 0)
    with pytest.raises(ValueError, match="metadata"):
        targets.write(address, 0, 0.7, expected)
    assert parameter.writes == []


def test_missing_feature_is_not_inferred_from_allowlist(monkeypatch):
    client = AbletonOSCClient(defer_bind=True)
    monkeypatch.setattr(client, "_parameter_target_request", lambda operation, payload: {"success": True, "features": []})
    result = client.get_addressed_parameter({"kind": "return", "index": 0, "device_path": [0]}, 0)
    assert not result["success"]
    assert "does not expose" in result["error"]
    client.close()
