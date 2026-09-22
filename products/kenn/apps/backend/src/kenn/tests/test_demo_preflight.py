"""Deterministic coverage for the investor-demo preflight runner."""

from __future__ import annotations

from scripts.demo_preflight import DemoPreflight


class FakePreflight(DemoPreflight):
    def _request(self, path, payload=None, *, timeout=2.0):
        tracks = [
            {"index": 0, "name": "Kick", "pan": 0.0, "devices": []},
            {"index": 1, "name": "Bass", "devices": [{"index": 0, "name": "EQ Eight"}]},
            *({"index": index, "name": f"Track {index + 1}", "devices": []} for index in range(2, 8)),
        ]
        if path == "/api/health":
            return {"ok": True, "subsystems": {"knowledge_index": {"available": True, "active_mode": "bm25_only"}}}, 2.0
        if path == "/api/ableton/ping":
            return {"ok": True, "connected": True}, 20.0
        if path.startswith("/api/ableton/osc/session"):
            return {"status": "connected", "tracks": tracks}, 30.0
        if path == "/api/ableton/capabilities":
            return {"write_boundary": {"confirmation_required": True, "readback_required": True}}, 2.0
        if path.startswith("/api/ableton/osc/device-parameters"):
            return {"success": True, "parameters": [{"index": 1, "name": "1 Gain A"}]}, 3.0
        if path == "/api/ableton/command":
            return {"answer_mode": "session_question", "track_count": 8}, 40.0
        raise AssertionError(path)


def test_read_only_preflight_checks_pass_with_clear_details(monkeypatch) -> None:
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    runner = FakePreflight("http://kenn.test", expected_tracks=["Kick", "Bass"])

    selected = [
        "ableton_ping", "demo_session", "server_health", "retrieval_index",
        "daw_control", "session_qa", "device_control", "audio_analysis", "latency",
    ]
    results = runner.run(selected)

    assert all(item.passed for item in results)
    assert all(item.detail for item in results)


def test_undo_check_never_mutates_without_explicit_flag() -> None:
    result = FakePreflight("http://kenn.test", expected_tracks=[]).run(["undo_roundtrip"])[0]

    assert result.passed is False
    assert "--allow-mutations" in result.detail
