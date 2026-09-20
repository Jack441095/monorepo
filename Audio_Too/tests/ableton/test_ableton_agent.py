"""Tests for Phase 4: Ableton integration and version history database tracking."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LM = ROOT / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM.parent))

from agents.MixReview.ableton_live_api import AbletonOSCClient
from kenn.core import session_memory


def test_osc_message_encoding() -> None:
    client = AbletonOSCClient()
    # Address: "/test", Args: [42, 3.14, "hello"]
    encoded = client._encode_message("/test", [42, 3.14, "hello"])
    
    # Assert length is multiple of 4
    assert len(encoded) % 4 == 0
    
    # 1. Address block "/test" (5 chars) + 3 null bytes = 8 bytes
    assert encoded[:8] == b"/test\x00\x00\x00"
    
    # 2. Tag block ",ifs" (4 chars) + 4 null bytes = 8 bytes
    assert encoded[8:16] == b",ifs\x00\x00\x00\x00"


def test_apply_repair_chain_sends_udp(monkeypatch) -> None:
    client = AbletonOSCClient()
    
    sent_packets = []
    def mock_sendto(self_obj, packet, address):
        sent_packets.append((packet, address))
        
    import socket
    monkeypatch.setattr(socket.socket, "sendto", mock_sendto)
    
    repair = {
        "track": "Master",
        "device": 2,
        "params": [
            {"parameter": 1, "value": 440.0},
            {"parameter": 3, "value": -6.0}
        ]
    }
    
    success = client.apply_repair_chain(repair)
    assert success is True
    assert len(sent_packets) == 2
    
    # First message: track_idx=-1, device_idx=2, param_idx=1, value=440.0
    # Second message: track_idx=-1, device_idx=2, param_idx=3, value=-6.0
    packet1, addr1 = sent_packets[0]
    assert addr1 == ("127.0.0.1", 9000)
    assert b"/live/device/set/parameter/value" in packet1


def test_mix_versioning_sqlite(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "test_kenn.db"
    monkeypatch.setattr(session_memory, "DB_PATH", db_file)
    
    # Ensure tables are created
    session_memory._get_db()
    
    # Verify no versions initially
    versions = session_memory.list_mix_versions("session456")
    assert len(versions) == 0
    
    # Save a version
    metrics = {"score": 90, "filename": "mix_v1.wav"}
    repair = {"track": 0, "params": []}
    session_memory.save_mix_version("session456", "v1", metrics, repair)
    
    # Retrieve and verify
    versions = session_memory.list_mix_versions("session456")
    assert len(versions) == 1
    assert versions[0]["version_label"] == "v1"
    assert versions[0]["metrics"]["score"] == 90
    assert versions[0]["repair_chain"]["track"] == 0


def test_ableton_bridge_version_history(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "test_kenn.db"
    monkeypatch.setattr(session_memory, "DB_PATH", db_file)
    
    # Ensure tables are created
    session_memory._get_db()
    
    import ableton_bridge
    
    # Verify no versions initially
    res = ableton_bridge.list_mix_versions("sess123")
    assert res["ok"] is True
    assert len(res["versions"]) == 0
    
    # Save a version via bridge
    metrics = {"score": 95, "filename": "bridge_v1.wav"}
    repair = {"track": 1, "params": []}
    save_res = ableton_bridge.save_mix_version("sess123", "bridge_v1", metrics, repair)
    assert save_res["ok"] is True
    
    # Retrieve and verify via bridge
    res = ableton_bridge.list_mix_versions("sess123")
    assert res["ok"] is True
    assert len(res["versions"]) == 1
    assert res["versions"][0]["version_label"] == "bridge_v1"
    assert res["versions"][0]["metrics"]["score"] == 95

