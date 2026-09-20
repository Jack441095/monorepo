"""Tests for wiring the existing Ableton OSC push into Thursday chat/voice.

docs/CAPABILITY_IMPROVEMENTS_2026-07-06.md flagged that AbletonOSCClient
(studio/agents/MixReview/ableton_live_api.py) only had one caller — a KENN
web endpoint (/api/ableton/apply-repair) with no frontend button wired to
it at all. thursday/client.py now exposes the same OSC push, gated behind
the same daw_control action-policy flag, and thursday/registry_handlers.py
parses a natural-language command for it so voice/chat can trigger it.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday import client as api  # noqa: E402
from thursday.registry.handlers import _handle_ableton_push  # noqa: E402


def test_ableton_osc_status_reports_client_available() -> None:
    status = api.ableton_osc_status()
    assert status == {"ok": True, "status": "initialized", "port": 9000}


def test_set_parameter_blocked_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
    result = api.ableton_set_parameter(2, 1, 3, -6.0)
    assert result["ok"] is False
    assert "AUDIO_TOO_ALLOW_DAW_CONTROL" in result["error"]


def test_apply_repair_chain_blocked_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_ALLOW_DAW_CONTROL", raising=False)
    result = api.ableton_apply_repair_chain({"track": 0, "device": 0, "params": []})
    assert result["ok"] is False
    assert "AUDIO_TOO_ALLOW_DAW_CONTROL" in result["error"]


def test_set_parameter_sends_udp_when_allowed(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    sent_packets = []

    def fake_sendto(self_obj, packet, address):
        sent_packets.append((packet, address))

    monkeypatch.setattr(socket.socket, "sendto", fake_sendto)
    result = api.ableton_set_parameter("master", 2, 1, 440.0)
    assert result == {"ok": True}
    assert len(sent_packets) == 1
    packet, address = sent_packets[0]
    assert address == ("127.0.0.1", 9000)
    assert b"/live/device/set/parameter/value" in packet


def test_apply_repair_chain_sends_udp_when_allowed(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_ALLOW_DAW_CONTROL", "1")
    sent_packets = []

    def fake_sendto(self_obj, packet, address):
        sent_packets.append((packet, address))

    monkeypatch.setattr(socket.socket, "sendto", fake_sendto)
    repair_chain = {
        "track": "Master",
        "device": 2,
        "params": [{"parameter": 1, "value": 440.0}, {"parameter": 3, "value": -6.0}],
    }
    result = api.ableton_apply_repair_chain(repair_chain)
    assert result == {"ok": True}
    assert len(sent_packets) == 2


def test_handle_ableton_push_parses_command_and_calls_api(monkeypatch) -> None:
    calls = []

    class FakeApi:
        def ableton_set_parameter(self, track, device, parameter, value):
            calls.append((track, device, parameter, value))
            return {"ok": True}

    reply = _handle_ableton_push(FakeApi(), "set ableton track 2 device 1 parameter 3 to -6")
    assert calls == [("2", 1, 3, -6.0)]
    assert "Pushed to Ableton" in reply
    assert "track 2" in reply
    assert "device 1" in reply
    assert "parameter 3" in reply


def test_handle_ableton_push_accepts_master_track() -> None:
    class FakeApi:
        def ableton_set_parameter(self, track, device, parameter, value):
            assert track.lower() == "master"
            return {"ok": True}

    reply = _handle_ableton_push(FakeApi(), "push to ableton track master device 0 parameter 1 to 0.5")
    assert "master" in reply.lower()


def test_handle_ableton_push_asks_for_details_when_unparseable() -> None:
    class FakeApi:
        def ableton_set_parameter(self, *a, **k):
            raise AssertionError("should not be called")

    reply = _handle_ableton_push(FakeApi(), "push that to ableton")
    assert "track, device, parameter, and value" in reply


def test_handle_ableton_push_surfaces_policy_denial() -> None:
    class FakeApi:
        def ableton_set_parameter(self, track, device, parameter, value):
            return {"ok": False, "error": "Action disabled by policy. Set AUDIO_TOO_ALLOW_DAW_CONTROL=1 only after reviewing the security boundary."}

    reply = _handle_ableton_push(FakeApi(), "set ableton track 2 device 1 parameter 3 to -6")
    assert "Couldn't push to Ableton" in reply
    assert "AUDIO_TOO_ALLOW_DAW_CONTROL" in reply


def test_ableton_push_service_is_registered_in_studio_registry() -> None:
    from thursday.registry import build_services

    class FakeApi:
        pass

    services = build_services(FakeApi())
    assert "ableton_push" in services
