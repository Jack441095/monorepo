"""Deterministic coverage for the investor-demo preflight runner."""

from __future__ import annotations

import urllib.error
from pathlib import Path

from scripts.demo_preflight import DemoPreflight, load_fixture


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
        if path == "/api/ableton/osc/return-tracks":
            return {"ok": True, "return_tracks": [{"index": 0, "name": "A-Reverb", "devices": ["Hybrid Reverb"]}]}, 3.0
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


def test_transport_failure_is_plain_english_without_errno_or_runtime_type() -> None:
    runner = DemoPreflight("http://127.0.0.1:8090", expected_tracks=[])

    result = runner._check(
        "server_health",
        lambda: (_ for _ in ()).throw(urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))),
    )

    assert result.passed is False
    assert result.detail == "KENN isn't responding at http://127.0.0.1:8090 — start the server and retry."
    assert "urlopen" not in result.detail
    assert "Errno" not in result.detail


def test_unexpected_preflight_exception_does_not_leak_raw_details() -> None:
    runner = DemoPreflight("http://kenn.test", expected_tracks=[])

    result = runner._check("latency", lambda: (_ for _ in ()).throw(ValueError("raw parser internals")))

    assert result.passed is False
    assert result.detail == "This preflight check could not complete safely — inspect the KENN server log, then retry."
    assert "raw parser internals" not in result.detail


def test_default_demo_fixture_contract_is_named_and_device_bound() -> None:
    fixture = Path(__file__).resolve().parents[5] / "tooling" / "demo_session_fixture.json"

    tracks, devices, returns = load_fixture(fixture)

    assert len(tracks) == 8
    assert tracks[:2] == ["Kick", "Snare / Clap"]
    assert devices["Bass"] == ["EQ Eight"]
    assert devices["Lead Vocal"] == ["Compressor"]
    assert returns == {"A-Reverb": ["Hybrid Reverb"]}


def test_device_check_reports_exact_fixture_mismatch() -> None:
    runner = FakePreflight(
        "http://kenn.test",
        expected_tracks=["Kick", "Bass"],
        required_devices={"Bass": ["EQ Eight", "Saturator"]},
    )

    result = runner.run(["device_control"])[0]

    assert result.passed is False
    assert result.detail == "I can see 'Bass', but it is missing: Saturator. Visible devices: EQ Eight."


def test_device_check_rejects_duplicate_eqs_on_scripted_bass_target() -> None:
    class DuplicateEqPreflight(FakePreflight):
        def _live_session(self):
            state, _ = self._request("/api/ableton/osc/session?detail=topology")
            bass = next(track for track in state["tracks"] if track["name"] == "Bass")
            bass["devices"].append({"index": 1, "name": "EQ Eight"})
            return state

    runner = DuplicateEqPreflight(
        "http://kenn.test",
        expected_tracks=["Kick", "Bass"],
        required_devices={"Bass": ["EQ Eight"]},
    )

    result = runner.run(["device_control"])[0]

    assert result.passed is False
    assert result.detail == "The Bass track must contain exactly one EQ Eight for the scripted control check; found 2."


def test_device_check_reports_required_return_device_mismatch() -> None:
    class WrongReturnPreflight(FakePreflight):
        def _request(self, path, payload=None, *, timeout=2.0):
            if path == "/api/ableton/osc/return-tracks":
                return {"ok": True, "return_tracks": [{"index": 0, "name": "A-Reverb", "devices": ["Reverb"]}]}, 3.0
            return super()._request(path, payload, timeout=timeout)

    runner = WrongReturnPreflight(
        "http://kenn.test",
        expected_tracks=["Kick", "Bass"],
        required_devices={"Bass": ["EQ Eight"]},
        required_returns={"A-Reverb": ["Hybrid Reverb"]},
    )

    result = runner.run(["device_control"])[0]

    assert result.passed is False
    assert result.detail == (
        "I can see return track 'A-Reverb', but it is missing: Hybrid Reverb. Visible devices: Reverb."
    )
